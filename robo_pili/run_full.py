# -*- coding: utf-8 -*-
"""
Máquina de Vendas — Bot Completo (Multi-tenant)
Prospecção + WhatsApp (envio, respostas, follow-up)
Lê toda configuração do banco — sem hardcode.

Uso: python run_full.py --schema emp_1
"""

import argparse
import asyncio
import json
import os
import random
import re
import sys
from datetime import datetime, timezone, timedelta

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ── Resolve paths ──────────────────────────────────────────────────────────────
_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

import psycopg2
import psycopg2.extras

_BRT = timezone(timedelta(hours=-3))


def _ts():
    return datetime.now(_BRT).strftime('%H:%M:%S')


def _agora():
    return datetime.now(_BRT)


def _fix_url(url):
    if url.startswith('psql://'):
        return 'postgresql://' + url[7:]
    if url.startswith('postgres://'):
        return 'postgresql://' + url[11:]
    return url


DATABASE_URL = _fix_url(os.environ.get('DATABASE_URL', ''))


# =============================================================================
# CARREGAR CONFIG DO BANCO
# =============================================================================

def carregar_config(schema: str) -> dict:
    """Carrega bot_config do schema do usuário."""
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        with conn.cursor() as c:
            c.execute('SET search_path TO %s, public', (schema,))
        conn.commit()
        with conn.cursor() as c:
            c.execute('SELECT * FROM bot_config ORDER BY id DESC LIMIT 1')
            row = c.fetchone()
        conn.close()
        if row:
            cfg = dict(row)
            for field in ('termos_busca', 'linkedin_cargos'):
                if isinstance(cfg.get(field), str):
                    try:
                        cfg[field] = json.loads(cfg[field])
                    except Exception:
                        cfg[field] = []
            return cfg
    except Exception as e:
        print(f'[run_full] Erro ao carregar config: {e}', flush=True)
    return {}


def _patch_modulos(schema: str, cfg: dict):
    """
    Patcha os módulos config e database para usar os valores do usuário.
    Deve ser chamado ANTES de importar WhatsApp/Mensagens/etc.
    """
    import config as _cfg

    # Schema do banco
    _cfg.DB_SCHEMA = schema

    # Termos de busca
    termos = cfg.get('termos_busca') or []
    if termos:
        _cfg.TERMOS_BUSCA = termos

    # Link de agendamento
    demo_link = os.environ.get('DEMO_CAL_LINK', '')
    if demo_link:
        _cfg.DEMO_CAL_LINK = demo_link

    # Mensagens customizadas do usuário
    empresa_nome = cfg.get('empresa_nome') or 'Nossa empresa'
    produto = cfg.get('descricao') or 'nossa solução'
    cal_link = _cfg.DEMO_CAL_LINK

    msg_inicial = cfg.get('msg_inicial')
    msg_followup1 = cfg.get('msg_followup1')
    msg_followup2 = cfg.get('msg_followup2')

    # Se o usuário não configurou mensagens, gera templates baseados na descrição
    if not msg_inicial:
        msg_inicial = (
            f"Olá! 👋 Tudo bem? Aqui é da {empresa_nome}.\n\n"
            f"Vi que você pode se interessar pela nossa solução: {produto[:120]}\n\n"
            f"Posso te apresentar mais detalhes? "
            f"Ou agenda uma conversa rápida: {cal_link}"
        )
    if not msg_followup1:
        msg_followup1 = (
            f"Oi! Passando para saber se teve chance de ver nossa mensagem sobre "
            f"{empresa_nome}. 😊\n\nSe quiser bater um papo: {cal_link}"
        )
    if not msg_followup2:
        msg_followup2 = (
            f"Olá! Última mensagem, prometo! 😅\n\n"
            f"Se algum dia precisar de {produto[:80]}, "
            f"pode contar com a {empresa_nome}.\n"
            f"Agende aqui: {cal_link}"
        )

    _cfg.MENSAGENS['inicial'] = [msg_inicial]
    _cfg.MENSAGENS['followup1'] = msg_followup1
    _cfg.MENSAGENS['followup2'] = msg_followup2

    # Limites diários e horário
    _cfg.MAX_WHATSAPP_DIA = int(cfg.get('wa_limite_dia') or 60)
    _cfg.HORARIO_INICIO = int(cfg.get('horario_inicio') or 8)
    _cfg.HORARIO_FIM = int(cfg.get('horario_fim') or 18)

    # Patcha database.DB_SCHEMA também
    import database as _db
    _db.DB_SCHEMA = schema

    print(f'[{schema}] Config carregado: {len(termos)} termos, limite {_cfg.MAX_WHATSAPP_DIA}/dia', flush=True)
    return _cfg


