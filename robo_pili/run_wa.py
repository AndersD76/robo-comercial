# -*- coding: utf-8 -*-
"""
Runner standalone do bot WhatsApp — Pili Equipamentos
Prospecção: Busca → Enriquecimento → Score → Envio → Follow-up → IA
"""

import re
import sys
import time
import asyncio
import random
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from database import (
    init_database, get_empresas_sem_contato, registrar_interacao,
    atualizar_status_empresa, incrementar_contagem, log_acao,
    get_empresas_contactadas, get_estagio_conversa,
    marcar_demo_proposto, marcar_demo_confirmado,
    get_empresa_por_whatsapp, salvar_empresa, telefone_existe,
    get_empresas_para_followup,
)
from whatsapp import WhatsAppBot
from mensagens import GeradorMensagens
from config import (
    HORARIO_INICIO, HORARIO_FIM, DIAS_ATIVOS, TERMOS_BUSCA,
    CNAES_ALVO, PALAVRAS_POSITIVAS, PALAVRAS_NEGATIVAS,
    SCORE_TEM_WHATSAPP, SCORE_TEM_EMAIL, SCORE_TEM_SITE,
    SCORE_CNAE_INDUSTRIAL, SCORE_PORTE_MEDIO_GRANDE,
    CNPJ_API_URL, CNPJ_API_DELAY,
    FOLLOWUP1_DIAS, FOLLOWUP2_DIAS,
)

_BRT = timezone(timedelta(hours=-3))
_ultimo_cnpj_ts: float = 0.0  # rate limit ReceitaWS


def _ts() -> str:
    return datetime.now(_BRT).strftime('%H:%M:%S')


def _agora() -> datetime:
    return datetime.now(_BRT)


def _horario_comercial(now: datetime) -> bool:
    """Mensagens WA só em horário comercial: seg-sex 8h-18h."""
    if now.weekday() not in DIAS_ATIVOS:
        return False
    return HORARIO_INICIO <= now.hour < HORARIO_FIM


# =============================================================================
# UTILITÁRIOS
# =============================================================================

_DDDS = {
    '11', '12', '13', '14', '15', '16', '17', '18', '19',
    '21', '22', '24', '27', '28',
    '31', '32', '33', '34', '35', '37', '38',
    '41', '42', '43', '44', '45', '46', '47', '48', '49',
    '51', '53', '54', '55',
    '61', '62', '63', '64', '65', '66', '67', '68', '69',
    '71', '73', '74', '75', '77', '79',
    '81', '82', '83', '84', '85', '86', '87', '88', '89',
    '91', '92', '93', '94', '95', '96', '97', '98', '99',
}


def _valida_telefone(t: str) -> str | None:
    if not t:
        return None
    n = re.sub(r'\D', '', str(t))
    if n.startswith('55') and len(n) >= 12:
        n = n[2:]
    if len(n) not in (10, 11):
        return None
    if n[:2] not in _DDDS or len(set(n[2:])) == 1:
        return None
    return n


def _tel_para_wa(t: str) -> str | None:
    """Celular (11 dígitos) → '55XXXXXXXXXXX'. Fixo → None."""
    v = _valida_telefone(t)
    return ('55' + v) if (v and len(v) == 11) else None


def _valida_cnpj(cnpj: str) -> str | None:
    c = re.sub(r'\D', '', str(cnpj or ''))
    if len(c) != 14 or len(set(c)) == 1:
        return None

    def dig(s, p):
        r = sum(int(s[i]) * p[i] for i in range(len(p))) % 11
        return '0' if r < 2 else str(11 - r)

    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    p2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    if c[12] != dig(c[:12], p1):
        return None
    if c[13] != dig(c[:13], p2):
        return None
    return c


