# -*- coding: utf-8 -*-
"""
Runner standalone do bot WhatsApp — Pili Equipamentos
Invocado pelo dashboard via subprocess: python run_wa.py
"""

import sys
import asyncio
from datetime import datetime

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


async def ciclo_envio(bot: WhatsAppBot, gerador: GeradorMensagens, limite: int = 10):
    """Um ciclo de envio: pega leads novos e envia mensagens."""
    leads = get_empresas_sem_contato(limite=limite)
    if not leads:
        print(f"[{datetime.now():%H:%M}] Sem leads novos para contatar")
        return

    for lead in leads:
        pode, motivo = bot.pode_enviar()
        if not pode:
            print(f"[{datetime.now():%H:%M}] Pausa: {motivo}")
            break

        numero = lead.get('whatsapp') or lead.get('telefone')
        if not numero:
            continue

        nome = lead.get('nome_fantasia', 'lead')
        mensagem = gerador.gerar_inicial(lead)

        ok = await bot.enviar_mensagem(numero, mensagem, nome_lead=nome)
        if ok:
            registrar_interacao(lead['id'], None, 'whatsapp', 'inicial', mensagem)
            atualizar_status_empresa(lead['id'], 'contactada')
            incrementar_contagem('whatsapp_enviados')
            log_acao('info', f"Mensagem enviada para {nome} ({numero})")
            print(f"[{datetime.now():%H:%M}] OK  {nome}")
        else:
            print(f"[{datetime.now():%H:%M}] FALHA  {nome}")

        await bot.delay_entre_mensagens()


async def ciclo_respostas(bot: WhatsAppBot, gerador: GeradorMensagens):
    """Verifica e responde mensagens recebidas."""
    contactadas = get_empresas_contactadas(limite=20)
    numeros = [e['whatsapp'] for e in contactadas if e.get('whatsapp')]

    if not numeros:
        return

    com_resposta = await bot.verificar_respostas_pendentes(numeros)
    for info in com_resposta:
        numero = info.get('numero')
        empresa = get_empresa_por_whatsapp(numero)
        if not empresa:
            continue

        estagio = get_estagio_conversa(empresa['id'])
        resposta_lead = info.get('ultima_mensagem', '')

        resposta, intencao = gerador.gerar_resposta(
            empresa, resposta_lead, estagio=estagio
        )

        ok = await bot.responder_conversa(resposta)
        if ok:
            registrar_interacao(empresa['id'], None, 'whatsapp', 'resposta', resposta)
            nivel = intencao['nivel']
            if nivel in ('demo', 'agendamento'):
                marcar_demo_proposto(empresa['id'])
            elif nivel == 'confirmacao':
                marcar_demo_confirmado(empresa['id'])
            log_acao('info', f"Resposta enviada: {empresa.get('nome_fantasia')}")

        await asyncio.sleep(5)


async def main():
    """Loop principal do bot WhatsApp Pili Equipamentos."""
    print(f"[{datetime.now():%H:%M}] Iniciando bot WhatsApp Pili Equipamentos...")

    init_database()

    bot = WhatsAppBot()
    gerador = GeradorMensagens()

    conectado = await bot.iniciar()
    if not conectado:
        print("[ERRO] WhatsApp não conectou. Encerrando.")
        await bot.fechar()
        return

    print(f"[{datetime.now():%H:%M}] Conectado! Iniciando ciclos de prospecção...")
    log_acao('info', 'Bot WhatsApp Pili iniciado')

    try:
        while True:
            agora = datetime.now()

            if agora.hour < HORARIO_INICIO or agora.hour >= HORARIO_FIM:
                print(f"[{agora:%H:%M}] Fora do horário. Aguardando 30 min...")
                await asyncio.sleep(1800)
                continue

            if agora.weekday() not in DIAS_ATIVOS:
                print(f"[{agora:%H:%M}] Fim de semana. Aguardando 1h...")
                await asyncio.sleep(3600)
                continue

            await ciclo_envio(bot, gerador, limite=10)
            await asyncio.sleep(60)
            await ciclo_respostas(bot, gerador)

            print(f"[{agora:%H:%M}] Ciclo completo. Próximo em 5 min...")
            await asyncio.sleep(300)

    except (asyncio.CancelledError, KeyboardInterrupt):
        print("[INFO] Bot encerrado")
    finally:
        log_acao('info', 'Bot WhatsApp Pili encerrado')
        await bot.fechar()


if __name__ == '__main__':
    asyncio.run(main())