# =============================================================================
# SISTEMA DE IA DINÂMICO
# =============================================================================

class GeradorMensagensDinamico:
    """
    Gerador de mensagens que usa a descrição da empresa do usuário
    para personalizar o prompt da IA — em vez do hardcode da Pili.
    """

    def __init__(self, cfg: dict, schema: str):
        self.cfg = cfg
        self.schema = schema
        self.empresa_nome = cfg.get('empresa_nome') or 'Nossa empresa'
        self.descricao = cfg.get('descricao') or 'solução para empresas'
        self.demo_link = os.environ.get('DEMO_CAL_LINK', '')
        self.ai_client = None

        api_key = os.environ.get('ANTHROPIC_API_KEY', '')
        if api_key:
            try:
                import anthropic
                self.ai_client = anthropic.Anthropic(api_key=api_key)
                print(f'[{schema}] Claude AI conectado', flush=True)
            except Exception:
                pass
        if not self.ai_client:
            print(f'[{schema}] Sem IA — usando templates fixos', flush=True)

    def _system_prompt(self):
        return f"""Você é vendedor da empresa "{self.empresa_nome}".

SOBRE A EMPRESA/PRODUTO:
{self.descricao}

LINK DE AGENDAMENTO: {self.demo_link}

REGRAS PARA MENSAGENS WHATSAPP:
1. Máximo 6 linhas (WhatsApp é rápido)
2. Comece com "Olá!" ou "Oi!"
3. Mencione o segmento/atividade da empresa do lead
4. Se tiver link de agendamento, inclua-o
5. Use 1-2 emojis no máximo
6. Tom profissional mas amigável
7. Retorne APENAS a mensagem, sem aspas"""

    def gerar_inicial(self, lead):
        segmento = lead.get('segmento', 'empresa')
        nome_lead = lead.get('nome_fantasia', 'empresa')
        cidade = lead.get('cidade', '')
        estado = lead.get('estado', '')

        if self.ai_client:
            try:
                info = (f"Empresa: {nome_lead}\nSegmento: {segmento}\n"
                        f"Cidade: {cidade}, {estado}")
                r = self.ai_client.messages.create(
                    model='claude-haiku-4-5-20251001',
                    max_tokens=350,
                    system=self._system_prompt(),
                    messages=[{'role': 'user',
                                'content': f'Crie mensagem inicial de WhatsApp:\n{info}'}]
                )
                msg = r.content[0].text.strip().strip('"')
                if msg:
                    return msg
            except Exception as e:
                print(f'[{self.schema}] IA erro: {e}', flush=True)

        # Fallback template
        from config import MENSAGENS, DEMO_CAL_LINK
        tpl = random.choice(MENSAGENS['inicial']) if isinstance(MENSAGENS['inicial'], list) else MENSAGENS['inicial']
        return tpl.format(segmento=segmento, cal_link=DEMO_CAL_LINK,
                          empresa=self.empresa_nome)

    def gerar_resposta(self, lead, mensagem_recebida, historico=None, estagio='inicial'):
        intencao = self.detectar_intencao(mensagem_recebida, estagio)

        if self.ai_client:
            try:
                ctx = ''
                if historico:
                    for m in historico[-4:]:
                        quem = 'Lead' if m.get('tipo') == 'recebida' else 'Você'
                        ctx += f'{quem}: {m.get("mensagem", "")}\n'

                r = self.ai_client.messages.create(
                    model='claude-haiku-4-5-20251001',
                    max_tokens=300,
                    system=self._system_prompt(),
                    messages=[{'role': 'user',
                                'content': (
                                    f'Lead: {lead.get("nome_fantasia")}\n'
                                    f'Estágio: {estagio}\n'
                                    f'Intenção detectada: {intencao["nivel"]}\n'
                                    f'Histórico:\n{ctx}\n'
                                    f'Última mensagem do lead: {mensagem_recebida}\n\n'
                                    'Gere uma resposta adequada.'
                                )}]
                )
                msg = r.content[0].text.strip().strip('"')
                if msg:
                    return msg, intencao
            except Exception as e:
                print(f'[{self.schema}] IA resp erro: {e}', flush=True)

        return self._resposta_fallback(intencao, estagio), intencao

    def gerar_followup(self, lead, numero_followup):
        from config import MENSAGENS, DEMO_CAL_LINK
        key = f'followup{numero_followup}'
        tpl = MENSAGENS.get(key, '')
        if isinstance(tpl, list):
            tpl = random.choice(tpl)
        return tpl.format(
            cal_link=DEMO_CAL_LINK,
            empresa=self.empresa_nome,
            segmento=lead.get('segmento', 'empresa')
        )

    def detectar_intencao(self, msg, estagio='inicial'):
        msg_lower = (msg or '').lower()
        if any(w in msg_lower for w in ['sim', 'quero', 'interesse', 'pode', 'manda', 'envia', 'quero ver']):
            nivel = 'alta'
        elif any(w in msg_lower for w in ['agendar', 'reunião', 'demo', 'demonstração', 'visita']):
            nivel = 'demo'
        elif any(w in msg_lower for w in ['confirmad', 'marcad', 'ok', 'certo', 'às ', 'as ']):
            nivel = 'confirmacao'
        elif any(w in msg_lower for w in ['não', 'nao', 'obrigado', 'descadastrar', 'parar', 'remove']):
            nivel = 'baixa'
        else:
            nivel = 'media'
        return {'nivel': nivel, 'msg_original': msg}

    def _resposta_fallback(self, intencao, estagio):
        from config import MENSAGENS, DEMO_CAL_LINK
        nivel = intencao.get('nivel', 'media')
        if nivel in ('demo', 'agendamento'):
            msg = MENSAGENS.get('demo_proposta', '')
        elif nivel == 'confirmacao':
            msg = MENSAGENS.get('demo_confirmada', '')
        elif nivel == 'alta':
            msg = MENSAGENS.get('interesse', '')
        else:
            msg = f'Obrigado pelo contato! Qualquer dúvida é só chamar. Agende aqui: {DEMO_CAL_LINK}'
        if isinstance(msg, list):
            msg = random.choice(msg)
        return msg.format(cal_link=DEMO_CAL_LINK, empresa=self.empresa_nome)