def _calcular_score(lead: dict) -> int:
    score = 0
    if lead.get('whatsapp'):
        score += SCORE_TEM_WHATSAPP
    if lead.get('email'):
        score += SCORE_TEM_EMAIL
    if lead.get('website'):
        score += SCORE_TEM_SITE
    cnae = str(lead.get('cnae_codigo', ''))[:2]
    if cnae in CNAES_ALVO:
        score += SCORE_CNAE_INDUSTRIAL
        lead.setdefault('segmento', CNAES_ALVO[cnae])
    porte = str(lead.get('porte', '')).lower()
    if any(p in porte for p in ('medio', 'média', 'grande')):
        score += SCORE_PORTE_MEDIO_GRANDE
    nome = lead.get('nome_fantasia', '')
    seg = lead.get('segmento', '')
    txt = f"{nome} {seg}".lower()
    for p in PALAVRAS_POSITIVAS:
        if p in txt:
            score += 3
    for p in PALAVRAS_NEGATIVAS:
        if p in txt:
            score -= 50
    return max(0, min(100, score))


# =============================================================================
# ENRIQUECIMENTO DO SITE
# =============================================================================

_PAGINAS_CONTATO = (
    '/contato', '/contact', '/fale-conosco', '/sobre', '/quem-somos',
)


def _url_raiz(url: str) -> str:
    """Extrai URL raiz (protocolo + domínio). Bing retorna subpages via cite."""
    try:
        p = urlparse(url)
        if p.scheme and p.netloc:
            return f"{p.scheme}://{p.netloc}"
    except Exception:
        pass
    return url

_EMAILS_INVALIDOS = (
    'example', 'test', 'noreply', 'no-reply', '.js', '.css',
    '.png', '.jpg', 'sentry', 'wix', 'jquery', 'mailer-daemon',
)

_PAT_EMAIL = re.compile(
    r'[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}', re.IGNORECASE
)
_PAT_CNPJ = re.compile(r'\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}')
_PAT_WA = [
    re.compile(r'wa\.me/(\+?5?5?\d{10,11})', re.I),
    re.compile(r'wa\.me/(\+?\d{8,15})', re.I),
    re.compile(
        r'api\.whatsapp\.com/send\?[^"\']*phone=(\+?\d{8,15})', re.I
    ),
    re.compile(
        r'[Ww]hats[Aa]pp[:\s\xa0]*'
        r'\(?(\d{2})\)?\s*(\d{4,5})[-.\s]?(\d{4})'
    ),
]
_PAT_TEL = [
    re.compile(r'tel:(\+?[\d\s\-\(\)]{8,})'),
    re.compile(r'\((\d{2})\)\s*(\d{4,5})[-.\s]?(\d{4})'),
    re.compile(r'(\d{2})\s*[-.]?\s*(\d{4,5})[-.\s](\d{4})'),
    re.compile(r'\b((?:55)?(?:11|12|13|14|15|16|17|18|19|21|22|24|27|28|'
               r'31|32|33|34|35|37|38|41|42|43|44|45|46|47|48|49|51|53|54|'
               r'55|61|62|63|64|65|66|67|68|69|71|73|74|75|77|79|81|82|83|'
               r'84|85|86|87|88|89|91|92|93|94|95|96|97|98|99)'
               r'\d{8,9})\b'),
]


