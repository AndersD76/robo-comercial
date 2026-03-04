# -*- coding: utf-8 -*-
"""
LinkedIn Bot — Prisma / PrismaBiz
Estratégia:
  1. Busca empresas por setor (metalurgia, indústria, ISO 9001…)
  2. Encontra responsáveis por Qualidade/SGQ
  3. Envia pedido de conexão com nota personalizada (IA)
  4. Após aceite, envia DM com pitch + link demo
  5. Exporta contatos para pipeline WhatsApp
"""

import asyncio
import random
from datetime import datetime, timezone, timedelta

from config import (
    ANTHROPIC_API_KEY, DEMO_CAL_LINK,
    LINKEDIN_EMAIL, LINKEDIN_PASSWORD,
    LINKEDIN_MAX_CONEXOES_DIA, LINKEDIN_MAX_MENSAGENS_DIA,
    LINKEDIN_TERMOS_BUSCA, LINKEDIN_CARGOS_ALVO,
    HORARIO_INICIO, HORARIO_FIM, DIAS_ATIVOS,
)

try:
    import anthropic
    HAS_AI = True
except ImportError:
    HAS_AI = False

try:
    from database import get_connection, salvar_lead_linkedin, registrar_log
    HAS_DB = True
except ImportError:
    HAS_DB = False

# Fuso horário de Brasília (UTC-3)
_BRT = timezone(timedelta(hours=-3))

# Diretório de sessão separado do WhatsApp
SESSION_DIR = './linkedin_session'

LINKEDIN_URL = 'https://www.linkedin.com'