# =============================================================================
# MAIN LOOP
# =============================================================================

async def main(schema: str):
    print(f'\n{"="*60}', flush=True)
    print(f'[MáquinaVendas] Bot completo — schema: {schema}', flush=True)
    print(f'{"="*60}\n', flush=True)

    if not DATABASE_URL:
        print('ERRO: DATABASE_URL não configurado', flush=True)
        return

    # 1. Carrega config do banco
    cfg = carregar_config(schema)
    if not cfg:
        print(f'[{schema}] AVISO: Nenhuma config encontrada. Configure em /configurar', flush=True)

    # 2. Patcha módulos com valores do usuário
    _cfg = _patch_modulos(schema, cfg)

    # 3. Importa módulos que dependem de config (após patch)
    from database import (
        init_database, get_empresas_sem_contato, registrar_interacao,
        atualizar_status_empresa, incrementar_contagem, log_acao,
        get_empresas_contactadas, get_estagio_conversa,
        marcar_demo_proposto, marcar_demo_confirmado,
        get_empresa_por_whatsapp, get_empresas_para_followup,
    )
    import database as _db
    _db.DB_SCHEMA = schema  # garante

    from buscador import Buscador
    from whatsapp import WhatsAppBot

    # 4. Inicializa banco
    try:
        init_database()
    except Exception as e:
        print(f'[{schema}] Erro init_database: {e}', flush=True)

    # 5. Gerador de mensagens dinâmico
    gerador = GeradorMensagensDinamico(cfg, schema)

    # 6. Inicia WhatsApp
    bot = WhatsAppBot()
    conectado = await bot.iniciar()
    if not conectado:
        print(f'[{schema}] ✗ WhatsApp não conectou. Encerrando.', flush=True)
        await bot.fechar()
        return

    print(f'[{schema}] ✓ WhatsApp conectado!', flush=True)
    log_acao('info', f'[{schema}] Bot iniciado')

    # 7. Buscador
    from buscador import Buscador
    buscador = Buscador()
    buscador_pronto = False
    ciclo_num = 0

    def _horario_comercial():
        agora = _agora()
        if agora.weekday() not in _cfg.DIAS_ATIVOS:
            return False
        return _cfg.HORARIO_INICIO <= agora.hour < _cfg.HORARIO_FIM

    try:
        while True:
            ciclo_num += 1
            comercial = _horario_comercial()

            msgs_hoje = bot.msgs_enviadas_hoje if hasattr(bot, 'msgs_enviadas_hoje') else 0
            print(f'\n[{schema} {_ts()}] ━━━ Ciclo #{ciclo_num} | msgs hoje: {msgs_hoje} | comercial: {"sim" if comercial else "não"} ━━━', flush=True)

            # ── Prospecção (a cada 3 ciclos, 24/7) ──
            if ciclo_num % 3 == 1:
                try:
                    if not buscador_pronto:
                        await buscador.iniciar()
                        buscador_pronto = True
                    # Usa termos do usuário
                    from run_busca import ciclo_busca
                    await asyncio.wait_for(
                        ciclo_busca(schema, buscador, _cfg.TERMOS_BUSCA),
                        timeout=480
                    )
                except asyncio.TimeoutError:
                    print(f'[{schema} {_ts()}] ⚠ ciclo_busca timeout', flush=True)
                except Exception as e:
                    print(f'[{schema} {_ts()}] ✗ ciclo_busca: {e}', flush=True)

            # ── Mensagens WA (só horário comercial) ──
            if comercial:
                # Respostas
                try:
                    await asyncio.wait_for(
                        _ciclo_respostas(bot, gerador, schema,
                                         get_empresas_contactadas, get_empresa_por_whatsapp,
                                         get_estagio_conversa, registrar_interacao,
                                         atualizar_status_empresa, marcar_demo_proposto,
                                         marcar_demo_confirmado, log_acao),
                        timeout=120
                    )
                except asyncio.TimeoutError:
                    print(f'[{schema} {_ts()}] ⚠ ciclo_respostas timeout', flush=True)
                except Exception as e:
                    print(f'[{schema} {_ts()}] ✗ ciclo_respostas: {e}', flush=True)

                # Envio inicial
                try:
                    await asyncio.wait_for(
                        _ciclo_envio(bot, gerador, schema,
                                     get_empresas_sem_contato, registrar_interacao,
                                     atualizar_status_empresa, log_acao),
                        timeout=180
                    )
                except asyncio.TimeoutError:
                    print(f'[{schema} {_ts()}] ⚠ ciclo_envio timeout', flush=True)
                except Exception as e:
                    print(f'[{schema} {_ts()}] ✗ ciclo_envio: {e}', flush=True)

                # Follow-up
                try:
                    await asyncio.wait_for(
                        _ciclo_followup(bot, gerador, schema,
                                        get_empresas_para_followup, registrar_interacao,
                                        atualizar_status_empresa, log_acao),
                        timeout=120
                    )
                except asyncio.TimeoutError:
                    print(f'[{schema} {_ts()}] ⚠ ciclo_followup timeout', flush=True)
                except Exception as e:
                    print(f'[{schema} {_ts()}] ✗ ciclo_followup: {e}', flush=True)
            else:
                print(f'[{schema} {_ts()}] ℹ Fora do horário ({_cfg.HORARIO_INICIO}h-{_cfg.HORARIO_FIM}h seg-sex) — só prospecção', flush=True)

            print(f'[{schema} {_ts()}] ✓ Ciclo #{ciclo_num} completo.', flush=True)
            await asyncio.sleep(5)

    except (asyncio.CancelledError, KeyboardInterrupt):
        print(f'[{schema}] Bot encerrado', flush=True)
    except Exception as e:
        print(f'[{schema}] ERRO FATAL: {e}', flush=True)
        log_acao('erro', f'Erro fatal: {e}')
    finally:
        log_acao('info', f'[{schema}] Bot encerrado')
        if buscador_pronto:
            await buscador.fechar()
        await bot.fechar()


