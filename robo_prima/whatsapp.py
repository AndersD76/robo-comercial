# -*- coding: utf-8 -*-
"""
Automação WhatsApp Web v3 - PrismaBiz
Usa Playwright com seletores estáveis (atributos data-*, JS DOM)
Corrige: leitura de respostas, sessão persistente, newline extra
"""

import re
import random
import asyncio
from urllib.parse import quote

from config import (
    INTERVALO_MSG_MIN, INTERVALO_MSG_MAX,
    PAUSA_LONGA_A_CADA, PAUSA_LONGA_MIN, PAUSA_LONGA_MAX,
    HORARIO_INICIO, HORARIO_FIM, DIAS_ATIVOS,
    MAX_WHATSAPP_DIA, WARMUP,
)

# Diretório para salvar sessão e evitar QR toda vez
SESSION_DIR = './whatsapp_session'


class WhatsAppBot:
    """Automação WhatsApp Web com Playwright — seletores estáveis"""

    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None
        self._pw = None
        self.conectado = False
        self.msgs_enviadas_hoje = 0
        self.msgs_enviadas_sessao = 0

    # =========================================================================
    # CONEXÃO
    # =========================================================================

    async def iniciar(self):
        """Inicia browser com contexto persistente (salva sessão/QR)"""
        import os
        from playwright.async_api import async_playwright

        self._pw = await async_playwright().start()

        os.makedirs(SESSION_DIR, exist_ok=True)

        # headless=True em Linux/Railway (sem display); False no Windows local
        import sys as _sys
        _headless = _sys.platform != 'win32'

        # Contexto persistente: salva cookies/sessão em disco → não pede QR toda vez
        self.context = await self._pw.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR,
            headless=_headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--start-maximized',
            ],
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            viewport={'width': 1366, 'height': 768},
        )

        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()

        # Remove navigator.webdriver
        await self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)

        print("\n  Abrindo WhatsApp Web...")
        await self.page.goto('https://web.whatsapp.com', timeout=30000)

        # Verifica se já está conectado (sessão salva)
        ja_conectado = await self._verificar_ja_conectado()
        if not ja_conectado:
            print("\n  ESCANEIE O QR CODE NO DASHBOARD > QR Code")
            # Salva screenshots do QR enquanto aguarda
            qr_task = asyncio.ensure_future(self._salvar_qr_loop())
            conectado = await self._aguardar_conexao(timeout=300)
            qr_task.cancel()
            # Remove arquivo QR após autenticação
            try:
                os.remove('./wa_qr.png')
            except OSError:
                pass
        else:
            conectado = True

        if conectado:
            self.conectado = True
            print("\n  [OK] WhatsApp conectado!")
            return True
        else:
            print("\n  [ERRO] WhatsApp nao conectou em 5 minutos")
            return False

    async def _salvar_qr_loop(self):
        """Salva screenshot do QR Code a cada 3s para o dashboard servir."""
        while True:
            try:
                await self.page.screenshot(path='./wa_qr.png', full_page=False)
            except Exception:
                pass
            await asyncio.sleep(3)

    async def _verificar_ja_conectado(self):
        """Verifica se a sessão já está ativa (sem precisar de QR)"""
        try:
            await self.page.wait_for_selector('#side', timeout=5000)
            return True
        except Exception:
            return False

    async def _aguardar_conexao(self, timeout=180):
        """Aguarda até o WhatsApp conectar"""
        seletores = ['#side', '[data-icon="menu"]', '[data-icon="chat"]']

        for i in range(timeout):
            for seletor in seletores:
                try:
                    el = await self.page.query_selector(seletor)
                    if el:
                        await asyncio.sleep(2)
                        return True
                except Exception:
                    pass

            if i % 15 == 0 and i > 0:
                print(f"  Aguardando conexão... ({i}s)")

            await asyncio.sleep(1)

        return False

    async def fechar(self):
        """Fecha browser"""
        self.conectado = False
        if self.context:
            await self.context.close()
        if self._pw:
            await self._pw.stop()

    # =========================================================================
    # ENVIO DE MENSAGEM
    # =========================================================================

    async def enviar_mensagem(self, telefone, mensagem, nome_lead=""):
        """Envia mensagem para um número via WhatsApp Web"""
        if not self.conectado:
            print("    [ERRO] WhatsApp não conectado")
            return False

        numero = self._formatar_numero(telefone)
        if not numero:
            print(f"    [ERRO] Número inválido: {telefone}")
            return False

        try:
            url = f"https://web.whatsapp.com/send?phone={numero}&text={quote(mensagem)}"
            await self.page.goto(url, timeout=20000)
            await asyncio.sleep(random.uniform(4, 7))

            # Detecta popup de número inválido
            erro = await self.page.query_selector('div[data-animate-modal-body="true"]')
            if erro:
                texto_erro = await erro.inner_text()
                if 'não está no WhatsApp' in texto_erro or 'invalid' in texto_erro.lower():
                    print(f"    [!] Número não está no WhatsApp: {numero}")
                    try:
                        btn_ok = await self.page.query_selector('div[data-animate-modal-body="true"] button')
                        if btn_ok:
                            await btn_ok.click()
                    except Exception:
                        pass
                    return False

            enviado = await self._clicar_enviar()

            if enviado:
                self.msgs_enviadas_hoje += 1
                self.msgs_enviadas_sessao += 1
                nome_display = nome_lead[:25] if nome_lead else numero
                print(f"    [OK] Enviado para {nome_display} ({self.msgs_enviadas_hoje} hoje)")
                return True
            else:
                print(f"    [ERRO] Não conseguiu enviar para {numero}")
                return False

        except Exception as e:
            print(f"    [ERRO] WhatsApp: {e}")
            return False

    async def _clicar_enviar(self):
        """Tenta clicar no botão enviar"""
        seletores = [
            'span[data-icon="send"]',
            'button[aria-label="Enviar"]',
            '[data-testid="send"]',
            'button[aria-label="Send"]',
        ]

        for tentativa in range(3):
            for seletor in seletores:
                try:
                    btn = await self.page.wait_for_selector(seletor, timeout=5000)
                    if btn:
                        await btn.click()
                        await asyncio.sleep(2)
                        return True
                except Exception:
                    continue
            await asyncio.sleep(2)

        # Fallback: Enter na caixa de texto
        try:
            input_box = await self._get_input_box()
            if input_box:
                await input_box.press('Enter')
                await asyncio.sleep(2)
                return True
        except Exception:
            pass

        return False

    # =========================================================================
    # VERIFICAR E LER RESPOSTAS — seletores estáveis via JS
    # =========================================================================

    async def verificar_respostas_pendentes(self, numeros: list) -> list:
        """
        Abre cada conversa pelo número e verifica se o lead respondeu.
        Substitui verificar_nao_lidas() que usava classes CSS dinâmicas.
        """
        if not self.conectado:
            return []

        resultados = []

        for numero in numeros[:10]:  # máx 10 por ciclo para não demorar muito
            numero_fmt = self._formatar_numero(numero)
            if not numero_fmt:
                continue

            try:
                url = f"https://web.whatsapp.com/send?phone={numero_fmt}"
                await self.page.goto(url, timeout=20000)
                await asyncio.sleep(random.uniform(3, 5))

                dados = await self._ler_conversa_atual()
                if dados and dados.get('lead_respondeu'):
                    dados['numero'] = numero_fmt
                    resultados.append(dados)

                await asyncio.sleep(random.uniform(1, 2))

            except Exception as e:
                print(f"    [!] Erro ao verificar {numero_fmt}: {e}")
                continue

        return resultados

    async def _ler_conversa_atual(self) -> dict:
        """
        Lê a conversa atualmente aberta usando atributos estáveis do DOM.
        Usa data-pre-plain-text (contém remetente/hora) e innerText das mensagens.
        """
        try:
            await asyncio.sleep(2)  # aguarda mensagens carregarem

            # Nome do contato no header
            nome = "Lead"
            try:
                header = await self.page.query_selector('header [data-testid="conversation-header"] span[dir="auto"]')
                if not header:
                    header = await self.page.query_selector('header span[dir="auto"]')
                if header:
                    nome = (await header.inner_text()).strip()[:40]
            except Exception:
                pass

            # Lê mensagens via JavaScript usando atributos estáveis
            msgs = await self.page.evaluate("""
                () => {
                    const resultado = [];

                    // Tenta via data-pre-plain-text (formato: "[hora, remetente] ")
                    const comAttr = document.querySelectorAll('[data-pre-plain-text]');
                    if (comAttr.length > 0) {
                        comAttr.forEach(el => {
                            const attr = el.getAttribute('data-pre-plain-text') || '';
                            const textEl = el.querySelector('span[class*="selectable"], span.copyable-text, span');
                            const texto = textEl ? textEl.innerText.trim() : el.innerText.trim();
                            if (!texto) return;
                            // Se o atributo contém "Você" ou é mensagem enviada
                            const deMim = attr.includes('Você') || el.closest('[class*="message-out"]') !== null;
                            resultado.push({ texto, deMim, attr });
                        });
                        return resultado;
                    }

                    // Fallback: data-testid para mensagens
                    const msgEls = document.querySelectorAll('[data-testid="msg-container"]');
                    msgEls.forEach(el => {
                        const textEl = el.querySelector('.copyable-text span, [class*="selectable"] span');
                        const texto = textEl ? textEl.innerText.trim() : '';
                        if (!texto) return;
                        const deMim = el.querySelector('[data-testid="msg-check"], [data-testid="msg-dblcheck"]') !== null;
                        resultado.push({ texto, deMim });
                    });

                    return resultado;
                }
            """)

            if not msgs:
                return None

            ultimas = msgs[-10:]
            msgs_recebidas = [m['texto'] for m in ultimas if not m.get('deMim')]
            msgs_enviadas = [m['texto'] for m in ultimas if m.get('deMim')]

            # Lead respondeu se a última mensagem é dele
            ultima = ultimas[-1] if ultimas else None
            lead_respondeu = ultima and not ultima.get('deMim') and len(msgs_recebidas) > 0

            return {
                'nome': nome,
                'lead_respondeu': lead_respondeu,
                'ultima_recebida': msgs_recebidas[-1] if msgs_recebidas else None,
                'msgs_recebidas': msgs_recebidas,
                'msgs_enviadas': msgs_enviadas,
            }

        except Exception as e:
            print(f"    [!] Erro ao ler conversa: {e}")
            return None

    async def responder_conversa(self, mensagem):
        """Responde na conversa aberta atualmente (sem newline extra no final)"""
        try:
            input_box = await self._get_input_box()
            if not input_box:
                return False

            await input_box.click()
            await asyncio.sleep(0.5)

            linhas = mensagem.split('\n')
            for i, linha in enumerate(linhas):
                await input_box.type(linha, delay=random.randint(20, 50))
                # Shift+Enter apenas entre linhas, não após a última
                if i < len(linhas) - 1:
                    await self.page.keyboard.down('Shift')
                    await self.page.keyboard.press('Enter')
                    await self.page.keyboard.up('Shift')

            await asyncio.sleep(0.5)
            await self.page.keyboard.press('Enter')
            await asyncio.sleep(2)
            return True

        except Exception as e:
            print(f"    [ERRO] Responder: {e}")
            return False

    async def _get_input_box(self):
        """Retorna a caixa de texto do WhatsApp Web (tenta múltiplos seletores)"""
        seletores = [
            'div[contenteditable="true"][data-tab="10"]',
            'div[contenteditable="true"][aria-label="Digite uma mensagem"]',
            'div[contenteditable="true"][aria-label="Type a message"]',
            'div[contenteditable="true"][role="textbox"]',
        ]
        for seletor in seletores:
            try:
                el = await self.page.wait_for_selector(seletor, timeout=4000)
                if el:
                    return el
            except Exception:
                continue
        return None

    # =========================================================================
    # ANTI-BAN
    # =========================================================================

    async def delay_entre_mensagens(self):
        """Delay aleatório entre mensagens (anti-ban)"""
        if self.msgs_enviadas_sessao > 0 and self.msgs_enviadas_sessao % PAUSA_LONGA_A_CADA == 0:
            pausa = random.uniform(PAUSA_LONGA_MIN, PAUSA_LONGA_MAX)
            print(f"\n  [PAUSA] Pausa longa de {pausa:.0f}s (anti-ban)...")
            await asyncio.sleep(pausa)
        else:
            delay = random.uniform(INTERVALO_MSG_MIN, INTERVALO_MSG_MAX)
            print(f"    Aguardando {delay:.0f}s...")
            await asyncio.sleep(delay)

    def pode_enviar(self, dia_warmup=7):
        """Verifica se pode enviar mais mensagens hoje"""
        from datetime import datetime

        agora = datetime.now()

        if agora.hour < HORARIO_INICIO or agora.hour >= HORARIO_FIM:
            return False, "Fora do horário comercial"

        if agora.weekday() not in DIAS_ATIVOS:
            return False, "Dia inativo (fim de semana)"

        limite = WARMUP.get(dia_warmup, MAX_WHATSAPP_DIA)
        if self.msgs_enviadas_hoje >= limite:
            return False, f"Limite diário atingido ({self.msgs_enviadas_hoje}/{limite})"

        return True, "OK"

    # =========================================================================
    # UTILIDADES
    # =========================================================================

    def _formatar_numero(self, telefone):
        """Formata número para WhatsApp (55XXXXXXXXXXX)"""
        if not telefone:
            return None

        numeros = re.sub(r'\D', '', str(telefone))

        if numeros.startswith('55') and len(numeros) in [12, 13]:
            return numeros

        if len(numeros) == 11:
            return '55' + numeros
        elif len(numeros) == 10:
            # Celular sem o 9 → adiciona
            ddd = numeros[:2]
            resto = numeros[2:]
            return '55' + ddd + '9' + resto

        return None