async def _extrair_site(page, url_base: str) -> dict:
    """
    Visita a home + páginas de contato.
    Extrai: nome, whatsapp, telefone, email, cnpj.
    Usa HTML + texto limpo do body para capturar números JS-renderizados.
    """
    dados: dict = {
        'nome': None, 'whatsapp': None,
        'telefone': None, 'email': None, 'cnpj': None,
    }

    # Normaliza para raiz do domínio (Bing via cite retorna subpages)
    url_base = _url_raiz(url_base)

    paginas = [url_base] + [
        url_base.rstrip('/') + p for p in _PAGINAS_CONTATO
    ]

    for pag in paginas:
        try:
            await page.goto(
                pag, timeout=20000, wait_until='domcontentloaded'
            )
            await asyncio.sleep(random.uniform(1.2, 2.0))
            html = await page.content()
            try:
                body_text = await page.inner_text('body')
            except Exception:
                body_text = ''
            conteudo = html + '\n' + body_text
        except Exception:
            continue

        # Nome (só na home)
        if pag == url_base and not dados['nome']:
            try:
                t = await page.title()
                dados['nome'] = (t or '')[:100] or None
            except Exception:
                pass

        # WhatsApp — wa.me links (maior confiabilidade)
        if not dados['whatsapp']:
            for pat in _PAT_WA:
                m = pat.search(conteudo)
                if m:
                    num = ''.join(m.groups())
                    w = _tel_para_wa(num)
                    if w:
                        dados['whatsapp'] = w
                        break

        # Telefone
        if not dados['telefone']:
            for pat in _PAT_TEL:
                for m in pat.finditer(conteudo):
                    v = _valida_telefone(''.join(m.groups()))
                    if v:
                        dados['telefone'] = v
                        break
                if dados['telefone']:
                    break

        # Email
        if not dados['email']:
            for e in _PAT_EMAIL.findall(conteudo):
                e = e.lower()
                if not any(x in e for x in _EMAILS_INVALIDOS):
                    dados['email'] = e
                    break

        # CNPJ
        if not dados['cnpj']:
            for raw in _PAT_CNPJ.findall(conteudo):
                v = _valida_cnpj(raw)
                if v:
                    dados['cnpj'] = v
                    break

        # Para de navegar se já temos o suficiente
        if dados['whatsapp'] and dados['cnpj']:
            break

    # Celular sem wa.me → tenta usar como WhatsApp
    if not dados['whatsapp'] and dados['telefone']:
        dados['whatsapp'] = _tel_para_wa(dados['telefone'])

    return dados


# =============================================================================
# CONSULTA CNPJ (ReceitaWS)
# =============================================================================

def _consultar_cnpj_sync(cnpj: str) -> dict | None:
    """Consulta síncrona à ReceitaWS (rate limit: 21s entre chamadas)."""
    global _ultimo_cnpj_ts
    try:
        import requests
        espera = CNPJ_API_DELAY - (time.time() - _ultimo_cnpj_ts)
        if espera > 0:
            time.sleep(espera)

        url = CNPJ_API_URL.format(cnpj=cnpj)
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, timeout=10, headers=headers)
        _ultimo_cnpj_ts = time.time()

        if r.status_code != 200:
            return None
        d = r.json()
        situacao = d.get('situacao', '').upper()
        if d.get('status') == 'ERROR' or situacao != 'ATIVA':
            return None

        atividades = d.get('atividade_principal', [])
        cnae_cod = atividades[0].get('code', '')[:2] if atividades else ''
        cnae_txt = atividades[0].get('text', '') if atividades else ''

        tel = _valida_telefone(d.get('telefone', ''))
        logr = d.get('logradouro', '')
        num = d.get('numero', '')
        return {
            'razao_social': d.get('nome', ''),
            'nome_fantasia': d.get('fantasia') or d.get('nome', ''),
            'segmento': cnae_txt,
            'cnae_codigo': cnae_cod,
            'porte': d.get('porte', ''),
            'cidade': d.get('municipio', ''),
            'estado': d.get('uf', ''),
            'endereco': f"{logr} {num}".strip(),
            'telefone': tel,
            'whatsapp': _tel_para_wa(tel) if tel else None,
            'email': (d.get('email') or '').lower() or None,
        }
    except Exception:
        return None


# =============================================================================
# CICLO PROSPECÇÃO COMPLETA
# =============================================================================