# =============================================================================
# CICLOS INTERNOS (adaptados para multi-tenant)
# =============================================================================

async def _ciclo_envio(bot, gerador, schema,
                       get_sem_contato, registrar, atualizar, log):
    leads = get_sem_contato(limite=10)
    if not leads:
        return

    print(f'[{schema} {_ts()}] ℹ {len(leads)} lead(s) para contatar via WA', flush=True)
    enviadas = falhas = 0

    for lead in leads:
        pode, motivo = bot.pode_enviar()
        if not pode:
            print(f'[{schema} {_ts()}] ⚠ {motivo}', flush=True)
            break

        numero = lead.get('whatsapp') or lead.get('telefone')
        if not numero:
            continue

        nome = lead.get('nome_fantasia', 'empresa')
        mensagem = gerador.gerar_inicial(lead)

        try:
            ok = await asyncio.wait_for(
                bot.enviar_mensagem(numero, mensagem, nome_lead=nome),
                timeout=45
            )
        except (asyncio.TimeoutError, Exception) as e:
            print(f'[{schema} {_ts()}] ⚠ Erro WA {nome[:35]}: {e}', flush=True)
            ok = False

        if ok:
            registrar(lead['id'], None, 'whatsapp', 'inicial', mensagem)
            atualizar(lead['id'], 'contactada')
            enviadas += 1
            await bot.delay_entre_mensagens()
        else:
            atualizar(lead['id'], 'sem_whatsapp')
            falhas += 1
            await asyncio.sleep(random.uniform(2, 5))

    print(f'[{schema} {_ts()}] ✓ Envio WA: {enviadas} ok, {falhas} falhas', flush=True)