class LinkedInBot:
    """
    Automação LinkedIn com Playwright.
    Mantém sessão persistente para não precisar logar toda vez.
    """

    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None
        self._pw = None
        self.conectado = False
        self.conexoes_hoje = 0
        self.msgs_hoje = 0
        self._msgs_respondidas: set = set()  # hashes já respondidos na sessão
        self._ciclo = 0
        self.ai = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) \
            if HAS_AI and ANTHROPIC_API_KEY else None

    # =========================================================================
    # SESSÃO
    # =========================================================================

    async def iniciar(self, headless: bool = True):
        """Abre browser com sessão persistente.
        Se DISPLAY está configurado (Xvfb), abre visível para permitir noVNC."""
        import os
        from playwright.async_api import async_playwright

        self._pw = await async_playwright().start()
        os.makedirs(SESSION_DIR, exist_ok=True)

        # Se tem display (Xvfb no container), abre visível para noVNC funcionar
        tem_display = self._tem_display()
        usar_headless = not tem_display if headless else False
        self._headless = usar_headless

        self.context = await self._pw.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR,
            headless=usar_headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-dev-shm-usage',
            ],
            user_agent=(
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/121.0.0.0 Safari/537.36'
            ),
            viewport={'width': 1366, 'height': 768},
            locale='pt-BR',
        )
        self.page = self.context.pages[0] if self.context.pages \
            else await self.context.new_page()
        modo = 'visível (Xvfb)' if not usar_headless else 'headless'
        self._log(f"LinkedIn bot Prisma iniciado ({modo})")

    async def fechar(self):
        if self.context:
            await self.context.close()
        if self._pw:
            await self._pw.stop()
        self._parar_vnc()

    @staticmethod
    def _tem_display() -> bool:
        """Verifica se há display disponível (X11/Wayland/Xvfb)."""
        import os, sys
        if sys.platform == 'win32':
            return True
        return bool(os.environ.get('DISPLAY') or
                    os.environ.get('WAYLAND_DISPLAY'))

    # ── VNC remoto (noVNC) ────────────────────────────────────────────────
    _vnc_procs: list = []

    def _iniciar_vnc(self):
        """Inicia x11vnc + websockify para acesso remoto via noVNC."""
        import subprocess, os
        if self._vnc_procs:
            return  # Já rodando
        display = os.environ.get('DISPLAY', ':99')
        try:
            p_vnc = subprocess.Popen(
                ['x11vnc', '-display', display, '-nopw', '-forever',
                 '-shared', '-rfbport', '5900', '-noxdamage'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            p_ws = subprocess.Popen(
                ['websockify', '--web', '/usr/share/novnc',
                 '6080', 'localhost:5900'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            self._vnc_procs = [p_vnc, p_ws]
            self._log(
                "noVNC iniciado — acesse pelo dashboard para "
                "resolver a verificação",
                'aviso'
            )
        except FileNotFoundError:
            self._log(
                "x11vnc/websockify não instalados — "
                "usando screenshots como fallback",
                'aviso'
            )

    def _parar_vnc(self):
        """Para x11vnc + websockify."""
        for p in self._vnc_procs:
            try:
                p.terminate()
            except Exception:
                pass
        self._vnc_procs = []

    # =========================================================================
    # LOGIN
    # =========================================================================

    async def _fechar_cookie_banner(self):
        """Tenta fechar banners de cookies/consent que bloqueiam a página."""
        for sel in [
            'button[action-type="ACCEPT"]',
            'button.artdeco-global-alert__action',
            '[data-test-global-alert-action]',
            'button:has-text("Accept")',
            'button:has-text("Aceitar")',
        ]:
            try:
                btn = await self.page.query_selector(sel)
                if btn:
                    await btn.click()
                    await asyncio.sleep(1)
                    return
            except Exception:
                continue

    async def fazer_login(self) -> bool:
        """
        Faz login se não estiver autenticado.
        Retorna True se já estava logado ou logou com sucesso.
        """
        self._log("Verificando sessão LinkedIn...")
        await self.page.goto(
            f'{LINKEDIN_URL}/feed/', wait_until='domcontentloaded'
        )
        await asyncio.sleep(random.uniform(2, 4))

        # Verifica se já está logado (feed carregou)
        if '/feed' in self.page.url or '/in/' in self.page.url:
            self.conectado = True
            self._log("Sessão LinkedIn ativa — login não necessário", 'sucesso')
            return True

        # Precisa logar
        email_conf = LINKEDIN_EMAIL[:4] + '***' if LINKEDIN_EMAIL else '(não definido)'
        self._log(f"Fazendo login com {email_conf}...")
        try:
            await self.page.goto(
                f'{LINKEDIN_URL}/login', wait_until='domcontentloaded'
            )
            await asyncio.sleep(random.uniform(2, 4))
            await self._fechar_cookie_banner()

            # Tenta diferentes seletores para o campo de email
            campo_email = None
            for sel in [
                '#username',
                'input[name="session_key"]',
                'input[autocomplete="username"]',
            ]:
                try:
                    await self.page.wait_for_selector(sel, timeout=5000)
                    campo_email = sel
                    break
                except Exception:
                    continue

            if not campo_email:
                self._log(
                    f"Campo de login não encontrado — URL: {self.page.url}. "
                    "Abrindo noVNC no dashboard para login manual.",
                    'erro'
                )
                resolvido = await self._aguardar_checkpoint()
                if resolvido:
                    self.conectado = True
                    self._log("Login manual via noVNC OK", 'sucesso')
                    return True
                return False

            await self.page.fill(campo_email, LINKEDIN_EMAIL)
            await asyncio.sleep(random.uniform(0.5, 1.2))

            campo_pwd = '#password'
            for sel_p in ['#password', 'input[name="session_password"]',
                          'input[type="password"]']:
                try:
                    el = await self.page.query_selector(sel_p)
                    if el:
                        campo_pwd = sel_p
                        break
                except Exception:
                    continue
            await self.page.fill(campo_pwd, LINKEDIN_PASSWORD)
            await asyncio.sleep(random.uniform(0.5, 1))
            await self.page.press(campo_pwd, 'Enter')
            await asyncio.sleep(random.uniform(3, 5))

            if '/feed' in self.page.url:
                self.conectado = True
                self._log("Login LinkedIn OK — feed carregado", 'sucesso')
                return True
            elif '/checkpoint' in self.page.url:
                self._log(
                    "LinkedIn exige verificação — resolva pelo "
                    "navegador interativo no dashboard (noVNC). "
                    "Bot aguarda até 10 min.",
                    'aviso'
                )
                resolvido = await self._aguardar_checkpoint()
                if resolvido:
                    self.conectado = True
                    self._log("Checkpoint resolvido — sessão ativa", 'sucesso')
                    return True
                self._log(
                    "Checkpoint não foi resolvido em 10 min — abortando.",
                    'erro'
                )
                return False
            else:
                self._log(f"Falha no login — URL atual: {self.page.url}", 'erro')
                return False
        except Exception as e:
            self._log(f"Erro no login: {e}", 'erro')
            return False

    async def _aguardar_checkpoint(self, timeout_min: int = 10) -> bool:
        """
        Inicia noVNC para o usuário resolver CAPTCHA/verificação interativamente
        no browser real do bot. Salva screenshot como fallback.
        """
        import os
        base_dir = os.path.dirname(os.path.abspath(__file__))
        chk_path = os.path.join(base_dir, 'li_checkpoint.png')
        timeout_s = timeout_min * 60
        elapsed = 0

        # Tenta resolver reCAPTCHA automaticamente (checkbox simples)
        captcha_tentado = False

        # Inicia noVNC se display disponível
        if self._tem_display():
            self._iniciar_vnc()
            self._log(
                "noVNC ativo — acesse pelo dashboard para resolver "
                "a verificação no browser real",
                'aviso'
            )

        while elapsed < timeout_s:
            # Screenshot para fallback no dashboard
            try:
                await self.page.screenshot(path=chk_path, full_page=False)
            except Exception:
                pass

            # Tenta clicar reCAPTCHA checkbox automaticamente (1x)
            if not captcha_tentado:
                captcha_tentado = True
                await self._tentar_resolver_captcha()

            # Verifica se resolveu
            cur = self.page.url
            if '/feed' in cur or ('/in/' in cur and '/checkpoint' not in cur):
                self._parar_vnc()
                try:
                    os.remove(chk_path)
                except Exception:
                    pass
                return True

            await asyncio.sleep(3)
            elapsed += 3

        self._parar_vnc()
        return False

    async def _tentar_resolver_captcha(self):
        """Tenta clicar no checkbox do reCAPTCHA dentro do iframe."""
        try:
            # reCAPTCHA fica dentro de um iframe
            for frame in self.page.frames:
                if 'recaptcha' in (frame.url or ''):
                    try:
                        checkbox = await frame.query_selector(
                            '.recaptcha-checkbox-border, '
                            '#recaptcha-anchor'
                        )
                        if checkbox:
                            self._log("Tentando resolver reCAPTCHA...")
                            await checkbox.click()
                            await asyncio.sleep(5)
                            # Verifica se resolveu (às vezes só o click resolve)
                            cur = self.page.url
                            if '/feed' in cur:
                                self._log("reCAPTCHA resolvido!", 'sucesso')
                            return
                    except Exception:
                        continue
            # Tenta também botão de submit/verificar na página principal
            for sel in [
                'button[type="submit"]',
                'button:has-text("Verificar")',
                'button:has-text("Verify")',
                'input[type="submit"]',
            ]:
                try:
                    btn = await self.page.query_selector(sel)
                    if btn:
                        await btn.click()
                        await asyncio.sleep(3)
                        return
                except Exception:
                    continue
        except Exception as e:
            self._log(f"Erro ao tentar resolver CAPTCHA: {e}", 'aviso')

    async def _executar_acao(self, act: dict):
        """Executa click/type/press vindo do dashboard."""
        action = act.get('action')
        if action == 'click':
            x, y = act.get('x', 0), act.get('y', 0)
            await self.page.mouse.click(x, y)
        elif action == 'type':
            texto = act.get('text', '')
            if texto:
                await self.page.keyboard.type(texto, delay=50)
        elif action == 'press':
            key = act.get('key', 'Enter')
            await self.page.keyboard.press(key)

    # =========================================================================
    # BUSCA DE LEADS
    # =========================================================================

    async def buscar_pessoas(self, termo: str, pagina: int = 1) -> list[dict]:
        """
        Busca pessoas no LinkedIn por cargo/setor.
        Retorna lista de dicts com nome, cargo, empresa, url_perfil.
        """
        resultados = []
        try:
            url = (
                f'{LINKEDIN_URL}/search/results/people/'
                f'?keywords={termo.replace(" ", "%20")}'
                f'&page={pagina}'
            )
            self._log(f"Buscando: \"{termo}\" (página {pagina})...")
            await self.page.goto(url, wait_until='domcontentloaded')
            await asyncio.sleep(random.uniform(2, 4))

            # Detecta checkpoint / muro de login após navegação
            cur_url = self.page.url
            if '/checkpoint' in cur_url or '/login' in cur_url or '/authwall' in cur_url:
                self._log(
                    "Redirecionado para checkpoint/login — sessão expirada. "
                    "Verifique credenciais e aprovação 2FA.", 'aviso'
                )
                return resultados

            # Scroll para carregar lazy items
            await self.page.evaluate('window.scrollTo(0, 800)')
            await asyncio.sleep(1)

            # Extrai todos os dados em um único evaluate — mais robusto que
            # múltiplas chamadas CSS (LinkedIn muda classes constantemente)
            perfis_data = await self.page.evaluate("""() => {
                const extrairNome = (el) => {
                    const cands = [
                        el.querySelector('span.entity-result__title-text a span[aria-hidden="true"]'),
                        el.querySelector('a[href*="/in/"] span[aria-hidden="true"]'),
                        el.querySelector('span.entity-result__title-text a'),
                        el.querySelector('a[href*="/in/"]'),
                    ];
                    for (const c of cands) {
                        const t = c?.textContent?.trim();
                        if (t && t !== 'LinkedIn Member') return t;
                    }
                    return '';
                };
                const extrairTexto = (el, sels) => {
                    for (const s of sels) {
                        const t = el.querySelector(s)?.textContent?.trim();
                        if (t) return t;
                    }
                    return '';
                };
                const extrairUrl = (el) => {
                    const a = el.querySelector('a[href*="/in/"]');
                    return a ? a.href.split('?')[0] : '';
                };

                // Tenta múltiplas estratégias para encontrar os cards
                let cards = [];
                const strats = [
                    () => [...document.querySelectorAll('li.reusable-search__result-container')],
                    () => [...document.querySelectorAll('li[class*="reusable-search__result-container"]')],
                    () => [...document.querySelectorAll('li[class*="result-container"]')],
                    () => [...document.querySelectorAll('li.scaffold-finite-scroll__list-item')]
                            .filter(li => li.querySelector('a[href*="/in/"]')),
                    () => [...document.querySelectorAll('li')]
                            .filter(li => li.querySelector('a[href*="/in/"]')
                                && li.querySelector('span[aria-hidden="true"]')
                                && li.offsetHeight > 40),
                ];
                for (const s of strats) {
                    cards = s();
                    if (cards.length > 0) break;
                }

                return cards.slice(0, 12).map(card => ({
                    nome:    extrairNome(card),
                    cargo:   extrairTexto(card, [
                        '.entity-result__primary-subtitle',
                        '[class*="primary-subtitle"]',
                        '[class*="entity-result__summary"]',
                    ]),
                    empresa: extrairTexto(card, [
                        '.entity-result__secondary-subtitle',
                        '[class*="secondary-subtitle"]',
                    ]),
                    url: extrairUrl(card),
                }));
            }""")

            n_total = len(perfis_data or [])
            self._log(f"  {n_total} perfis encontrados na página")

            for p in (perfis_data or []):
                nome    = (p.get('nome') or '').strip()
                cargo   = (p.get('cargo') or '').strip()
                empresa = (p.get('empresa') or '').strip()
                url_p   = (p.get('url') or '').strip()

                if not nome or 'LinkedIn Member' in nome:
                    continue
                if not self._cargo_alvo(cargo):
                    continue

                self._log(f"  → {nome} | {cargo} @ {empresa}")
                resultados.append({
                    'nome': nome,
                    'cargo': cargo,
                    'empresa': empresa,
                    'url_perfil': url_p,
                    'termo_busca': termo,
                })

            self._log(
                f"Resultado: {len(resultados)} leads qualificados "
                f"(cargo-alvo) de {n_total} perfis"
            )
        except Exception as e:
            self._log(f"Erro na busca: {e}", 'erro')
        return resultados

    def _cargo_alvo(self, cargo: str) -> bool:
        cargo_lower = cargo.lower()
        return any(c.lower() in cargo_lower for c in LINKEDIN_CARGOS_ALVO)

    # =========================================================================
    # ENVIAR CONEXÃO
    # =========================================================================

    async def enviar_conexao(self, perfil: dict) -> bool:
        """
        Acessa o perfil e envia pedido de conexão com nota personalizada.
        """
        if self.conexoes_hoje >= LINKEDIN_MAX_CONEXOES_DIA:
            self._log("Limite diário de conexões atingido", 'aviso')
            return False

        url = perfil.get('url_perfil', '')
        if not url:
            return False

        nome = perfil.get('nome', '?')
        cargo = perfil.get('cargo', '?')
        empresa = perfil.get('empresa', '?')
        self._log(f"Conectando com {nome} | {cargo} @ {empresa}...")

        try:
            await self.page.goto(url, wait_until='domcontentloaded')
            await asyncio.sleep(random.uniform(2, 4))

            # Botão "Conectar"
            conectar_btn = await self.page.query_selector(
                'button[aria-label*="Conectar"], button[aria-label*="Connect"]'
            )
            if not conectar_btn:
                # Pode estar em "Mais" (…)
                mais_btn = await self.page.query_selector(
                    'button[aria-label*="Mais"], button[aria-label*="More"]'
                )
                if mais_btn:
                    await mais_btn.click()
                    await asyncio.sleep(1)
                    conectar_btn = await self.page.query_selector(
                        'div[aria-label*="Conectar"],'
                        ' div[aria-label*="Connect"]'
                    )

            if not conectar_btn:
                self._log(f"  Botão Conectar não encontrado para {nome}", 'aviso')
                return False

            await conectar_btn.click()
            await asyncio.sleep(random.uniform(1, 2))

            # Clica "Adicionar nota"
            nota_btn = await self.page.query_selector(
                'button[aria-label*="nota"], button[aria-label*="note"]'
            )
            if nota_btn:
                await nota_btn.click()
                await asyncio.sleep(1)

                nota = await self._gerar_nota_conexao(perfil)
                textarea = await self.page.query_selector(
                    'textarea[name="message"]'
                )
                if textarea:
                    await textarea.fill(nota)
                    await asyncio.sleep(random.uniform(0.5, 1))

            # Confirma envio
            enviar_btn = await self.page.query_selector(
                'button[aria-label*="Enviar"], button[aria-label*="Send"]'
            )
            if enviar_btn:
                await enviar_btn.click()
                self.conexoes_hoje += 1
                self._log(
                    f"✓ Conexão #{self.conexoes_hoje}/{LINKEDIN_MAX_CONEXOES_DIA} "
                    f"enviada: {nome} @ {empresa}",
                    'sucesso'
                )
                if HAS_DB:
                    salvar_lead_linkedin(perfil, 'conexao_enviada')
                await asyncio.sleep(random.uniform(3, 7))
                return True

        except Exception as e:
            self._log(f"Erro ao conectar com {nome}: {e}", 'erro')
        return False

    async def _gerar_nota_conexao(self, perfil: dict) -> str:
        """Nota de 200 chars max para o pedido de conexão."""
        nome = perfil.get('nome', '').split()[0]
        empresa = perfil.get('empresa', 'sua empresa')
        cargo = perfil.get('cargo', '')

        if self.ai:
            try:
                r = self.ai.messages.create(
                    model='claude-3-haiku-20240307',
                    max_tokens=80,
                    system=(
                        "Escreva uma nota CURTA (max 200 chars) de pedido "
                        "de conexão no LinkedIn para um profissional de "
                        "qualidade/gestão industrial. Mencione PrismaBiz "
                        "(gestão da qualidade). Seja direto e profissional. "
                        "Retorne APENAS a nota, sem aspas."
                    ),
                    messages=[{
                        'role': 'user',
                        'content': (
                            f'Nome: {nome}, Cargo: {cargo}, '
                            f'Empresa: {empresa}'
                        ),
                    }],
                )
                nota = r.content[0].text.strip()
                return nota[:295]  # LinkedIn limita a 300 chars
            except Exception:
                pass

        # Fallback
        return (
            f"Oi {nome}, vi que você atua em {cargo} na {empresa}. "
            "Trabalho com gestão da qualidade e acredito que posso "
            "agregar. Vamos conectar?"
        )[:295]

    # =========================================================================
    # ENVIAR DM PÓS-CONEXÃO
    # =========================================================================

    async def enviar_dm_novos_contatos(self):
        """
        Abre o inbox, pega conexões aceitas recentemente sem DM enviada,
        e manda o pitch inicial.
        """
        if self.msgs_hoje >= LINKEDIN_MAX_MENSAGENS_DIA:
            return

        try:
            await self.page.goto(
                f'{LINKEDIN_URL}/messaging/', wait_until='domcontentloaded'
            )
            await asyncio.sleep(random.uniform(2, 3))

            # Pega threads sem mensagem de nossa parte ainda
            threads = (
                await self.page.query_selector_all(
                    'li.msg-conversation-listitem'
                )
                or await self.page.query_selector_all(
                    'li[class*="msg-conversation"]'
                )
                or await self.page.query_selector_all(
                    '[data-control-name="conversation"]'
                )
                or []
            )
            self._log(
                f"Inbox: {len(threads)} threads — verificando DMs iniciais"
            )

            enviadas = 0
            for thread in threads[:5]:
                try:
                    preview_txt = await thread.evaluate("""el => {
                        const sels = [
                            '.msg-conversation-card__message-snippet',
                            '[class*="message-snippet"]',
                            '[class*="conversation-card"] span',
                        ];
                        for (const s of sels) {
                            const e = el.querySelector(s);
                            if (e) return e.textContent.trim();
                        }
                        return '';
                    }""")

                    # Se o preview é da nossa conta, já mandamos — pula
                    if preview_txt.startswith('Você:'):
                        continue

                    await thread.click()
                    await asyncio.sleep(random.uniform(1, 2))

                    nome = await self.page.evaluate("""() => {
                        const sels = [
                            '.msg-entity-lockup__entity-title',
                            '[class*="entity-title"]',
                            '.msg-thread-top-bar h2',
                            'h2[class*="conversation"] span',
                        ];
                        for (const s of sels) {
                            const e = document.querySelector(s);
                            if (e) return e.textContent.trim();
                        }
                        return 'contato';
                    }""")

                    self._log(f"  Enviando DM inicial para {nome}...")
                    msg = self._gerar_dm_inicial(nome)
                    await self._digitar_e_enviar(msg)
                    self.msgs_hoje += 1
                    enviadas += 1
                    self._log(
                        f"  ✓ DM #{self.msgs_hoje}/{LINKEDIN_MAX_MENSAGENS_DIA} "
                        f"enviada para {nome}",
                        'sucesso'
                    )

                    if self.msgs_hoje >= LINKEDIN_MAX_MENSAGENS_DIA:
                        self._log("Limite de DMs do dia atingido", 'aviso')
                        break
                    await asyncio.sleep(random.uniform(30, 60))
                except Exception:
                    continue

            if enviadas == 0:
                self._log("Nenhuma DM inicial pendente encontrada")

        except Exception as e:
            self._log(f"Erro ao enviar DMs: {e}", 'erro')

    def _gerar_dm_inicial(self, nome: str) -> str:
        primeiro = nome.split()[0]
        return (
            f"Oi {primeiro}, obrigado por conectar! 👋\n\n"
            "Trabalho com o PrismaBiz — sistema de gestão da qualidade com "
            "11 ferramentas gratuitas "
            "(Auditoria, Plano de Ação, SWOT, PDCA…).\n\n"
            "Faz sentido para vocês? Se quiser ver ao vivo:\n"
            f"📅 {DEMO_CAL_LINK}\n\n"
            "Qualquer dúvida, é só chamar!"
        )

    async def _digitar_e_enviar(self, texto: str):
        caixa = (
            await self.page.query_selector('div.msg-form__contenteditable')
            or await self.page.query_selector(
                'div[contenteditable="true"][role="textbox"]'
            )
            or await self.page.query_selector('div[contenteditable="true"]')
        )
        if not caixa:
            self._log("Caixa de mensagem não encontrada", 'aviso')
            return
        await caixa.click()
        # Digita linha por linha (Enter quebra a msg no LinkedIn)
        for linha in texto.split('\n'):
            await caixa.type(linha, delay=random.randint(20, 60))
            await self.page.keyboard.press('Shift+Enter')
        # Apaga último shift+enter extra
        await self.page.keyboard.press('Backspace')
        await asyncio.sleep(0.5)
        await self.page.keyboard.press('Enter')
        await asyncio.sleep(random.uniform(1, 2))

    # =========================================================================
    # MONITORAR INBOX — RESPOSTAS DOS LEADS
    # =========================================================================

    async def monitorar_inbox(self):
        """
        Varre o inbox buscando mensagens de leads não respondidas por nós.
        Para cada resposta recebida, gera reply via Claude Haiku e envia.
        Objetivo final: marcar demo/reunião.
        """
        if self.msgs_hoje >= LINKEDIN_MAX_MENSAGENS_DIA:
            return
        try:
            await self.page.goto(
                f'{LINKEDIN_URL}/messaging/', wait_until='domcontentloaded'
            )
            await asyncio.sleep(random.uniform(2, 3))

            threads = (
                await self.page.query_selector_all(
                    'li.msg-conversation-listitem'
                )
                or await self.page.query_selector_all(
                    'li[class*="msg-conversation"]'
                )
                or await self.page.query_selector_all(
                    '[data-control-name="conversation"]'
                )
                or []
            )
            self._log(f"Monitorando inbox: {len(threads)} threads")

            replies = 0
            for thread in threads[:20]:
                try:
                    preview = await thread.evaluate("""el => {
                        const sels = [
                            '.msg-conversation-card__message-snippet',
                            '[class*="message-snippet"]',
                            '[class*="conversation-card"] span',
                        ];
                        for (const s of sels) {
                            const e = el.querySelector(s);
                            if (e) return e.textContent.trim();
                        }
                        return '';
                    }""")

                    # Pula se última msg foi nossa ou thread vazia
                    if preview.startswith('Você:') or not preview:
                        continue

                    await thread.click()
                    await asyncio.sleep(random.uniform(1.5, 2.5))

                    nome = await self.page.evaluate("""() => {
                        const sels = [
                            '.msg-entity-lockup__entity-title',
                            '[class*="entity-title"]',
                            '.msg-thread-top-bar h2',
                            'h2[class*="conversation"] span',
                        ];
                        for (const s of sels) {
                            const e = document.querySelector(s);
                            if (e) return e.textContent.trim();
                        }
                        return 'contato';
                    }""")

                    self._log(f"  Resposta de {nome}: \"{preview[:70]}\"")

                    historico = await self._ler_conversa()
                    if not historico:
                        continue

                    ultima = historico[-1]
                    # Pula se última msg foi nossa
                    if ultima.get('de_nos'):
                        continue

                    # Pula se já respondemos esta msg na sessão atual
                    msg_hash = hash(ultima.get('texto', ''))
                    if msg_hash in self._msgs_respondidas:
                        self._log("  (já respondido nesta sessão — pulando)")
                        continue

                    self._log(f"  Gerando reply IA para {nome}...")
                    resposta = await self._gerar_resposta_inbox(
                        nome, historico
                    )
                    if not resposta:
                        continue

                    await self._digitar_e_enviar(resposta)
                    self.msgs_hoje += 1
                    replies += 1
                    self._msgs_respondidas.add(msg_hash)
                    self._log(
                        f"  ✓ Reply enviado para {nome}: \"{resposta[:60]}...\"",
                        'sucesso'
                    )
                    self._atualizar_resposta_db(nome, ultima['texto'])

                    if self.msgs_hoje >= LINKEDIN_MAX_MENSAGENS_DIA:
                        self._log("Limite de DMs do dia atingido", 'aviso')
                        break
                    await asyncio.sleep(random.uniform(20, 40))

                except Exception:
                    continue

            if replies == 0:
                self._log("Nenhuma resposta pendente no inbox")

        except Exception as e:
            self._log(f"Erro no monitoramento do inbox: {e}", 'erro')

    async def _ler_conversa(self) -> list[dict]:
        """
        Extrai histórico de mensagens do thread aberto via JavaScript.
        Tenta seletores novos e antigos do LinkedIn para robustez.
        Retorna lista de dicts: {texto: str, de_nos: bool}
        """
        try:
            await asyncio.sleep(1)
            dados = await self.page.evaluate("""() => {
                // Tenta estrutura nova primeiro
                const newGroups = [
                    ...document.querySelectorAll('[class*="message-group"]')
                ];
                if (newGroups.length > 0) {
                    return newGroups.map(g => ({
                        de_nos: (
                            g.className.includes('outgoing') ||
                            g.getAttribute('data-outgoing') === 'true'
                        ),
                        texto: [
                            ...g.querySelectorAll(
                                '[class*="message-body"],'
                                '[class*="msg-s-event"]'
                            )
                        ].map(b => b.textContent.trim())
                         .filter(Boolean).join(' ')
                    })).filter(m => m.texto.length > 0);
                }
                // Fallback estrutura antiga
                const groups = [
                    ...document.querySelectorAll('.msg-s-message-group')
                ];
                return groups.map(g => ({
                    de_nos: g.classList.contains(
                        'msg-s-message-group--outgoing'
                    ),
                    texto: [...g.querySelectorAll(
                        '.msg-s-event-listitem__body'
                    )].map(b => b.textContent.trim())
                      .filter(Boolean).join(' ')
                })).filter(m => m.texto.length > 0);
            }""")
            return dados or []
        except Exception as e:
            self._log(f"Erro ao ler conversa: {e}", 'aviso')
            return []

    async def _gerar_resposta_inbox(
        self, nome: str, historico: list[dict]
    ) -> str:
        """Gera resposta via Claude Haiku com foco em agendar demo Prisma."""
        primeiro = nome.split()[0]
        hist_txt = '\n'.join([
            f"{'Eu' if m['de_nos'] else nome}: {m['texto']}"
            for m in historico[-6:]
        ])

        if self.ai:
            try:
                r = self.ai.messages.create(
                    model='claude-3-haiku-20240307',
                    max_tokens=150,
                    system=(
                        "Você é Daniel, vendedor do PrismaBiz — sistema de "
                        "gestão da qualidade com Auditoria, Plano de Ação, "
                        "SWOT, PDCA e mais 7 módulos, todos 100% gratuitos. "
                        f"Link para demo: {DEMO_CAL_LINK}\n"
                        "OBJETIVO: Agendar demo de 20 min.\n"
                        "REGRAS: resposta curta (2-3 frases), natural e "
                        "profissional. Interesse → convide para o link. "
                        "Objeção preço → é GRATUITO. "
                        "Objeção tempo → são 20 min apenas. "
                        "Desinteresse claro → agradeça e encerre. "
                        "Retorne APENAS a mensagem, sem aspas."
                    ),
                    messages=[{
                        'role': 'user',
                        'content': (
                            f"Histórico:\n{hist_txt}"
                            f"\n\nResponda para {primeiro}:"
                        ),
                    }],
                )
                return r.content[0].text.strip()
            except Exception:
                pass

        return (
            f"Oi {primeiro}! Fico feliz com o retorno. "
            "Que tal uma demo de 20 min para ver o PrismaBiz ao vivo? "
            f"É gratuito e você agenda aqui: {DEMO_CAL_LINK}"
        )

    def _atualizar_resposta_db(self, nome: str, ultima_msg: str):
        """Registra no banco que o lead respondeu."""
        if not HAS_DB:
            return
        try:
            conn = get_connection()
            c = conn.cursor()
            c.execute(
                """UPDATE leads_linkedin
                   SET respondeu = 1, ultima_resposta = %s
                   WHERE LOWER(nome) LIKE LOWER(%s)""",
                (ultima_msg[:500], f'%{nome.split()[0]}%')
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    # =========================================================================
    # LOOP PRINCIPAL
    # =========================================================================

    async def executar(self):
        """Loop contínuo: busca → conecta → dm"""
        ok = await self.fazer_login()
        if not ok:
            self._log("Não foi possível logar no LinkedIn. Abortando.", 'erro')
            return

        self._log(
            f"LinkedIn bot Prisma ativo — "
            f"max {LINKEDIN_MAX_CONEXOES_DIA} conexões/dia, "
            f"{LINKEDIN_MAX_MENSAGENS_DIA} DMs/dia",
            'sucesso'
        )
        termos = LINKEDIN_TERMOS_BUSCA.copy()
        random.shuffle(termos)
        self._log(f"{len(termos)} termos de busca carregados")
        termo_idx = 0

        while True:
            try:
                now = datetime.now(_BRT)

                if not self._horario_ativo(now):
                    # Log uma vez por hora quando inativo
                    if now.minute == 0:
                        self._log(
                            f"Fora do horário ativo "
                            f"({now.strftime('%H:%M')} BRT). "
                            f"Ativo: seg-sex {HORARIO_INICIO:02d}h–{HORARIO_FIM:02d}h"
                        )
                    await asyncio.sleep(60)
                    continue

                # Reset diário
                if now.hour == HORARIO_INICIO and now.minute < 5:
                    self.conexoes_hoje = 0
                    self.msgs_hoje = 0
                    self._log("Reset diário — contadores zerados para hoje")

                self._ciclo += 1
                self._log(
                    f"━━━ Ciclo #{self._ciclo} "
                    f"| {now.strftime('%H:%M')} BRT "
                    f"| Conexões: {self.conexoes_hoje}/{LINKEDIN_MAX_CONEXOES_DIA} "
                    f"| DMs: {self.msgs_hoje}/{LINKEDIN_MAX_MENSAGENS_DIA} ━━━"
                )

                # ── Fase 1: busca + conexões ──
                if self.conexoes_hoje < LINKEDIN_MAX_CONEXOES_DIA:
                    termo = termos[termo_idx % len(termos)]
                    termo_idx += 1
                    pagina = random.randint(1, 4)
                    leads = await self.buscar_pessoas(termo, pagina)

                    if leads:
                        self._log(f"Fase 1: {len(leads)} leads — enviando conexões...")
                        for lead in leads:
                            if self.conexoes_hoje >= LINKEDIN_MAX_CONEXOES_DIA:
                                self._log("Limite de conexões do dia atingido")
                                break
                            await self.enviar_conexao(lead)
                            pausa = random.randint(45, 120)
                            self._log(f"Aguardando {pausa}s antes do próximo...")
                            await asyncio.sleep(pausa)
                    else:
                        self._log("Fase 1: nenhum lead qualificado nesta busca")
                else:
                    self._log("Fase 1: limite de conexões já atingido hoje — pulando busca")

                # ── Fase 2: DMs para novas conexões ──
                if self.msgs_hoje < LINKEDIN_MAX_MENSAGENS_DIA:
                    self._log("Fase 2: verificando DMs iniciais para novas conexões...")
                    await self.enviar_dm_novos_contatos()
                else:
                    self._log("Fase 2: limite de DMs já atingido hoje — pulando")

                # ── Fase 3: monitorar respostas e reply via IA ──
                self._log("Fase 3: monitorando inbox para respostas...")
                await self.monitorar_inbox()

                # Pausa entre ciclos
                prox = random.randint(300, 600)
                self._log(
                    f"Ciclo #{self._ciclo} concluído. "
                    f"Próximo em {prox // 60} min {prox % 60}s."
                )
                await asyncio.sleep(prox)

            except Exception as e:
                self._log(f"Erro no loop principal: {e}", 'erro')
                await asyncio.sleep(60)

    def _horario_ativo(self, now: datetime) -> bool:
        if now.weekday() not in DIAS_ATIVOS:
            return False
        return HORARIO_INICIO <= now.hour < HORARIO_FIM

    def _log(self, msg: str, tipo: str = 'info'):
        ts = datetime.now(_BRT).strftime('%H:%M:%S')
        icone = {
            'info': 'ℹ', 'sucesso': '✓', 'aviso': '⚠', 'erro': '✗'
        }.get(tipo, 'ℹ')
        print(f"[LI/Prisma {ts}] {icone} {msg}", flush=True)
        if HAS_DB:
            try:
                registrar_log(tipo, f"[LinkedIn] {msg}")
            except Exception:
                pass


# ── Entrada standalone ──────────────────────────────────────────────────────
if __name__ == '__main__':
    import sys
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    bot = LinkedInBot()

    async def main():
        await bot.iniciar()
        await bot.executar()

    asyncio.run(main())