async def ciclo_busca():
    """
    Prospecção completa a cada chamada:
    1. Busca Bing/DuckDuckGo com termo aleatório
    2. Visita home + /contato → extrai WA/tel/email/CNPJ
    3. Se achou CNPJ → consulta ReceitaWS
    4. Calcula score e salva leads com contato no banco
    """
    from buscador import Buscador

    buscador = Buscador()
    try:
        await buscador.iniciar()

        termo = random.choice(TERMOS_BUSCA)
        print(
            f"[WA/Pili {_ts()}] ℹ Prospecção: '{termo}'",
            flush=True
        )

        resultados = await buscador.buscar_leads(
            termo, max_resultados=15
        )
        print(
            f"[WA/Pili {_ts()}] ℹ "
            f"{len(resultados)} sites para enriquecer",
            flush=True
        )

        salvos = 0
        for r in resultados:
            url = r.get('url', '')
            if not url:
                continue

            # 1. Visita site (timeout 30s)
            try:
                site = await asyncio.wait_for(
                    _extrair_site(buscador.page, url), timeout=30)
            except asyncio.TimeoutError:
                print(
                    f"  [DBG] timeout extraindo: {url[:55]}",
                    flush=True)
                site = {}
            except Exception as e:
                print(
                    f"  [DBG] erro extraindo {url[:40]}: "
                    f"{type(e).__name__}",
                    flush=True)
                site = {}

            wa = site.get('whatsapp')
            tel = site.get('telefone')
            email = site.get('email')
            print(
                f"  [DBG] {url[:55]}\n"
                f"        wa={wa} tel={tel} email={email} "
                f"cnpj={site.get('cnpj')}",
                flush=True
            )

            # 2. Monta lead base
            tel_busca = r['telefones'][0] if r.get('telefones') else None
            lead = {
                'nome_fantasia': (
                    site.get('nome') or r.get('titulo', '')
                )[:100],
                'website': url,
                'whatsapp': wa,
                'telefone': tel or tel_busca,
                'email': email,
                'cnpj': site.get('cnpj'),
                'fonte': r.get('fonte', 'bing'),
                'score': r.get('relevancia', 0),
            }

            # 3. Enriquece CNPJ via ReceitaWS
            if lead['cnpj']:
                try:
                    dados_rf = await asyncio.to_thread(
                        _consultar_cnpj_sync, lead['cnpj']
                    )
                    if dados_rf:
                        campos = (
                            'razao_social', 'segmento', 'cnae_codigo',
                            'porte', 'cidade', 'estado', 'endereco',
                        )
                        for campo in campos:
                            if not lead.get(campo):
                                lead[campo] = dados_rf.get(campo)
                        if not lead['telefone']:
                            lead['telefone'] = dados_rf.get('telefone')
                        if not lead['whatsapp']:
                            lead['whatsapp'] = dados_rf.get('whatsapp')
                        if not lead['email']:
                            lead['email'] = dados_rf.get('email')
                        nf = lead.get('nome_fantasia', '')
                        if not nf or len(nf) < 4:
                            lead['nome_fantasia'] = dados_rf.get(
                                'nome_fantasia', ''
                            )
                except Exception as e:
                    print(
                        f"  [DBG] erro CNPJ {lead['cnpj']}: "
                        f"{type(e).__name__}: {e}",
                        flush=True)

            # 4. Descarta sem contato ou já existente
            numero = lead.get('whatsapp') or lead.get('telefone')
            if not numero:
                print(
                    f"  [DBG] descartado (sem tel/WA): "
                    f"{lead['nome_fantasia'][:50]}",
                    flush=True
                )
                continue
            if telefone_existe(numero):
                print(
                    f"  [DBG] descartado (já existe no DB): "
                    f"{lead['nome_fantasia'][:50]}",
                    flush=True
                )
                continue

            # 5. Score final e salva
            lead['score'] = _calcular_score(lead)

            try:
                salvar_empresa(lead)
                salvos += 1
                tipo = 'WA' if lead.get('whatsapp') else 'TEL'
                nf = lead['nome_fantasia'][:45]
                print(
                    f"[WA/Pili {_ts()}] ✓ Lead [{tipo}] "
                    f"score={lead['score']} | {nf}",
                    flush=True
                )
            except Exception as e:
                print(
                    f"[WA/Pili {_ts()}] ✗ Erro salvando "
                    f"lead: {type(e).__name__}: {e}",
                    flush=True)

            await asyncio.sleep(random.uniform(2, 4))

        print(
            f"[WA/Pili {_ts()}] ✓ Prospecção: "
            f"{len(resultados)} sites → {salvos} leads salvos",
            flush=True
        )
        log_acao('info', f"Prospecção '{termo}': {salvos} leads")

    except Exception as e:
        print(
            f"[WA/Pili {_ts()}] ⚠ Erro na prospecção: {e}",
            flush=True
        )
    finally:
        await buscador.fechar()