async def _ciclo_respostas(bot, gerador, schema,
                            get_contactadas, get_por_wa, get_estagio,
                            registrar, atualizar, marcar_demo, marcar_confirmado, log):
    contactadas = get_contactadas(limite=20)
    numeros = [e['whatsapp'] for e in contactadas if e.get('whatsapp')]
    if not numeros:
        return

    print(f'[{schema} {_ts()}] ℹ Verificando {len(numeros)} conversa(s)...', flush=True)
    com_resposta = await bot.verificar_respostas_pendentes(numeros)
    if not com_resposta:
        return

    print(f'[{schema} {_ts()}] ✓ {len(com_resposta)} resposta(s)', flush=True)

    for info in com_resposta:
        numero = info.get('numero')
        empresa = get_por_wa(numero)
        if not empresa:
            continue

        estagio = get_estagio(empresa['id'])
        msg_lead = info.get('ultima_recebida', '')
        nome = empresa.get('nome_fantasia', numero)

        try:
            resposta, intencao = gerador.gerar_resposta(empresa, msg_lead, estagio=estagio)
        except Exception as e:
            print(f'[{schema} {_ts()}] ✗ Erro gerando resposta: {e}', flush=True)
            continue

        try:
            await bot.page.goto(
                f'https://web.whatsapp.com/send?phone={numero}', timeout=20000)
            await asyncio.sleep(random.uniform(3, 5))
        except Exception:
            continue

        try:
            ok = await asyncio.wait_for(bot.responder_conversa(resposta), timeout=30)
        except Exception:
            ok = False

        if ok:
            registrar(empresa['id'], None, 'whatsapp', 'resposta', resposta)
            nivel = intencao.get('nivel', 'media')
            if nivel in ('demo', 'agendamento'):
                marcar_demo(empresa['id'])
                atualizar(empresa['id'], 'respondeu')
            elif nivel == 'confirmacao':
                marcar_confirmado(empresa['id'])
                atualizar(empresa['id'], 'convertido')
            elif nivel == 'baixa':
                atualizar(empresa['id'], 'encerrado')
            log('info', f'Resposta: {nome} | {msg_lead[:50]}')

        await asyncio.sleep(5)


async def _ciclo_followup(bot, gerador, schema,
                           get_followup, registrar, atualizar, log):
    from config import FOLLOWUP1_DIAS, FOLLOWUP2_DIAS
    for n_fu, dias in [(1, FOLLOWUP1_DIAS), (2, FOLLOWUP2_DIAS)]:
        tipo = f'followup{n_fu}'
        leads = get_followup(dias, tipo)

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
            try:
                ok = await asyncio.wait_for(
                    bot.enviar_mensagem(numero, msg, nome_lead=nome), timeout=45)
            except Exception:
                ok = False

            if ok:
                registrar(lead['id'], None, 'whatsapp', tipo, msg)
                await bot.delay_entre_mensagens()

    print(f'[{schema} {_ts()}] ✓ Follow-up concluído', flush=True)


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--schema', required=True, help='Schema do usuário (ex: emp_1)')
    args = parser.parse_args()
    asyncio.run(main(args.schema))
