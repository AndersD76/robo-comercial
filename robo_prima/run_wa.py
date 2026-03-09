# -*- coding: utf-8 -*-
"""
Runner standalone do bot WhatsApp — PrismaBiz
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
    get_empresas_para_followup, salvar_contato, get_decisor_empresa,
    decisor_ja_existe,
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
    APOLLO_HABILITADO,
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
    '51', '52', '53', '54', '55',
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
    '/contato', '/contact',
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
        r'[Ww]hats[Aa]pp[:\s\xa0]*\(?(\d{2})\)?\s*(\d{4,5})[-.\s]?(\d{4})'
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
                pag, timeout=10000, wait_until='domcontentloaded'
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
        if dados['whatsapp'] or (dados['telefone'] and dados['email']):
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
        # QSA: socios/socias = decisores em PMEs
        socios = []
        for s in (d.get('qsa', []) or []):
            nome_s = s.get('nome', '') or s.get('nome_socio', '')
            qual_s = s.get('qual', '') or s.get('qualificacao_socio', '')
            if nome_s:
                socios.append({'nome': nome_s, 'cargo': qual_s})
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
            'socios': socios,
        }
    except Exception:
        return None


# =============================================================================
# SALVAR DECISOR
# =============================================================================

def _salvar_decisor(empresa_id, nome, cargo='', email=None, telefone=None):
    """Salva contato decisor (flag decisor=1) evitando duplicatas."""
    if not empresa_id or not nome or not str(nome).strip():
        return
    nome = str(nome).strip()[:200]
    if decisor_ja_existe(empresa_id, nome):
        return
    try:
        salvar_contato(empresa_id, {
            'nome': nome,
            'cargo': (cargo or '')[:200],
            'email': email,
            'telefone': telefone,
            'decisor': 1,
        })
        print(
            f'  [Decisor] {nome[:40]} ({(cargo or "")[:30]}) '
            f'→ empresa #{empresa_id}',
            flush=True
        )
    except Exception as e:
        print(f'  [ERRO] _salvar_decisor: {e}', flush=True)


# =============================================================================
# CICLO PROSPECÇÃO COMPLETA
# =============================================================================

async def ciclo_busca(buscador_ext=None):
    """
    Prospecção completa a cada chamada:
    1. Busca Bing/DuckDuckGo com termo aleatório
    2. Visita home + /contato → extrai WA/tel/email/CNPJ
    3. Se achou CNPJ → consulta ReceitaWS
    4. Calcula score e salva leads com contato no banco
    """
    from buscador import Buscador

    proprio = buscador_ext is None
    buscador = buscador_ext or Buscador()
    try:
        if proprio:
            await buscador.iniciar()

        termo = random.choice(TERMOS_BUSCA)
        print(
            f"[WA/Prisma {_ts()}] ℹ Prospecção: '{termo}'",
            flush=True
        )

        # === Apollo.io: decisores diretos (executado 1x a cada 3 ciclos) ===
        if APOLLO_HABILITADO:
            try:
                apollo_leads = await buscador.buscar_apollo(max_resultados=20)
                for ar in apollo_leads:
                    empresa_nome = ar.get('titulo', '')
                    website = ar.get('url', '')
                    if not empresa_nome:
                        continue
                    lead_ap = {
                        'nome_fantasia': empresa_nome[:100],
                        'website': website,
                        'whatsapp': ar.get('decisor_telefone') and _tel_para_wa(ar['decisor_telefone']),
                        'telefone': ar.get('decisor_telefone'),
                        'email': ar.get('decisor_email'),
                        'fonte': 'apollo',
                        'score': 60,
                    }
                    numero_ap = lead_ap.get('whatsapp') or lead_ap.get('telefone')
                    if numero_ap and not telefone_existe(numero_ap):
                        empresa_id_ap = salvar_empresa(lead_ap)
                        if empresa_id_ap:
                            _salvar_decisor(
                                empresa_id_ap,
                                ar.get('decisor_nome', ''),
                                ar.get('decisor_cargo', ''),
                                ar.get('decisor_email'),
                                ar.get('decisor_telefone'),
                            )
            except Exception as e:
                print(f'[WA/Prisma {_ts()}] ⚠ Apollo: {e}', flush=True)

        resultados = await buscador.buscar_leads(termo, max_resultados=8)
        print(
            f"[WA/Prisma {_ts()}] ℹ "
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

            # 3. Enriquece CNPJ via ReceitaWS (pula se já tem contato — evita delay 21s)
            if lead['cnpj'] and not (lead.get('whatsapp') or lead.get('telefone')):
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
                        # Socios QSA = decisores em PMEs
                        if dados_rf.get('socios'):
                            lead['_socios'] = dados_rf['socios']
                except Exception as e:
                    print(
                        f"  [DBG] erro CNPJ {lead['cnpj']}: "
                        f"{type(e).__name__}: {e}",
                        flush=True)

            # 4. Descarta sem contato ou já existente
            numero = lead.get('whatsapp') or lead.get('telefone')
            if not numero:
                print(
                    f"  [DBG] descartado (sem telefone/WA): "
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
                empresa_id = salvar_empresa(lead)
                salvos += 1
                tipo = 'WA' if lead.get('whatsapp') else 'TEL'
                nf = lead['nome_fantasia'][:45]
                print(
                    f"[WA/Prisma {_ts()}] ✓ Lead [{tipo}] "
                    f"score={lead['score']} | {nf}",
                    flush=True
                )

                # Salva decisor se disponivel
                if empresa_id:
                    # Fonte Apollo: decisor direto
                    if r.get('decisor_nome'):
                        _salvar_decisor(empresa_id, r.get('decisor_nome'),
                                        r.get('decisor_cargo', ''),
                                        r.get('decisor_email'),
                                        r.get('decisor_telefone'))
                    # Fonte ReceitaWS: socios QSA
                    for socio in lead.get('_socios', []):
                        _salvar_decisor(empresa_id, socio['nome'],
                                        socio.get('cargo', ''), None, None)
                    # Se ainda sem QSA e tem nome → busca CNPJ por nome → QSA
                    if not lead.get('_socios') and not r.get('decisor_nome'):
                        nf = lead.get('nome_fantasia', '')
                        if nf and len(nf) > 5:
                            try:
                                cnpj_extra = await buscador.buscar_cnpj_por_nome(nf)
                                if cnpj_extra:
                                    dados_qsa = await asyncio.to_thread(
                                        _consultar_cnpj_sync, cnpj_extra
                                    )
                                    if dados_qsa:
                                        for campo in (
                                            'segmento', 'cnae_codigo',
                                            'porte', 'cidade', 'estado',
                                        ):
                                            if not lead.get(campo):
                                                lead[campo] = dados_qsa.get(campo)
                                        for socio in (dados_qsa.get('socios') or []):
                                            _salvar_decisor(
                                                empresa_id,
                                                socio['nome'],
                                                socio.get('cargo', ''),
                                                None, None,
                                            )
                            except Exception:
                                pass
                    # Hunter.io: emails com cargo
                    if lead.get('website') and empresa_id:
                        dominio = lead.get('website', '').replace('https://', '').replace('http://', '').split('/')[0]
                        try:
                            hunter = await buscador.buscar_hunter_email(dominio)
                            for h in hunter:
                                _salvar_decisor(empresa_id, h.get('nome', ''),
                                                h.get('cargo', ''), h.get('email'), None)
                        except Exception:
                            pass
            except Exception as e:
                print(
                    f"[WA/Prisma {_ts()}] ✗ Erro salvando "
                    f"lead: {type(e).__name__}: {e}",
                    flush=True)

            await asyncio.sleep(random.uniform(2, 4))

        print(
            f"[WA/Prisma {_ts()}] ✓ Prospecção: "
            f"{len(resultados)} sites → {salvos} leads salvos",
            flush=True
        )
        log_acao('info', f"Prospecção '{termo}': {salvos} leads")

    except Exception as e:
        print(
            f"[WA/Prisma {_ts()}] ⚠ Erro na prospecção: {e}",
            flush=True
        )
    finally:
        if proprio:
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
            f"[WA/Prisma {_ts()}] ℹ Sem leads novos para contatar",
            flush=True
        )
        return

    print(
        f"[WA/Prisma {_ts()}] ℹ {len(leads)} lead(s) para contatar",
        flush=True
    )
    enviadas = falhas = 0

    for lead in leads:
        pode, motivo = bot.pode_enviar()
        if not pode:
            print(f"[WA/Prisma {_ts()}] ⚠ {motivo}", flush=True)
            break

        numero = lead.get('whatsapp') or lead.get('telefone')
        if not numero:
            continue

        nome = lead.get('nome_fantasia', 'empresa')
        # Injeta decisor no lead para personalizar mensagem
        decisor = get_decisor_empresa(lead.get('id'))
        if decisor:
            lead['decisor_nome'] = decisor.get('nome', '')
            lead['decisor_cargo'] = decisor.get('cargo', '')
        mensagem = gerador.gerar_inicial(lead)

        seg = lead.get('segmento') or ''
        decisor_log = lead.get('decisor_nome', '')
        decisor_info = f' | decisor: {decisor_log.split()[0]}' if decisor_log else ''
        print(
            f"[WA/Prisma {_ts()}] ℹ → {nome[:40]} "
            f"(score {lead.get('score', 0)} | {seg or 'sem segmento'}{decisor_info})",
            flush=True
        )
        try:
            ok = await asyncio.wait_for(
                bot.enviar_mensagem(
                    numero, mensagem, nome_lead=nome),
                timeout=45)
        except asyncio.TimeoutError:
            print(
                f"[WA/Prisma {_ts()}] ⚠ Timeout enviando "
                f"para {nome[:35]}",
                flush=True)
            ok = False
        except Exception as e:
            print(
                f"[WA/Prisma {_ts()}] ✗ Erro enviando "
                f"para {nome[:35]}: {e}",
                flush=True)
            ok = False

        if ok:
            registrar_interacao(
                lead['id'], None, 'whatsapp', 'inicial', mensagem
            )
            atualizar_status_empresa(lead['id'], 'contactada')
            # registrar_interacao já chama incrementar_contagem
            enviadas += 1
            await bot.delay_entre_mensagens()
        else:
            atualizar_status_empresa(lead['id'], 'sem_whatsapp')
            falhas += 1
            await asyncio.sleep(random.uniform(2, 5))

    print(
        f"[WA/Prisma {_ts()}] ✓ Envio: {enviadas} ok, {falhas} falhas",
        flush=True
    )


# =============================================================================
# CICLO FOLLOW-UP
# =============================================================================

async def ciclo_followup(bot: WhatsAppBot, gerador: GeradorMensagens):
    """Follow-up 1 (3 dias) e Follow-up 2 (7 dias) sem resposta."""
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
                f"[WA/Prisma {_ts()}] ℹ Follow-up {n_fu} → {nome[:40]}",
                flush=True
            )
            try:
                ok = await asyncio.wait_for(
                    bot.enviar_mensagem(
                        numero, msg, nome_lead=nome),
                    timeout=45)
            except asyncio.TimeoutError:
                print(
                    f"[WA/Prisma {_ts()}] ⚠ Timeout "
                    f"follow-up {nome[:35]}",
                    flush=True)
                ok = False
            except Exception as e:
                print(
                    f"[WA/Prisma {_ts()}] ✗ Erro "
                    f"follow-up {nome[:35]}: {e}",
                    flush=True)
                ok = False

            if ok:
                registrar_interacao(
                    lead['id'], None, 'whatsapp', tipo, msg
                )
                # registrar_interacao já chama incrementar_contagem
                log_acao('info', f"Follow-up {n_fu}: {nome}")

            await bot.delay_entre_mensagens()


# =============================================================================
# DETECÇÃO DE ROBÔ / CHATBOT
# =============================================================================

_PADROES_ROBO = [
    # Menus numerados (1. Vendas 2. Suporte)
    r'(?:^|\n)\s*[1-9]\s*[-–.)]\s*\w',
    # Pede nome/CPF/CNPJ em formato bot
    r'(?:envie|informe|digite)\s+(?:seu\s+)?(?:nome|cpf|cnpj|email|e-mail)',
    # "escolha uma opção", "selecione", "digite o número"
    r'(?:escolha|selecione|digite)\s+(?:uma?\s+)?(?:op[cç][aã]o|n[uú]mero|opcao|numero)',
    # "Bem-vindo(a) à/ao" — saudação automatizada
    r'bem[- ]?vindo\(?a?\)?\s+(?:ao?|[àa])\s',
    # "Seja bem vindo" / "Seja muito bem vindo"
    r'seja\s+(?:muito\s+)?bem\s*vindo',
    # "agradece seu contato" / "agradecemos"
    r'agrade[cç](?:e|emos)\s+(?:seu|o)\s+contato',
    # "para falar com", "para atendimento"
    r'para\s+(?:falar|atendimento|suporte|vendas|financeiro)',
    # "horário de atendimento"
    r'hor[aá]rio\s+de\s+atendimento',
    # "Envie uma informação com no máximo"
    r'envie\s+uma?\s+informa[cç][aã]o',
    # "não entendi", "não compreendi" (bot não entendeu)
    r'n[aã]o\s+(?:entendi|compreendi|identifiquei)',
    # "fora do horário"
    r'fora\s+do\s+hor[aá]rio',
    # "aguarde" + "atendente"
    r'aguarde.*atendente|atendente.*aguarde',
    # "como podemos ajudar" / "como posso ajudar" (saudação genérica)
    r'como\s+(?:podemos|posso)\s+(?:ajudar|te ajudar)',
    # "atendente do Pré Vendas" / "atendente virtual"
    r'atendente\s+(?:do|da|virtual)',
    # "somos especialist" (apresentação empresa auto)
    r'^ol[aá]!?\s+(?:bem[- ]?vindo|seja)',
    # "pré vendas online"
    r'pr[eé][- ]?vendas\s+online',
]
_RE_ROBO = [re.compile(p, re.IGNORECASE) for p in _PADROES_ROBO]


def _eh_resposta_robo(msg: str) -> bool:
    """Detecta se a mensagem parece ser de um chatbot/robô."""
    if not msg:
        return False
    msg = msg.strip()
    # Mensagem com menu numerado (>= 3 opções)
    linhas_menu = [l for l in msg.split('\n')
                   if re.match(r'^\s*[1-9]\s*[-–.)]\s*\w', l.strip())]
    if len(linhas_menu) >= 3:
        return True
    # Padrões regex
    for rx in _RE_ROBO:
        if rx.search(msg):
            return True
    return False


# =============================================================================
# CICLO RESPOSTAS
# =============================================================================

async def ciclo_respostas(bot: WhatsAppBot, gerador: GeradorMensagens):
    """Verifica conversas ativas e responde com IA."""
    contactadas = get_empresas_contactadas(limite=20)
    numeros = [e['whatsapp'] for e in contactadas if e.get('whatsapp')]

    if not numeros:
        print(
            f"[WA/Prisma {_ts()}] ℹ "
            "Nenhuma empresa contactada para verificar",
            flush=True
        )
        return

    print(
        f"[WA/Prisma {_ts()}] ℹ "
        f"Verificando {len(numeros)} conversa(s)...",
        flush=True
    )
    com_resposta = await bot.verificar_respostas_pendentes(numeros)

    if not com_resposta:
        return

    print(
        f"[WA/Prisma {_ts()}] ✓ "
        f"{len(com_resposta)} resposta(s) recebida(s)",
        flush=True
    )

    for info in com_resposta:
        numero = info.get('numero')
        empresa = get_empresa_por_whatsapp(numero)
        if not empresa:
            print(
                f"[WA/Prisma {_ts()}] ⚠ Resposta de {numero}"
                " mas empresa não encontrada no DB",
                flush=True)
            continue

        estagio = get_estagio_conversa(empresa['id'])
        msg_lead = info.get('ultima_recebida', '')
        todas_recebidas = info.get('msgs_recebidas', [])
        nome = empresa.get('nome_fantasia', numero)

        # Detecta robô: se TODAS as msgs recebidas são de robô, ignora.
        # Se pelo menos uma parece humana, responde normalmente.
        if todas_recebidas and all(
            _eh_resposta_robo(m) for m in todas_recebidas
        ):
            print(
                f"[WA/Prisma {_ts()}] ⏭ {nome[:35]} — "
                f"resposta de robô (ignorando)",
                flush=True)
            atualizar_status_empresa(empresa['id'], 'robo_wa')
            continue

        print(
            f"[WA/Prisma {_ts()}] ℹ Respondendo {nome[:35]} "
            f"(estágio: {estagio})",
            flush=True
        )
        try:
            resposta, intencao = gerador.gerar_resposta(
                empresa, msg_lead, estagio=estagio
            )
        except Exception as e:
            print(
                f"[WA/Prisma {_ts()}] ✗ Erro gerando resposta "
                f"para {nome[:35]}: {e}",
                flush=True)
            continue

        # Navega para a conversa correta antes de responder
        try:
            await bot.page.goto(
                f"https://web.whatsapp.com/send?phone={numero}",
                timeout=20000)
            await asyncio.sleep(random.uniform(3, 5))
        except Exception as e:
            print(
                f"[WA/Prisma {_ts()}] ⚠ Erro navegando para "
                f"{nome[:35]}: {e}",
                flush=True)
            continue

        try:
            ok = await asyncio.wait_for(
                bot.responder_conversa(resposta), timeout=30)
        except asyncio.TimeoutError:
            print(
                f"[WA/Prisma {_ts()}] ⚠ Timeout respondendo "
                f"{nome[:35]}",
                flush=True)
            ok = False
        except Exception as e:
            print(
                f"[WA/Prisma {_ts()}] ✗ Erro respondendo "
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
                    f"[WA/Prisma {_ts()}] ✓ Demo proposta: {nome[:35]}",
                    flush=True
                )
            elif nivel == 'confirmacao':
                marcar_demo_confirmado(empresa['id'])
                atualizar_status_empresa(empresa['id'], 'convertido')
                print(
                    f"[WA/Prisma {_ts()}] ✓✓ DEMO CONFIRMADA: {nome[:35]}",
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
        f"[WA/Prisma {_ts()}] ℹ === Bot PrismaBiz iniciando ===",
        flush=True
    )

    init_database()
    print(f"[WA/Prisma {_ts()}] ℹ Banco inicializado", flush=True)

    bot = WhatsAppBot()
    gerador = GeradorMensagens()

    conectado = await bot.iniciar()
    if not conectado:
        print(
            f"[WA/Prisma {_ts()}] ✗ WhatsApp não conectou. Encerrando.",
            flush=True
        )
        await bot.fechar()
        return

    print(
        f"[WA/Prisma {_ts()}] ✓ WhatsApp conectado! Iniciando...",
        flush=True
    )
    log_acao('info', 'Bot PrismaBiz iniciado')

    # Buscador persistente — evita criar Chromium novo a cada ciclo
    from buscador import Buscador
    buscador = Buscador()
    buscador_pronto = False

    ciclo_num = 0

    erros_seguidos = 0

    try:
        while True:
            agora = _agora()
            ciclo_num += 1
            hoje = bot.msgs_enviadas_hoje
            sessao = bot.msgs_enviadas_sessao
            comercial = _horario_comercial(agora)
            print(
                f"[WA/Prisma {_ts()}] ━━━ Ciclo #{ciclo_num} "
                f"| msgs hoje: {hoje} | sessão: {sessao} "
                f"| comercial: {'sim' if comercial else 'não'} ━━━",
                flush=True
            )

            erros_ciclo = 0

            # ── Prospecção 24/7 (a cada 3 ciclos) ──
            if ciclo_num % 3 == 1:
                try:
                    if not buscador_pronto:
                        await buscador.iniciar()
                        buscador_pronto = True
                    await asyncio.wait_for(
                        ciclo_busca(buscador), timeout=480)
                except asyncio.TimeoutError:
                    erros_ciclo += 1
                    print(
                        f"[WA/Prisma {_ts()}] ⚠ "
                        "ciclo_busca timeout (8 min)",
                        flush=True)
                except Exception as e:
                    erros_ciclo += 1
                    print(
                        f"[WA/Prisma {_ts()}] ✗ "
                        f"Erro ciclo_busca: {e}",
                        flush=True)

            # ── Mensagens só em horário comercial (seg-sex 8h-18h) ──
            if comercial:
                try:
                    await asyncio.wait_for(
                        ciclo_respostas(bot, gerador), timeout=300)
                except asyncio.TimeoutError:
                    erros_ciclo += 1
                    print(
                        f"[WA/Prisma {_ts()}] ⚠ "
                        "ciclo_respostas timeout (5 min)",
                        flush=True)
                except Exception as e:
                    erros_ciclo += 1
                    print(
                        f"[WA/Prisma {_ts()}] ✗ "
                        f"Erro ciclo_respostas: {e}",
                        flush=True)

                try:
                    await asyncio.wait_for(
                        ciclo_envio(bot, gerador, limite=10),
                        timeout=180)
                except asyncio.TimeoutError:
                    erros_ciclo += 1
                    print(
                        f"[WA/Prisma {_ts()}] ⚠ "
                        "ciclo_envio timeout (3 min)",
                        flush=True)
                except Exception as e:
                    erros_ciclo += 1
                    print(
                        f"[WA/Prisma {_ts()}] ✗ "
                        f"Erro ciclo_envio: {e}",
                        flush=True)

                try:
                    await asyncio.wait_for(
                        ciclo_followup(bot, gerador), timeout=120)
                except asyncio.TimeoutError:
                    erros_ciclo += 1
                    print(
                        f"[WA/Prisma {_ts()}] ⚠ "
                        "ciclo_followup timeout (2 min)",
                        flush=True)
                except Exception as e:
                    erros_ciclo += 1
                    print(
                        f"[WA/Prisma {_ts()}] ✗ "
                        f"Erro ciclo_followup: {e}",
                        flush=True)
            else:
                print(
                    f"[WA/Prisma {_ts()}] ℹ Fora do horário "
                    f"comercial ({HORARIO_INICIO}h-"
                    f"{HORARIO_FIM}h seg-sex) "
                    "— apenas prospecção",
                    flush=True
                )

            # Circuit breaker: pausa maior se muitos erros
            if erros_ciclo > 0:
                erros_seguidos += erros_ciclo
                if erros_seguidos >= 10:
                    pausa = 300
                    print(
                        f"[WA/Prisma {_ts()}] ⚠ "
                        f"{erros_seguidos} erros seguidos"
                        f" — pausa de {pausa}s",
                        flush=True)
                    await asyncio.sleep(pausa)
                    erros_seguidos = 0
            else:
                erros_seguidos = 0

            print(
                f"[WA/Prisma {_ts()}] ✓ Ciclo #{ciclo_num} "
                "completo.",
                flush=True
            )
            await asyncio.sleep(5)

    except (asyncio.CancelledError, KeyboardInterrupt):
        print(
            f"[WA/Prisma {_ts()}] ℹ Bot encerrado pelo operador",
            flush=True
        )
    except Exception as e:
        print(
            f"[WA/Prisma {_ts()}] ✗ ERRO FATAL no main loop: {e}",
            flush=True)
        log_acao('erro', f'Erro fatal: {e}')
    finally:
        log_acao('info', 'Bot PrismaBiz encerrado')
        if buscador_pronto:
            await buscador.fechar()
        await bot.fechar()


if __name__ == '__main__':
    asyncio.run(main())