# =============================================================================
# CICLO ENVIO
# =============================================================================

async def ciclo_envio(
    bot: WhatsAppBot, gerador: GeradorMensagens, limite: int = 10
):
    """Envia mensagem inicial para leads ainda não contactados."""
    leads = get_empresas_sem_contato(limite=limite)
    if not leads:
        print(
            f"[WA/Pili {_ts()}] ℹ Sem leads novos para contatar",
            flush=True
        )
        return

    print(
        f"[WA/Pili {_ts()}] ℹ {len(leads)} lead(s) para contatar",
        flush=True
    )
    enviadas = falhas = 0

    for lead in leads:
        pode, motivo = bot.pode_enviar()
        if not pode:
            print(f"[WA/Pili {_ts()}] ⚠ {motivo}", flush=True)
            break

        numero = lead.get('whatsapp') or lead.get('telefone')
        if not numero:
            continue

        nome = lead.get('nome_fantasia', 'empresa')
        mensagem = gerador.gerar_inicial(lead)

        seg = lead.get('segmento', '')
        print(
            f"[WA/Pili {_ts()}] ℹ → {nome[:40]} "
            f"(score {lead.get('score', 0)} | {seg})",
            flush=True
        )
        try:
            ok = await asyncio.wait_for(
                bot.enviar_mensagem(
                    numero, mensagem, nome_lead=nome),
                timeout=45)
        except asyncio.TimeoutError:
            print(
                f"[WA/Pili {_ts()}] ⚠ Timeout enviando "
                f"para {nome[:35]}",
                flush=True)
            ok = False
        except Exception as e:
            print(
                f"[WA/Pili {_ts()}] ✗ Erro enviando "
                f"para {nome[:35]}: {e}",
                flush=True)
            ok = False

        if ok:
            registrar_interacao(
                lead['id'], None, 'whatsapp', 'inicial', mensagem
            )
            atualizar_status_empresa(lead['id'], 'contactada')
            incrementar_contagem('whatsapp_enviados')
            enviadas += 1
        else:
            falhas += 1

        await bot.delay_entre_mensagens()

    print(
        f"[WA/Pili {_ts()}] ✓ Envio: {enviadas} ok, {falhas} falhas",
        flush=True
    )


# =============================================================================
# CICLO FOLLOW-UP
# =============================================================================

async def ciclo_followup(bot: WhatsAppBot, gerador: GeradorMensagens):
    """Follow-up 1 (4 dias) e Follow-up 2 (10 dias) sem resposta."""
    for n_fu, dias in [(1, FOLLOWUP1_DIAS), (2, FOLLOWUP2_DIAS)]:
        tipo = f'followup{n_fu}'
        leads = get_empresas_para_followup(dias, tipo)

        for lead in leads[:3]:
            numero = lead.get('whatsapp') or lead.get('telefone')
            if not numero:
                continue

            pode, _ = bot.pode_enviar()
            if not pode:
                break

            msg = gerador.gerar_followup(lead, n_fu)
            if not msg:
                continue

            nome = lead.get('nome_fantasia', 'empresa')
            print(
                f"[WA/Pili {_ts()}] ℹ Follow-up {n_fu} → {nome[:40]}",
                flush=True
            )
            try:
                ok = await asyncio.wait_for(
                    bot.enviar_mensagem(
                        numero, msg, nome_lead=nome),
                    timeout=45)
            except asyncio.TimeoutError:
                print(
                    f"[WA/Pili {_ts()}] ⚠ Timeout "
                    f"follow-up {nome[:35]}",
                    flush=True)
                ok = False
            except Exception as e:
                print(
                    f"[WA/Pili {_ts()}] ✗ Erro "
                    f"follow-up {nome[:35]}: {e}",
                    flush=True)
                ok = False

            if ok:
                registrar_interacao(
                    lead['id'], None, 'whatsapp', tipo, msg
                )
                incrementar_contagem('whatsapp_enviados')
                log_acao('info', f"Follow-up {n_fu}: {nome}")

            await bot.delay_entre_mensagens()


