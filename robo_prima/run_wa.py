# -*- coding: utf-8 -*-
"""
Runner standalone do bot WhatsApp — PrismaBiz
Invocado pelo dashboard via subprocess: python run_wa.py
"""

import sys
import asyncio
from datetime import datetime, timezone, timedelta

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from database import (
    init_database, get_empresas_sem_contato, registrar_interacao,
    atualizar_status_empresa, incrementar_contagem, log_acao,
    get_empresas_contactadas, get_estagio_conversa,
    marcar_demo_proposto, marcar_demo_confirmado, get_empresa_por_whatsapp,
)
from whatsapp import WhatsAppBot
from mensagens import GeradorMensagens
from config import HORARIO_INICIO, HORARIO_FIM, DIAS_ATIVOS

# Fuso horário de Brasília (UTC-3)
_BRT = timezone(timedelta(hours=-3))


def _ts() -> str:
    return datetime.now(_BRT).strftime('%H:%M:%S')


def _agora() -> datetime:
    return datetime.now(_BRT)


async def ciclo_envio(
    bot: WhatsAppBot, gerador: GeradorMensagens, limite: int = 10
):
    """Um ciclo de envio: pega leads novos e envia mensagens."""
    leads = get_empresas_sem_contato(limite=limite)
    if not leads:
        print(
            f"[WA/Prisma {_ts()}] ℹ Sem leads novos para contatar",
            flush=True
        )
        return

    print(
        f"[WA/Prisma {_ts()}] ℹ {len(leads)} lead(s) para contatar "
        f"neste ciclo",
        flush=True
    )
    enviadas = 0
    falhas = 0

    for lead in leads:
        pode, motivo = bot.pode_enviar()
        if not pode:
            print(
                f"[WA/Prisma {_ts()}] ⚠ Pausa: {motivo}",
                flush=True
            )
            break

        numero = lead.get('whatsapp') or lead.get('telefone')
        if not numero:
            continue

        nome = lead.get('nome_fantasia', 'lead')
        segmento = lead.get('segmento', '')
        score = lead.get('score', 0)
        mensagem = gerador.gerar_inicial(lead)

        print(
            f"[WA/Prisma {_ts()}] ℹ Contatando: {nome} "
            f"(score {score} | {segmento})",
            flush=True
        )
        ok = await bot.enviar_mensagem(numero, mensagem, nome_lead=nome)
        if ok:
            registrar_interacao(
                lead['id'], None, 'whatsapp', 'inicial', mensagem
            )
            atualizar_status_empresa(lead['id'], 'contactada')
            incrementar_contagem('whatsapp_enviados')
            log_acao('info', f"Mensagem enviada para {nome} ({numero})")
            enviadas += 1
        else:
            falhas += 1

        await bot.delay_entre_mensagens()

    print(
        f"[WA/Prisma {_ts()}] ✓ Ciclo de envio: "
        f"{enviadas} enviadas, {falhas} falhas",
        flush=True
    )


async def ciclo_respostas(bot: WhatsAppBot, gerador: GeradorMensagens):
    """Verifica e responde mensagens recebidas."""
    contactadas = get_empresas_contactadas(limite=20)
    numeros = [e['whatsapp'] for e in contactadas if e.get('whatsapp')]

    if not numeros:
        print(
            f"[WA/Prisma {_ts()}] ℹ Nenhuma empresa contactada para verificar",
            flush=True
        )
        return

    print(
        f"[WA/Prisma {_ts()}] ℹ Verificando respostas: "
        f"{len(numeros)} empresa(s) contactada(s)",
        flush=True
    )
    com_resposta = await bot.verificar_respostas_pendentes(numeros)

    if not com_resposta:
        return

    print(
        f"[WA/Prisma {_ts()}] ✓ {len(com_resposta)} resposta(s) "
        f"a processar",
        flush=True
    )
    for info in com_resposta:
        numero = info.get('numero')
        empresa = get_empresa_por_whatsapp(numero)
        if not empresa:
            continue

        estagio = get_estagio_conversa(empresa['id'])
        resposta_lead = info.get('ultima_recebida', '')
        nome = empresa.get('nome_fantasia', numero)

        print(
            f"[WA/Prisma {_ts()}] ℹ Respondendo {nome} "
            f"(estágio: {estagio})...",
            flush=True
        )
        resposta, intencao = gerador.gerar_resposta(
            empresa, resposta_lead, estagio=estagio
        )

        ok = await bot.responder_conversa(resposta)
        if ok:
            registrar_interacao(
                empresa['id'], None, 'whatsapp', 'resposta', resposta
            )
            nivel = intencao['nivel']
            if nivel in ('demo', 'agendamento'):
                marcar_demo_proposto(empresa['id'])
                print(
                    f"[WA/Prisma {_ts()}] ✓ Demo proposta para {nome}",
                    flush=True
                )
            elif nivel == 'confirmacao':
                marcar_demo_confirmado(empresa['id'])
                print(
                    f"[WA/Prisma {_ts()}] ✓ Demo CONFIRMADA: {nome}",
                    flush=True
                )
            log_acao(
                'info', f"Resposta enviada: {empresa.get('nome_fantasia')}"
            )

        await asyncio.sleep(5)


async def main():
    """Loop principal do bot WhatsApp PrismaBiz."""
    print(
        f"[WA/Prisma {_ts()}] ℹ === Bot WhatsApp PrismaBiz iniciando ===",
        flush=True
    )

    init_database()
    print(f"[WA/Prisma {_ts()}] ℹ Banco de dados inicializado", flush=True)

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
        f"[WA/Prisma {_ts()}] ✓ Conectado! Iniciando ciclos de prospecção...",
        flush=True
    )
    log_acao('info', 'Bot WhatsApp PrismaBiz iniciado')
    ciclo_num = 0

    try:
        while True:
            agora = _agora()

            if agora.hour < HORARIO_INICIO or agora.hour >= HORARIO_FIM:
                print(
                    f"[WA/Prisma {_ts()}] ℹ Fora do horário "
                    f"({agora.strftime('%H:%M')} BRT). "
                    f"Ativo: {HORARIO_INICIO:02d}h–{HORARIO_FIM:02d}h. "
                    "Aguardando 30 min...",
                    flush=True
                )
                await asyncio.sleep(1800)
                continue

            if agora.weekday() not in DIAS_ATIVOS:
                print(
                    f"[WA/Prisma {_ts()}] ℹ Fim de semana. "
                    "Aguardando 1h...",
                    flush=True
                )
                await asyncio.sleep(3600)
                continue

            ciclo_num += 1
            print(
                f"[WA/Prisma {_ts()}] ━━━ Ciclo #{ciclo_num} "
                f"| msgs hoje: {bot.msgs_enviadas_hoje} "
                f"| sessão: {bot.msgs_enviadas_sessao} ━━━",
                flush=True
            )

            await ciclo_envio(bot, gerador, limite=10)
            await asyncio.sleep(60)
            await ciclo_respostas(bot, gerador)

            print(
                f"[WA/Prisma {_ts()}] ✓ Ciclo #{ciclo_num} completo. "
                "Próximo em 5 min...",
                flush=True
            )
            await asyncio.sleep(300)

    except (asyncio.CancelledError, KeyboardInterrupt):
        print(f"[WA/Prisma {_ts()}] ℹ Bot encerrado pelo operador", flush=True)
    finally:
        log_acao('info', 'Bot WhatsApp PrismaBiz encerrado')
        await bot.fechar()


if __name__ == '__main__':
    asyncio.run(main())