# =============================================================================
# CICLO RESPOSTAS
# =============================================================================

async def ciclo_respostas(bot: WhatsAppBot, gerador: GeradorMensagens):
    """Verifica conversas ativas e responde com IA."""
    contactadas = get_empresas_contactadas(limite=20)
    numeros = [e['whatsapp'] for e in contactadas if e.get('whatsapp')]

    if not numeros:
        print(
            f"[WA/Pili {_ts()}] ℹ "
            "Nenhuma empresa contactada para verificar",
            flush=True
        )
        return

    print(
        f"[WA/Pili {_ts()}] ℹ "
        f"Verificando {len(numeros)} conversa(s)...",
        flush=True
    )
    com_resposta = await bot.verificar_respostas_pendentes(numeros)

    if not com_resposta:
        return

    print(
        f"[WA/Pili {_ts()}] ✓ "
        f"{len(com_resposta)} resposta(s) recebida(s)",
        flush=True
    )

    for info in com_resposta:
        numero = info.get('numero')
        empresa = get_empresa_por_whatsapp(numero)
        if not empresa:
            print(
                f"[WA/Pili {_ts()}] ⚠ Resposta de {numero}"
                " mas empresa não encontrada no DB",
                flush=True)
            continue

        estagio = get_estagio_conversa(empresa['id'])
        msg_lead = info.get('ultima_recebida', '')
        nome = empresa.get('nome_fantasia', numero)

        print(
            f"[WA/Pili {_ts()}] ℹ Respondendo {nome[:35]} "
            f"(estágio: {estagio})",
            flush=True
        )
        try:
            resposta, intencao = gerador.gerar_resposta(
                empresa, msg_lead, estagio=estagio
            )
        except Exception as e:
            print(
                f"[WA/Pili {_ts()}] ✗ Erro gerando resposta "
                f"para {nome[:35]}: {e}",
                flush=True)
            continue

        try:
            ok = await asyncio.wait_for(
                bot.responder_conversa(resposta), timeout=30)
        except asyncio.TimeoutError:
            print(
                f"[WA/Pili {_ts()}] ⚠ Timeout respondendo "
                f"{nome[:35]}",
                flush=True)
            ok = False
        except Exception as e:
            print(
                f"[WA/Pili {_ts()}] ✗ Erro respondendo "
                f"{nome[:35]}: {e}",
                flush=True)
            ok = False

        if ok:
            registrar_interacao(
                empresa['id'], None, 'whatsapp', 'resposta', resposta
            )
            nivel = intencao['nivel']
            if nivel in ('demo', 'agendamento'):
                marcar_demo_proposto(empresa['id'])
                atualizar_status_empresa(empresa['id'], 'respondeu')
                print(
                    f"[WA/Pili {_ts()}] ✓ Demo proposta: {nome[:35]}",
                    flush=True
                )
            elif nivel == 'confirmacao':
                marcar_demo_confirmado(empresa['id'])
                atualizar_status_empresa(empresa['id'], 'convertido')
                print(
                    f"[WA/Pili {_ts()}] ✓✓ DEMO CONFIRMADA: {nome[:35]}",
                    flush=True
                )
            elif nivel == 'baixa':
                atualizar_status_empresa(empresa['id'], 'encerrado')
            log_acao('info', f"Resposta: {nome} | {msg_lead[:50]}")

        await asyncio.sleep(5)


# =============================================================================
# MAIN LOOP
# =============================================================================

async def main():
    print(
        f"[WA/Pili {_ts()}] ℹ === Bot Pili Equipamentos iniciando ===",
        flush=True
    )

    init_database()
    print(f"[WA/Pili {_ts()}] ℹ Banco inicializado", flush=True)

    bot = WhatsAppBot()
    gerador = GeradorMensagens()

    conectado = await bot.iniciar()
    if not conectado:
        print(
            f"[WA/Pili {_ts()}] ✗ WhatsApp não conectou. Encerrando.",
            flush=True
        )
        await bot.fechar()
        return

    print(
        f"[WA/Pili {_ts()}] ✓ WhatsApp conectado! Iniciando...",
        flush=True
    )
    log_acao('info', 'Bot Pili Equipamentos iniciado')
    ciclo_num = 0

    try:
        while True:
            agora = _agora()
            ciclo_num += 1
            hoje = bot.msgs_enviadas_hoje
            sessao = bot.msgs_enviadas_sessao
            comercial = _horario_comercial(agora)
            print(
                f"[WA/Pili {_ts()}] ━━━ Ciclo #{ciclo_num} "
                f"| msgs hoje: {hoje} | sessão: {sessao} "
                f"| comercial: {'sim' if comercial else 'não'} ━━━",
                flush=True
            )

            # ── Prospecção 24/7 (a cada 3 ciclos) ──
            if ciclo_num % 3 == 1:
                try:
                    await asyncio.wait_for(
                        ciclo_busca(), timeout=300)
                except asyncio.TimeoutError:
                    print(
                        f"[WA/Pili {_ts()}] ⚠ "
                        "ciclo_busca timeout (5 min)",
                        flush=True)
                except Exception as e:
                    print(
                        f"[WA/Pili {_ts()}] ✗ "
                        f"Erro ciclo_busca: {e}",
                        flush=True)

            # ── Mensagens só em horário comercial (seg-sex 8h-18h) ──
            if comercial:
                try:
                    await asyncio.wait_for(
                        ciclo_respostas(bot, gerador), timeout=120)
                except asyncio.TimeoutError:
                    print(
                        f"[WA/Pili {_ts()}] ⚠ "
                        "ciclo_respostas timeout (2 min)",
                        flush=True)
                except Exception as e:
                    print(
                        f"[WA/Pili {_ts()}] ✗ "
                        f"Erro ciclo_respostas: {e}",
                        flush=True)

                try:
                    await asyncio.wait_for(
                        ciclo_envio(bot, gerador, limite=10),
                        timeout=180)
                except asyncio.TimeoutError:
                    print(
                        f"[WA/Pili {_ts()}] ⚠ "
                        "ciclo_envio timeout (3 min)",
                        flush=True)
                except Exception as e:
                    print(
                        f"[WA/Pili {_ts()}] ✗ "
                        f"Erro ciclo_envio: {e}",
                        flush=True)

                try:
                    await asyncio.wait_for(
                        ciclo_followup(bot, gerador), timeout=120)
                except asyncio.TimeoutError:
                    print(
                        f"[WA/Pili {_ts()}] ⚠ "
                        "ciclo_followup timeout (2 min)",
                        flush=True)
                except Exception as e:
                    print(
                        f"[WA/Pili {_ts()}] ✗ "
                        f"Erro ciclo_followup: {e}",
                        flush=True)
            else:
                print(
                    f"[WA/Pili {_ts()}] ℹ Fora do horário comercial "
                    f"({HORARIO_INICIO}h-{HORARIO_FIM}h seg-sex) "
                    "— apenas prospecção",
                    flush=True
                )

            print(
                f"[WA/Pili {_ts()}] ✓ Ciclo #{ciclo_num} completo. "
                "Próximo em 1 min...",
                flush=True
            )
            await asyncio.sleep(60)

    except (asyncio.CancelledError, KeyboardInterrupt):
        print(
            f"[WA/Pili {_ts()}] ℹ Bot encerrado pelo operador",
            flush=True
        )
    except Exception as e:
        print(
            f"[WA/Pili {_ts()}] ✗ ERRO FATAL no main loop: {e}",
            flush=True)
        log_acao('erro', f'Erro fatal: {e}')
    finally:
        log_acao('info', 'Bot Pili Equipamentos encerrado')
        await bot.fechar()


if __name__ == '__main__':
    asyncio.run(main())
