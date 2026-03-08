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
from urllib.parse import quote

from config import (
    ANTHROPIC_API_KEY, DEMO_CAL_LINK,
    LINKEDIN_EMAIL, LINKEDIN_PASSWORD,
    LINKEDIN_MAX_CONEXOES_DIA, LINKEDIN_MAX_MENSAGENS_DIA,
    LINKEDIN_TERMOS_BUSCA, LINKEDIN_CARGOS_ALVO,
    HORARIO_INICIO, HORARIO_FIM, DIAS_ATIVOS,
    SALES_NAV_HABILITADO, SALES_NAV_FILTROS, SALES_NAV_TERMOS,
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
        self._ultimo_dia: int = -1  # dia do mês do último reset
        self._sales_nav_disponivel: bool | None = None  # None = não verificado
        self._apollo_leads_pendentes: list[dict] = []  # buffer de leads Apollo
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
                '--disable-infobars',
                '--disable-background-timer-throttling',
                '--disable-popup-blocking',
                '--disable-extensions',
                '--disable-component-update',
                '--disable-default-apps',
                '--disable-features=TranslateUI',
                '--lang=pt-BR',
                '--window-size=1366,768',
            ],
            user_agent=(
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/131.0.0.0 Safari/537.36'
            ),
            viewport={'width': 1366, 'height': 768},
            locale='pt-BR',
            timezone_id='America/Sao_Paulo',
            color_scheme='light',
            ignore_https_errors=True,
        )
        self.page = self.context.pages[0] if self.context.pages \
            else await self.context.new_page()

        # Stealth: esconde sinais de automação (Playwright/WebDriver)
        await self.page.add_init_script("""
            // Remove navigator.webdriver
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            // Chrome runtime
            window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){} };
            // Permissions API
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({state: Notification.permission}) :
                    originalQuery(parameters)
            );
            // Plugins (Chrome tem plugins, headless não)
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5].map(() => ({
                    name: 'Chrome PDF Plugin',
                    filename: 'internal-pdf-viewer',
                    description: 'Portable Document Format'
                }))
            });
            // Languages
            Object.defineProperty(navigator, 'languages', {get: () => ['pt-BR', 'pt', 'en-US', 'en']});
            // Platform
            Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
            // Hardware concurrency
            Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
            // Device memory
            Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});
            // WebGL vendor/renderer (real Chrome values)
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) return 'Google Inc. (NVIDIA)';
                if (parameter === 37446) return 'ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 Direct3D11 vs_5_0 ps_5_0, D3D11)';
                return getParameter.call(this, parameter);
            };
        """)
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
            vnc_log = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), 'vnc.log')
            vnc_f = open(vnc_log, 'a')
            p_vnc = subprocess.Popen(
                ['x11vnc', '-display', display, '-nopw', '-forever',
                 '-shared', '-rfbport', '5900', '-noxdamage'],
                stdout=vnc_f, stderr=vnc_f
            )
            import time; time.sleep(1)
            p_ws = subprocess.Popen(
                ['websockify', '--web', '/usr/share/novnc',
                 '6080', 'localhost:5900'],
                stdout=vnc_f, stderr=vnc_f
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
        if not LINKEDIN_EMAIL or not LINKEDIN_PASSWORD:
            self._log(
                "LINKEDIN_EMAIL ou LINKEDIN_PASSWORD nao configurados! "
                "Configure no Railway ou em linkedin_creds.json.",
                'erro'
            )
            return False
        email_conf = LINKEDIN_EMAIL[:4] + '***'
        self._log(f"Fazendo login com {email_conf}...")
        try:
            await self.page.goto(
                f'{LINKEDIN_URL}/login', wait_until='load'
            )
            await asyncio.sleep(random.uniform(3, 5))
            await self._fechar_cookie_banner()

            # Tenta diferentes seletores para o campo de email
            seletores_email = [
                '#username',
                'input[name="session_key"]',
                'input[autocomplete="username"]',
                'input[type="text"]',
                'input[type="email"]',
            ]
            campo_email = None
            for tentativa in range(2):
                for sel in seletores_email:
                    try:
                        await self.page.wait_for_selector(sel, timeout=5000)
                        campo_email = sel
                        break
                    except Exception:
                        continue
                if campo_email:
                    break
                # Segunda tentativa: recarrega a página
                self._log("Seletores não encontrados, recarregando página de login...")
                await self.page.reload(wait_until='load')
                await asyncio.sleep(random.uniform(3, 5))
                await self._fechar_cookie_banner()

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

            # Digita como humano (caractere por caractere com delay)
            await self.page.click(campo_email)
            await asyncio.sleep(random.uniform(0.3, 0.6))
            await self.page.type(campo_email, LINKEDIN_EMAIL, delay=random.randint(50, 120))
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
            await self.page.click(campo_pwd)
            await asyncio.sleep(random.uniform(0.2, 0.5))
            await self.page.type(campo_pwd, LINKEDIN_PASSWORD, delay=random.randint(50, 120))
            await asyncio.sleep(random.uniform(0.5, 1))
            await self.page.press(campo_pwd, 'Enter')
            await asyncio.sleep(random.uniform(3, 5))

            if '/feed' in self.page.url:
                self.conectado = True
                self._log("Login LinkedIn OK — feed carregado", 'sucesso')
                return True
            elif '/checkpoint' in self.page.url:
                cur_url = self.page.url
                # Se checkpoint deu erro interno, tenta limpar cookies e relogar
                if 'internal_error' in cur_url or 'errorKey' in cur_url:
                    self._log(
                        "Checkpoint com erro interno — sessão flagged. "
                        "Deletando sessão e reiniciando browser em 15s...",
                        'aviso'
                    )
                    # Fecha browser atual
                    try:
                        await self.context.close()
                    except Exception:
                        pass
                    try:
                        await self._pw.stop()
                    except Exception:
                        pass

                    # Deleta pasta de sessão inteira
                    import shutil
                    try:
                        shutil.rmtree(SESSION_DIR, ignore_errors=True)
                        self._log("Sessão antiga deletada", 'aviso')
                    except Exception as e_rm:
                        self._log(f"Erro ao deletar sessão: {e_rm}", 'aviso')

                    # Espera antes de recriar
                    await asyncio.sleep(15)

                    # Reinicia browser com sessão limpa
                    try:
                        await self.iniciar(headless=self._headless)
                        self._log("Browser reiniciado com sessão limpa", 'aviso')
                        # Tenta login de novo
                        await self.page.goto(
                            f'{LINKEDIN_URL}/login', wait_until='load'
                        )
                        await asyncio.sleep(random.uniform(3, 5))
                        await self._fechar_cookie_banner()
                        for sel in seletores_email:
                            try:
                                await self.page.wait_for_selector(sel, timeout=5000)
                                await self.page.click(sel)
                                await asyncio.sleep(0.3)
                                await self.page.type(sel, LINKEDIN_EMAIL, delay=random.randint(80, 150))
                                await asyncio.sleep(random.uniform(0.5, 1))
                                for sel_p in ['#password', 'input[name="session_password"]', 'input[type="password"]']:
                                    el = await self.page.query_selector(sel_p)
                                    if el:
                                        await self.page.click(sel_p)
                                        await asyncio.sleep(0.3)
                                        await self.page.type(sel_p, LINKEDIN_PASSWORD, delay=random.randint(80, 150))
                                        await asyncio.sleep(random.uniform(0.5, 1))
                                        await self.page.press(sel_p, 'Enter')
                                        break
                                break
                            except Exception:
                                continue
                        await asyncio.sleep(random.uniform(5, 8))
                        if '/feed' in self.page.url:
                            self.conectado = True
                            self._log("Login OK com sessão limpa!", 'sucesso')
                            return True
                        elif '/checkpoint' not in self.page.url:
                            self.conectado = True
                            self._log(f"Pós-login URL: {self.page.url}", 'aviso')
                            return True
                    except Exception as e2:
                        self._log(f"Retry com sessão limpa falhou: {e2}", 'aviso')
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
                f'?keywords={quote(termo)}'
                f'&page={pagina}'
            )
            self._log(f"Buscando: \"{termo}\" (página {pagina})...")
            await self.page.goto(url, wait_until='domcontentloaded')
            await asyncio.sleep(random.uniform(2, 4))

            # Detecta checkpoint / muro de login após navegação
            cur_url = self.page.url
            if '/checkpoint' in cur_url or '/login' in cur_url or '/authwall' in cur_url:
                self._log(
                    "Sessão expirada — tentando re-login...", 'aviso'
                )
                self.conectado = False
                ok = await self.fazer_login()
                if not ok:
                    self._log("Re-login falhou — abortando busca", 'erro')
                    return resultados
                # Tenta a busca novamente após re-login
                await self.page.goto(url, wait_until='domcontentloaded')
                await asyncio.sleep(random.uniform(2, 4))

            # Scroll progressivo para carregar lazy items
            for scroll_y in [400, 800, 1200, 1800]:
                await self.page.evaluate(f'window.scrollTo(0, {scroll_y})')
                await asyncio.sleep(0.5)
            await asyncio.sleep(1)

            # Extração: innerText do card <a> externo
            perfis_data = await self.page.evaluate("""() => {
                try {
                const allLinks = [...document.querySelectorAll('a[href*="/in/"]')];
                const seen = new Set();
                const results = [];

                const noise = [
                    'conexão em comum', 'conexões em comum',
                    'mutual connection', 'mutual connections',
                    '1st', '2nd', '3rd', '1º', '2º', '3º',
                    'connect', 'conectar', 'follow', 'seguir',
                    'message', 'mensagem', 'pending', 'pendente',
                    'send inmail', 'enviar inmail',
                    'e mais', 'and more', 'ver mais', 'see more',
                    'view profile', 'ver perfil', 'linkedin member',
                    'grau de conexão', 'degree connection',
                    'pular para', 'skip to', 'conteúdo principal',
                    'notificação', 'notification', 'premium',
                    'open to work', 'aberto a', 'hiring',
                    'currículo', 'resume', 'salvar', 'save',
                ];
                const isNoise = (t) => {
                    if (!t || t.length < 4 || /^\\d+$/.test(t)) return true;
                    const tl = t.toLowerCase();
                    if (/^\\d+\\s*(conex|connect|follower|seguidor)/i.test(tl)) return true;
                    return noise.some(n => tl.includes(n));
                };

                const allNames = new Set();
                for (const a of allLinks) {
                    const s = a.querySelector('span[aria-hidden="true"]');
                    const n = (s ? s.textContent : a.textContent || '').trim();
                    if (n && n.length > 2 && n !== 'LinkedIn Member') allNames.add(n.toLowerCase());
                }

                let debugCount = 0;

                for (const link of allLinks) {
                    const href = link.href.split('?')[0];
                    if (seen.has(href)) continue;
                    if (href.includes('/in/me/') || href.includes('/in/miniprofile')) continue;
                    const rect = link.getBoundingClientRect();
                    if (rect.height < 10 || rect.top < 50) continue;
                    seen.add(href);

                    let nome = '';
                    const ariaSpan = link.querySelector('span[aria-hidden="true"]');
                    if (ariaSpan) nome = ariaSpan.textContent.trim();
                    if (!nome) nome = link.textContent.trim();
                    nome = nome.replace(/\\n/g, ' ').replace(/\\s+/g, ' ').trim();
                    if (!nome || nome === 'LinkedIn Member' || nome.length > 80) continue;

                    let cargo = '';
                    let empresa = '';
                    const nomeLower = nome.toLowerCase();
                    const wantDebug = debugCount < 2;
                    const debugInfo = [];

                    // Sobe até achar o <a> externo que envolve o card inteiro
                    let outerA = link.parentElement;
                    while (outerA) {
                        if (outerA.tagName === 'A' && outerA !== link) break;
                        if (outerA.tagName === 'BODY' || outerA.id === 'root') {
                            outerA = null;
                            break;
                        }
                        outerA = outerA.parentElement;
                    }

                    // Pega TODO o texto visível do card via innerText
                    const cardEl = outerA || link.parentElement;
                    const cardText = (cardEl.innerText || '').trim();
                    const lines = cardText.split('\\n')
                        .map(l => l.trim())
                        .filter(l => l.length >= 3);

                    if (wantDebug) {
                        debugInfo.push('outerA=' + (outerA ? outerA.tagName : 'null'));
                        debugInfo.push('lines=' + JSON.stringify(lines.slice(0, 10)));
                    }

                    // Filtra linhas: remove nome, noise, nomes de outras pessoas
                    const useful = [];
                    for (const line of lines) {
                        const ll = line.toLowerCase();
                        if (isNoise(line)) continue;
                        if (allNames.has(ll)) continue;
                        if (ll === nomeLower) continue;
                        if (nomeLower.includes(ll) && ll.length < nomeLower.length) continue;
                        if (ll.includes(nomeLower) && nomeLower.length > 4) continue;
                        if (line.length <= 3) continue;
                        useful.push(line);
                    }

                    if (wantDebug) {
                        debugInfo.push('useful=' + JSON.stringify(useful.slice(0, 5)));
                    }

                    if (useful.length >= 1) cargo = useful[0];
                    if (useful.length >= 2) empresa = useful[1];

                    // Limpa
                    cargo = (cargo || '').replace(/^Cargo atual:\\s*/i, '').replace(/^Current:\\s*/i, '').trim();
                    empresa = (empresa || '').replace(/^Empresa atual:\\s*/i, '').trim();
                    if (cargo.length > 120) cargo = cargo.substring(0, 120);
                    if (empresa.length > 120) empresa = empresa.substring(0, 120);

                    const r = { nome, cargo, empresa, url: href };
                    if (wantDebug) {
                        r._debug = debugInfo;
                        debugCount++;
                    }
                    results.push(r);
                }
                return results.slice(0, 15);
                } catch(err) {
                    return [{_error: err.message, _stack: (err.stack||'').substring(0, 300)}];
                }
            }""")

            n_total = len(perfis_data or [])

            # Check for JS error
            if n_total == 1 and perfis_data[0].get('_error'):
                self._log(f"  [JS-ERROR] {perfis_data[0]['_error']}", 'erro')
                self._log(f"  [JS-STACK] {perfis_data[0].get('_stack','')}", 'erro')
                perfis_data = []
                n_total = 0

            self._log(f"  {n_total} perfis encontrados na página")

            # Debug inline
            if n_total > 0:
                for p in perfis_data[:2]:
                    if p.get('_debug'):
                        self._log(f"  [dbg] {p['nome']}", 'aviso')
                        for d in p['_debug']:
                            self._log(f"    {d}", 'aviso')
                    if not p.get('cargo'):
                        self._log(f"  [sem-cargo] {p['nome']}", 'aviso')

            # Debug: se 0 resultados, investigar estrutura da página
            if n_total == 0:
                cur = self.page.url
                self._log(f"  [debug] URL atual: {cur}", 'aviso')
                debug_info = await self.page.evaluate("""() => {
                    const body = document.body?.innerText || '';
                    if (body.includes('No results found') || body.includes('nenhum resultado'))
                        return {status: 'no_results'};
                    if (body.includes('Sign in') || body.includes('Entrar'))
                        return {status: 'login_wall'};

                    // Mapear links /in/ na página
                    const inLinks = [...document.querySelectorAll('a[href*="/in/"]')];
                    const inHrefs = inLinks.slice(0, 5).map(a => a.href.split('?')[0]);

                    // Encontrar containers dos resultados
                    const allLi = [...document.querySelectorAll('li')];
                    const liWithIn = allLi.filter(li => li.querySelector('a[href*="/in/"]'));

                    // Classes dos li que contêm links /in/
                    const liClasses = liWithIn.slice(0, 3).map(li => li.className.substring(0, 120));

                    // Verificar se há div container de resultados
                    const mainDiv = document.querySelector('div.search-results-container')
                        || document.querySelector('[class*="search-results"]')
                        || document.querySelector('main');
                    const mainClass = mainDiv?.className?.substring(0, 120) || 'nenhum';

                    return {
                        status: 'loaded',
                        total_li: allLi.length,
                        li_with_in_links: liWithIn.length,
                        in_hrefs: inHrefs,
                        li_classes: liClasses,
                        main_container: mainClass,
                    };
                }""")
                self._log(f"  [debug] {debug_info}", 'aviso')

            # Log primeiros perfis para debug de cargo
            if perfis_data and n_total > 0:
                amostra = perfis_data[:3]
                for p in amostra:
                    self._log(
                        f"  [amostra] {p.get('nome','')} | "
                        f"cargo=\"{p.get('cargo','')}\" | "
                        f"emp=\"{p.get('empresa','')}\"",
                        'info'
                    )

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
    # SALES NAVIGATOR — Busca avançada
    # =========================================================================

    async def _verificar_sales_nav(self) -> bool:
        """Verifica se a conta tem acesso ao Sales Navigator."""
        try:
            await self.page.goto(
                f'{LINKEDIN_URL}/sales/home',
                wait_until='domcontentloaded'
            )
            await asyncio.sleep(random.uniform(2, 4))
            url = self.page.url
            if '/sales/' in url and '/login' not in url:
                self._log("Sales Navigator ativo — conta com acesso", 'sucesso')
                return True
            self._log(
                "Sales Navigator não disponível nesta conta — "
                "usando busca padrão", 'aviso'
            )
            return False
        except Exception as e:
            self._log(f"Erro verificando Sales Nav: {e}", 'aviso')
            return False

    async def buscar_sales_nav(self, termo: str, pagina: int = 1) -> list[dict]:
        """
        Busca leads usando LinkedIn Sales Navigator.
        Filtros avançados: título, indústria, região, porte.
        Retorna lista de dicts com nome, cargo, empresa, url_perfil.
        """
        resultados = []
        try:
            # Monta URL do Sales Navigator com keyword
            url = (
                f'{LINKEDIN_URL}/sales/search/people/'
                f'?query=(keywords:{quote(termo)})'
                f'&page={pagina}'
            )
            self._log(f"[Sales Nav] Buscando: \"{termo}\" (pág {pagina})...")
            await self.page.goto(url, wait_until='domcontentloaded')
            await asyncio.sleep(random.uniform(3, 5))

            # Detecta se caiu fora do Sales Nav (sessão / sem acesso)
            cur_url = self.page.url
            if '/login' in cur_url or '/authwall' in cur_url:
                self._log("[Sales Nav] Sessão expirada — re-login...", 'aviso')
                self.conectado = False
                ok = await self.fazer_login()
                if not ok:
                    return resultados
                await self.page.goto(url, wait_until='domcontentloaded')
                await asyncio.sleep(random.uniform(3, 5))

            if '/sales/' not in self.page.url:
                self._log("[Sales Nav] Redirecionado para fora — sem acesso", 'aviso')
                return resultados

            # Scroll para carregar resultados
            for scroll_y in [400, 800, 1200]:
                await self.page.evaluate(f'window.scrollTo(0, {scroll_y})')
                await asyncio.sleep(0.5)

            # Extrai dados dos resultados — seletores Sales Navigator
            perfis_data = await self.page.evaluate("""() => {
                const results = [];

                // Estratégias de seletor para Sales Navigator
                // (LinkedIn muda frequentemente — múltiplos fallbacks)
                const strats = [
                    // Estratégia 1: seletores modernos do Sales Nav
                    () => [...document.querySelectorAll(
                        'li.artdeco-list__item[class*="search-results"],' +
                        'li[class*="search-results__result-item"],' +
                        'ol.search-results-container > li'
                    )],
                    // Estratégia 2: cards genéricos do Sales Nav
                    () => [...document.querySelectorAll(
                        'div[data-x--search-result],' +
                        '[class*="search-result__wrapper"],' +
                        '[class*="result-lockup"]'
                    )],
                    // Estratégia 3: lockup entities
                    () => [...document.querySelectorAll(
                        '.artdeco-entity-lockup,' +
                        '[class*="entity-lockup"]'
                    )].filter(el =>
                        el.querySelector('a[href*="/sales/lead/"]') ||
                        el.querySelector('a[href*="/sales/people/"]')
                    ),
                    // Estratégia 4: qualquer li com link de lead
                    () => [...document.querySelectorAll('li')]
                        .filter(li => {
                            const a = li.querySelector(
                                'a[href*="/sales/lead/"],' +
                                'a[href*="/sales/people/"]'
                            );
                            return a && li.offsetHeight > 50;
                        }),
                ];

                let cards = [];
                for (const s of strats) {
                    cards = s();
                    if (cards.length > 0) break;
                }

                for (const card of cards.slice(0, 15)) {
                    // Nome
                    let nome = '';
                    for (const sel of [
                        '[data-anonymize="person-name"]',
                        '.artdeco-entity-lockup__title a',
                        'a[href*="/sales/lead/"] span',
                        'a[href*="/sales/people/"] span',
                        '.result-lockup__name a',
                    ]) {
                        const el = card.querySelector(sel);
                        if (el) { nome = el.textContent.trim(); break; }
                    }

                    // Cargo/título
                    let cargo = '';
                    for (const sel of [
                        '[data-anonymize="title"]',
                        '.artdeco-entity-lockup__subtitle',
                        '.result-lockup__highlight-keyword',
                        '[class*="entity-lockup__subtitle"]',
                    ]) {
                        const el = card.querySelector(sel);
                        if (el) { cargo = el.textContent.trim(); break; }
                    }

                    // Empresa
                    let empresa = '';
                    for (const sel of [
                        '[data-anonymize="company-name"]',
                        '.artdeco-entity-lockup__caption a',
                        '.result-lockup__position-company a',
                        '[class*="entity-lockup__caption"] a',
                    ]) {
                        const el = card.querySelector(sel);
                        if (el) { empresa = el.textContent.trim(); break; }
                    }

                    // URL do perfil (Sales Nav → regular LinkedIn)
                    let url = '';
                    const linkEl = card.querySelector(
                        'a[href*="/sales/lead/"],' +
                        'a[href*="/sales/people/"],' +
                        'a[href*="/in/"]'
                    );
                    if (linkEl) {
                        url = linkEl.href.split('?')[0];
                    }

                    if (nome && nome !== 'LinkedIn Member') {
                        results.push({ nome, cargo, empresa, url });
                    }
                }
                return results;
            }""")

            n_total = len(perfis_data or [])
            self._log(f"  [Sales Nav] {n_total} perfis na página")

            for p in (perfis_data or []):
                nome = (p.get('nome') or '').strip()
                cargo = (p.get('cargo') or '').strip()
                empresa = (p.get('empresa') or '').strip()
                url_p = (p.get('url') or '').strip()

                if not nome:
                    continue
                if not self._cargo_alvo(cargo):
                    continue

                # Converte URL Sales Nav para URL regular se possível
                if '/sales/lead/' in url_p or '/sales/people/' in url_p:
                    url_regular = await self._sales_nav_to_regular_url(url_p)
                    if url_regular:
                        url_p = url_regular

                self._log(f"  → [SN] {nome} | {cargo} @ {empresa}")
                resultados.append({
                    'nome': nome,
                    'cargo': cargo,
                    'empresa': empresa,
                    'url_perfil': url_p,
                    'termo_busca': f'[SalesNav] {termo}',
                    'fonte': 'sales_navigator',
                })

            self._log(
                f"[Sales Nav] {len(resultados)} leads qualificados de {n_total}"
            )
        except Exception as e:
            self._log(f"[Sales Nav] Erro na busca: {e}", 'erro')
        return resultados

    async def _sales_nav_to_regular_url(self, sales_url: str) -> str:
        """
        Tenta extrair URL regular do perfil a partir do Sales Navigator.
        Sales Nav URLs contêm o ID do lead, não o vanity URL.
        """
        try:
            # Abre o perfil Sales Nav em outra aba para pegar o vanity URL
            # Mas para não sobrecarregar, usamos a URL Sales Nav mesmo
            # O bot vai navegar para o perfil real quando for enviar conexão
            return sales_url
        except Exception:
            return sales_url

    async def _navegar_perfil_para_conexao(self, url: str) -> str:
        """
        Se a URL é do Sales Navigator, navega até o perfil regular.
        Retorna a URL regular do perfil.
        """
        if '/sales/lead/' not in url and '/sales/people/' not in url:
            return url  # Já é URL regular

        try:
            await self.page.goto(url, wait_until='domcontentloaded')
            await asyncio.sleep(random.uniform(2, 4))

            # No Sales Nav, procura link "Ver perfil no LinkedIn"
            link_regular = await self.page.evaluate("""() => {
                // Botão/link para perfil regular
                const sels = [
                    'a[href*="linkedin.com/in/"]',
                    'a[data-control-name="view_linkedin"]',
                    '[class*="view-linkedin"] a',
                    'a[aria-label*="LinkedIn"]',
                ];
                for (const sel of sels) {
                    const el = document.querySelector(sel);
                    if (el && el.href && el.href.includes('/in/')) {
                        return el.href.split('?')[0];
                    }
                }
                return '';
            }""")

            if link_regular:
                self._log(f"  Perfil regular encontrado: {link_regular}")
                return link_regular

            # Se não encontrou link direto, tenta o vanity URL do cabeçalho
            return url
        except Exception as e:
            self._log(f"  Erro navegando perfil Sales Nav: {e}", 'aviso')
            return url

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
            # Se URL é do Sales Navigator, navega para perfil regular primeiro
            if '/sales/lead/' in url or '/sales/people/' in url:
                url = await self._navegar_perfil_para_conexao(url)
                perfil['url_perfil'] = url  # atualiza para salvar no DB

            await self.page.goto(url, wait_until='domcontentloaded')
            await asyncio.sleep(random.uniform(2, 4))

            # Botão "Conectar" — suporta LinkedIn regular e Sales Navigator
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

            # Scroll até o botão e clica
            await conectar_btn.scroll_into_view_if_needed()
            await asyncio.sleep(0.5)
            try:
                await conectar_btn.click(timeout=10000)
            except Exception:
                # Fallback: JS click se elemento coberto por overlay
                await self.page.evaluate("el => el.click()", conectar_btn)
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
                def _chamar_ai():
                    return self.ai.messages.create(
                        model='claude-haiku-4-5-20251001',
                        max_tokens=80,
                        system=(
                            "Escreva uma nota CURTA (max 180 chars) de pedido "
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
                r = await asyncio.to_thread(_chamar_ai)
                nota = r.content[0].text.strip()
                return nota[:200]  # LinkedIn limita a 200 chars
            except Exception:
                pass

        # Fallback
        return (
            f"Oi {nome}, vi que você atua em {cargo} na {empresa}. "
            "Trabalho com gestão da qualidade e acredito que posso "
            "agregar. Vamos conectar?"
        )[:200]

    # =========================================================================
    # ENVIAR DM PÓS-CONEXÃO
    # =========================================================================

    async def _obter_threads_inbox(self) -> list:
        """Navega pro inbox e retorna lista de threads com retry."""
        SELETORES_THREAD = [
            'li.msg-conversation-listitem',
            'li[class*="msg-conversation"]',
            '[data-control-name="conversation"]',
        ]
        for tentativa in range(2):
            try:
                await self.page.goto(
                    f'{LINKEDIN_URL}/messaging/',
                    wait_until='domcontentloaded',
                    timeout=15000)
                await asyncio.sleep(random.uniform(2, 4))
                # Espera pelo menos 1 thread aparecer
                for sel in SELETORES_THREAD:
                    try:
                        await self.page.wait_for_selector(
                            sel, timeout=5000)
                        threads = await self.page.query_selector_all(sel)
                        if threads:
                            return threads
                    except Exception:
                        continue
            except Exception as e:
                self._log(
                    f"Erro ao abrir inbox (tentativa {tentativa + 1}): "
                    f"{type(e).__name__}", 'aviso')
                await asyncio.sleep(3)
        return []

    async def _extrair_preview_thread(self, thread) -> str:
        """Extrai texto de preview de um thread com tratamento de erro."""
        try:
            return await thread.evaluate("""el => {
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
        except Exception:
            return ''

    async def _extrair_nome_conversa(self) -> str:
        """Extrai nome do contato na conversa aberta."""
        try:
            return await self.page.evaluate("""() => {
                const sels = [
                    '.msg-entity-lockup__entity-title',
                    '[class*="entity-title"]',
                    '.msg-thread-top-bar h2',
                    'h2[class*="conversation"] span',
                    '.msg-overlay-bubble-header__title',
                ];
                for (const s of sels) {
                    const e = document.querySelector(s);
                    if (e && e.textContent.trim()) return e.textContent.trim();
                }
                return '';
            }""")
        except Exception:
            return ''

    async def _clicar_thread_e_esperar(self, thread) -> bool:
        """Clica num thread e espera a conversa carregar."""
        try:
            await thread.click()
            # Espera painel de conversa abrir
            try:
                await self.page.wait_for_selector(
                    '.msg-s-message-list-content, '
                    '[class*="message-list"], '
                    'div.msg-form__contenteditable, '
                    'div[contenteditable="true"][role="textbox"]',
                    timeout=5000)
            except Exception:
                await asyncio.sleep(2)
            await asyncio.sleep(random.uniform(0.5, 1.5))
            return True
        except Exception as e:
            self._log(f"Erro ao abrir thread: {type(e).__name__}", 'aviso')
            return False

    def _leads_aguardando_dm(self) -> list[dict]:
        """Retorna leads com conexão enviada/aceita que ainda não receberam DM."""
        try:
            if not HAS_DB:
                return []
            conn = get_connection()
            c = conn.cursor()
            c.execute(
                "SELECT nome, url_perfil FROM leads_linkedin "
                "WHERE status IN ('conexao_enviada', 'conectado') "
                "AND dm_enviada_em IS NULL "
                "AND conexao_em IS NOT NULL "
                "ORDER BY conexao_em DESC "
                "LIMIT 10"
            )
            rows = list(c.fetchall())
            conn.close()
            return rows
        except Exception:
            return []

    async def enviar_dm_novos_contatos(self):
        """
        Busca leads do BANCO que tiveram conexão enviada mas ainda não
        receberam DM. Abre o perfil, clica em "Mensagem" e envia pitch.
        NÃO itera threads do inbox — só contata leads prospectados pelo bot.
        """
        if self.msgs_hoje >= LINKEDIN_MAX_MENSAGENS_DIA:
            return

        leads_pendentes = self._leads_aguardando_dm()
        if not leads_pendentes:
            self._log("Nenhum lead aguardando DM")
            return

        self._log(
            f"{len(leads_pendentes)} leads aguardando DM — verificando..."
        )

        enviadas = 0
        for lead in leads_pendentes:
            if self.msgs_hoje >= LINKEDIN_MAX_MENSAGENS_DIA:
                self._log("Limite de DMs do dia atingido", 'aviso')
                break

            nome = lead.get('nome', 'contato')
            url_perfil = lead.get('url_perfil', '')
            if not url_perfil:
                continue

            try:
                # Abre o perfil do lead
                await self.page.goto(
                    url_perfil, wait_until='domcontentloaded', timeout=15000
                )
                await asyncio.sleep(random.uniform(2, 4))

                # Verifica se somos conectados (botão "Mensagem" visível)
                msg_btn = await self.page.query_selector(
                    'button:has-text("Mensagem"), '
                    'button:has-text("Message"), '
                    'a[href*="/messaging/thread/"]'
                )
                if not msg_btn:
                    self._log(
                        f"  ⏭ {nome} — sem botão Mensagem (não aceitou ainda)")
                    continue

                # Clica no botão Mensagem para abrir chat
                await msg_btn.click()
                await asyncio.sleep(random.uniform(2, 3))

                # Espera caixa de mensagem carregar
                try:
                    await self.page.wait_for_selector(
                        'div.msg-form__contenteditable, '
                        'div[contenteditable="true"][role="textbox"]',
                        timeout=8000
                    )
                except Exception:
                    self._log(
                        f"  ⏭ {nome} — caixa de msg não carregou", 'aviso')
                    continue

                # Verifica se já enviamos msg nesta conversa
                try:
                    tem_outgoing = await self.page.evaluate("""() => {
                        const out = document.querySelectorAll(
                            '[class*="msg-s-message-group--outgoing"], '
                            + '[class*="outgoing"]'
                        );
                        return out.length > 0;
                    }""")
                    if tem_outgoing:
                        self._log(f"  ⏭ {nome} — já enviamos msg")
                        # Atualiza DB para não tentar de novo
                        if HAS_DB:
                            try:
                                salvar_lead_linkedin(
                                    {'nome': nome, 'url_perfil': url_perfil},
                                    'dm_enviada'
                                )
                            except Exception:
                                pass
                        continue
                except Exception:
                    pass

                self._log(f"  Enviando DM inicial para {nome}...")
                msg = self._gerar_dm_inicial(nome)
                ok = await self._digitar_e_enviar(msg)
                if not ok:
                    self._log(
                        f"  ✗ Falha ao enviar DM para {nome}", 'aviso')
                    continue
                self.msgs_hoje += 1
                enviadas += 1
                if HAS_DB:
                    try:
                        salvar_lead_linkedin(
                            {'nome': nome, 'url_perfil': url_perfil},
                            'dm_enviada'
                        )
                    except Exception:
                        pass
                self._log(
                    f"  ✓ DM #{self.msgs_hoje}/{LINKEDIN_MAX_MENSAGENS_DIA} "
                    f"enviada para {nome}",
                    'sucesso'
                )
                await asyncio.sleep(random.uniform(30, 60))
            except Exception as e:
                self._log(
                    f"  Erro DM {nome}: {type(e).__name__}: {e}",
                    'aviso')
                continue

        if enviadas == 0:
            self._log("Nenhuma DM pendente enviada neste ciclo")

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

    async def _digitar_e_enviar(self, texto: str, retries: int = 3) -> bool:
        """Digita e envia msg. Tenta múltiplos seletores com retry."""
        SELETORES_CAIXA = [
            'div.msg-form__contenteditable',
            'div[contenteditable="true"][role="textbox"]',
            'div.msg-form__msg-content-container div[contenteditable]',
            'form.msg-form div[contenteditable="true"]',
            'div[contenteditable="true"]',
        ]
        for tentativa in range(retries):
            caixa = None
            for sel in SELETORES_CAIXA:
                try:
                    caixa = await self.page.wait_for_selector(
                        sel, timeout=3000, state='visible')
                    if caixa:
                        break
                except Exception:
                    continue
            if not caixa:
                if tentativa < retries - 1:
                    self._log(
                        f"Caixa de msg não encontrada (tentativa "
                        f"{tentativa + 1}/{retries}), aguardando...", 'aviso')
                    await asyncio.sleep(2)
                    continue
                self._log("Caixa de mensagem não encontrada após retries", 'aviso')
                return False
            try:
                await caixa.click()
                await asyncio.sleep(0.3)
                for linha in texto.split('\n'):
                    await caixa.type(linha, delay=random.randint(20, 60))
                    await self.page.keyboard.press('Shift+Enter')
                await self.page.keyboard.press('Backspace')
                await asyncio.sleep(0.5)
                # Tenta botão Enviar primeiro, fallback Enter
                send_btn = await self.page.query_selector(
                    'button.msg-form__send-button, '
                    'button[type="submit"].msg-form__send-btn, '
                    'button.msg-form__send-btn')
                if send_btn and await send_btn.is_enabled():
                    await send_btn.click()
                else:
                    await self.page.keyboard.press('Enter')
                await asyncio.sleep(random.uniform(1, 2))
                return True
            except Exception as e:
                self._log(f"Erro ao digitar/enviar (tentativa "
                          f"{tentativa + 1}): {e}", 'aviso')
                await asyncio.sleep(1)
        return False

    # =========================================================================
    # MONITORAR INBOX — RESPOSTAS DOS LEADS
    # =========================================================================

    def _nomes_leads_banco(self) -> set:
        """Retorna nomes (lowercase) de leads prospectados pelo bot."""
        try:
            if not HAS_DB:
                return set()
            conn = get_connection()
            c = conn.cursor()
            c.execute("SELECT LOWER(nome) AS n FROM leads_linkedin")
            nomes = {r['n'] for r in c.fetchall() if r['n']}
            conn.close()
            return nomes
        except Exception:
            return set()

    async def monitorar_inbox(self):
        """
        Varre o inbox buscando respostas APENAS de leads do banco.
        Ignora conversas pessoais ou de contatos não prospectados.
        """
        if self.msgs_hoje >= LINKEDIN_MAX_MENSAGENS_DIA:
            return
        try:
            # Carrega nomes de leads do banco para filtrar
            nomes_db = self._nomes_leads_banco()
            if not nomes_db:
                self._log("Nenhum lead no banco — pulando inbox")
                return

            threads = await self._obter_threads_inbox()
            if not threads:
                self._log("Inbox vazio ou não carregou")
                return

            self._log(f"Monitorando inbox: {len(threads)} threads")

            replies = 0
            for thread in threads[:20]:
                try:
                    preview = await self._extrair_preview_thread(thread)

                    # Pula se última msg foi nossa ou vazia
                    if preview.startswith('Você:') or not preview:
                        continue

                    if not await self._clicar_thread_e_esperar(thread):
                        continue

                    nome = await self._extrair_nome_conversa()
                    if not nome:
                        nome = 'contato'

                    # SÓ responde se o nome corresponde a um lead do banco
                    nome_lower = nome.lower().strip()
                    if not any(n in nome_lower or nome_lower in n
                               for n in nomes_db):
                        continue

                    self._log(
                        f"  Resposta de {nome}: "
                        f"\"{preview[:70]}\"")

                    historico = await self._ler_conversa()
                    if not historico:
                        self._log(
                            f"  Sem histórico para {nome}", 'aviso')
                        continue

                    ultima = historico[-1]
                    if ultima.get('de_nos'):
                        continue

                    msg_hash = hash(ultima.get('texto', ''))
                    if msg_hash in self._msgs_respondidas:
                        self._log(
                            "  (já respondido nesta sessão)")
                        continue

                    self._log(f"  Gerando reply IA para {nome}...")
                    resposta = await self._gerar_resposta_inbox(
                        nome, historico)
                    if not resposta:
                        self._log(
                            f"  IA não gerou resposta para {nome}",
                            'aviso')
                        continue

                    ok = await self._digitar_e_enviar(resposta)
                    if not ok:
                        self._log(
                            f"  ✗ Falha ao enviar reply para {nome}",
                            'aviso')
                        continue
                    self.msgs_hoje += 1
                    replies += 1
                    self._msgs_respondidas.add(msg_hash)
                    self._log(
                        f"  ✓ Reply para {nome}: "
                        f"\"{resposta[:60]}...\"",
                        'sucesso')
                    self._atualizar_resposta_db(
                        nome, ultima['texto'])

                    if self.msgs_hoje >= LINKEDIN_MAX_MENSAGENS_DIA:
                        self._log(
                            "Limite de DMs do dia atingido", 'aviso')
                        break
                    await asyncio.sleep(random.uniform(20, 40))

                except Exception as e:
                    self._log(
                        f"  Erro em thread inbox: "
                        f"{type(e).__name__}: {e}", 'aviso')
                    continue

            if replies == 0:
                self._log("Nenhuma resposta pendente no inbox")

        except Exception as e:
            self._log(
                f"Erro no monitoramento do inbox: {e}", 'erro')

    async def _ler_conversa(self, retries: int = 2) -> list[dict]:
        """
        Extrai histórico de mensagens do thread aberto.
        Tenta múltiplas estratégias: JS evaluate e fallback Playwright.
        Retorna lista de dicts: {texto: str, de_nos: bool}
        """
        for tentativa in range(retries):
            # Espera container de mensagens carregar
            try:
                await self.page.wait_for_selector(
                    '.msg-s-message-list-content, '
                    '[class*="message-list"], '
                    '[class*="msg-thread"]',
                    timeout=5000)
            except Exception:
                await asyncio.sleep(2)

            # Estratégia 1: JS evaluate (rápido)
            try:
                dados = await self.page.evaluate("""() => {
                    // Estratégia A: seletores novos
                    let groups = [...document.querySelectorAll(
                        '[class*="message-group"]'
                    )];
                    if (groups.length) {
                        return groups.map(g => ({
                            de_nos: (
                                g.className.includes('outgoing') ||
                                g.getAttribute('data-outgoing') === 'true'
                            ),
                            texto: [...g.querySelectorAll(
                                '[class*="message-body"], '
                                + '[class*="msg-s-event"], '
                                + 'p.msg-s-event-listitem__body'
                            )].map(b => b.textContent.trim())
                              .filter(Boolean).join(' ')
                        })).filter(m => m.texto.length > 0);
                    }
                    // Estratégia B: seletores antigos
                    groups = [...document.querySelectorAll(
                        '.msg-s-message-group'
                    )];
                    if (groups.length) {
                        return groups.map(g => ({
                            de_nos: g.classList.contains(
                                'msg-s-message-group--outgoing'
                            ),
                            texto: [...g.querySelectorAll(
                                '.msg-s-event-listitem__body'
                            )].map(b => b.textContent.trim())
                              .filter(Boolean).join(' ')
                        })).filter(m => m.texto.length > 0);
                    }
                    // Estratégia C: qualquer parágrafo na thread
                    const msgs = [...document.querySelectorAll(
                        '.msg-s-event-listitem, [class*="msg-event"]'
                    )];
                    return msgs.map(el => ({
                        de_nos: !!(el.closest('[class*="outgoing"]')),
                        texto: el.textContent.trim()
                    })).filter(m => m.texto.length > 0);
                }""")
                if dados and len(dados) > 0:
                    return dados
            except Exception as e:
                self._log(
                    f"Erro JS ao ler conversa (tentativa "
                    f"{tentativa + 1}): {type(e).__name__}", 'aviso')

            # Estratégia 2: Fallback Playwright (mais lento, mais robusto)
            try:
                items = await self.page.query_selector_all(
                    '.msg-s-event-listitem, [class*="msg-event"]')
                if items:
                    result = []
                    for item in items:
                        txt = (await item.text_content() or '').strip()
                        if not txt:
                            continue
                        parent = await item.evaluate_handle(
                            'el => el.closest("[class*=outgoing]")')
                        de_nos = bool(parent and str(parent) != 'null'
                                      and str(parent) != 'JSHandle@null')
                        result.append({'texto': txt, 'de_nos': de_nos})
                    if result:
                        return result
            except Exception as e:
                self._log(
                    f"Erro fallback ler conversa: {type(e).__name__}",
                    'aviso')

            await asyncio.sleep(1)

        self._log("Não conseguiu ler conversa após retries", 'aviso')
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
                cal = DEMO_CAL_LINK

                def _chamar_ai():
                    return self.ai.messages.create(
                        model='claude-haiku-4-5-20251001',
                        max_tokens=150,
                        system=(
                            "Você é Daniel, vendedor do PrismaBiz — sistema de "
                            "gestão da qualidade com Auditoria, Plano de Ação, "
                            "SWOT, PDCA e mais 7 módulos, todos 100% gratuitos. "
                            f"Link para demo: {cal}\n"
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
                r = await asyncio.to_thread(_chamar_ai)
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
            # Usa nome completo (exato) para evitar atualizar leads errados
            c.execute(
                """UPDATE leads_linkedin
                   SET respondeu = 1, ultima_resposta = %s
                   WHERE LOWER(nome) = LOWER(%s)
                   AND respondeu = 0""",
                (ultima_msg[:500], nome.strip())
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    # =========================================================================
    # LOOP PRINCIPAL
    # =========================================================================

    async def executar(self):
        """
        Loop contínuo multi-source:
        Alterna entre LinkedIn Search, Sales Navigator e Apollo.io
        Ciclo: busca → conecta → dm → inbox
        """
        ok = await self.fazer_login()
        if not ok:
            self._log(
                "Não foi possível logar no LinkedIn. Abortando.",
                'erro'
            )
            return

        # Verifica Sales Navigator (1x no início)
        if SALES_NAV_HABILITADO and self._sales_nav_disponivel is None:
            self._sales_nav_disponivel = await self._verificar_sales_nav()
            # Volta pro feed depois de verificar
            await self.page.goto(
                f'{LINKEDIN_URL}/feed/',
                wait_until='domcontentloaded'
            )
            await asyncio.sleep(2)

        # Inicializa Apollo.io
        apollo = None
        try:
            from apollo_client import ApolloClient
            apollo = ApolloClient()
            if apollo.disponivel():
                self._log(
                    "Apollo.io ativo — enriquecimento habilitado",
                    'sucesso'
                )
            else:
                self._log("Apollo.io não configurado — pulando")
                apollo = None
        except ImportError:
            self._log("Apollo client não encontrado — pulando")

        # Fontes de busca disponíveis
        fontes = ['linkedin']
        if self._sales_nav_disponivel:
            fontes.append('sales_nav')
        if apollo:
            fontes.append('apollo')

        self._log(
            f"LinkedIn bot Prisma ativo — "
            f"max {LINKEDIN_MAX_CONEXOES_DIA} conexões/dia, "
            f"{LINKEDIN_MAX_MENSAGENS_DIA} DMs/dia | "
            f"Fontes: {', '.join(fontes)}",
            'sucesso'
        )

        # Termos de busca por fonte
        termos_li = LINKEDIN_TERMOS_BUSCA.copy()
        random.shuffle(termos_li)
        termos_sn = SALES_NAV_TERMOS.copy() if self._sales_nav_disponivel else []
        random.shuffle(termos_sn)

        termo_idx_li = 0
        termo_idx_sn = 0
        termo_idx_apollo = 0

        while True:
            try:
                now = datetime.now(_BRT)

                # Reset diário (quando muda o dia)
                dia_atual = now.day
                if dia_atual != self._ultimo_dia:
                    self._ultimo_dia = dia_atual
                    if self.conexoes_hoje > 0 or self.msgs_hoje > 0:
                        self.conexoes_hoje = 0
                        self.msgs_hoje = 0
                        self._msgs_respondidas.clear()
                        self._log("Reset diário — contadores zerados")
                    if apollo:
                        apollo.buscas_hoje = 0

                self._ciclo += 1
                # Escolhe fonte deste ciclo (round-robin)
                fonte_idx = (self._ciclo - 1) % len(fontes)
                fonte = fontes[fonte_idx]

                self._log(
                    f"━━━ Ciclo #{self._ciclo} [{fonte.upper()}] "
                    f"| {now.strftime('%H:%M')} BRT "
                    f"| Cx: {self.conexoes_hoje}/"
                    f"{LINKEDIN_MAX_CONEXOES_DIA} "
                    f"| DM: {self.msgs_hoje}/"
                    f"{LINKEDIN_MAX_MENSAGENS_DIA} ━━━"
                )

                # ── Fase 1: busca + conexões ──
                if self.conexoes_hoje < LINKEDIN_MAX_CONEXOES_DIA:
                    leads = []

                    if fonte == 'linkedin':
                        termo = termos_li[termo_idx_li % len(termos_li)]
                        pagina = (termo_idx_li // len(termos_li)) + 1
                        if pagina > 3:
                            pagina = 1
                        termo_idx_li += 1
                        leads = await self.buscar_pessoas(termo, pagina)

                    elif fonte == 'sales_nav' and termos_sn:
                        termo = termos_sn[termo_idx_sn % len(termos_sn)]
                        pagina = (termo_idx_sn // len(termos_sn)) + 1
                        if pagina > 3:
                            pagina = 1
                        termo_idx_sn += 1
                        leads = await self.buscar_sales_nav(termo, pagina)

                    elif fonte == 'apollo' and apollo:
                        # Remove Apollo das fontes se foi desabilitado (plano free)
                        if hasattr(apollo, '_desabilitado') and apollo._desabilitado:
                            fontes = [f for f in fontes if f != 'apollo']
                            apollo = None
                            self._log("Apollo removido das fontes (plano free)")
                            continue
                        from apollo_client import APOLLO_KEYWORDS
                        kws = APOLLO_KEYWORDS
                        kw = kws[termo_idx_apollo % len(kws)]
                        termo_idx_apollo += 1
                        apollo_leads = await apollo.buscar_leads(kw)

                        # Salva leads Apollo no pipeline
                        if apollo_leads:
                            await apollo.salvar_leads_no_pipeline(
                                apollo_leads
                            )
                            # Filtra os que têm URL LinkedIn para conexão
                            leads = [
                                l for l in apollo_leads
                                if l.get('url_perfil')
                            ]
                            # Buffer: leads com telefone para WhatsApp
                            tel_leads = [
                                l for l in apollo_leads
                                if l.get('telefone')
                                and not l.get('url_perfil')
                            ]
                            if tel_leads:
                                self._log(
                                    f"  {len(tel_leads)} leads Apollo "
                                    f"com telefone → pipeline WA"
                                )

                    if leads:
                        self._log(
                            f"Fase 1: {len(leads)} leads [{fonte}] "
                            f"— enviando conexões..."
                        )
                        for lead in leads:
                            if self.conexoes_hoje >= LINKEDIN_MAX_CONEXOES_DIA:
                                self._log(
                                    "Limite de conexões atingido"
                                )
                                break
                            await self.enviar_conexao(lead)
                            pausa = random.randint(45, 120)
                            self._log(
                                f"Aguardando {pausa}s..."
                            )
                            await asyncio.sleep(pausa)
                    else:
                        self._log(
                            f"Fase 1: sem leads [{fonte}] neste ciclo"
                        )
                else:
                    self._log(
                        "Fase 1: limite de conexões atingido — "
                        "pulando busca"
                    )

                # ── Fase 2 e 3: DMs e respostas (horário comercial) ──
                if self._horario_mensagens(now):
                    if self.msgs_hoje < LINKEDIN_MAX_MENSAGENS_DIA:
                        self._log(
                            "Fase 2: DMs para novas conexões..."
                        )
                        await self.enviar_dm_novos_contatos()
                    else:
                        self._log("Fase 2: limite DMs atingido")

                    self._log("Fase 3: monitorando inbox...")
                    await self.monitorar_inbox()
                else:
                    self._log(
                        f"Fase 2-3: fora do horário "
                        f"({HORARIO_INICIO}h-22h) — "
                        f"apenas prospecção"
                    )

                # ── Fase 4: Apollo enriquecimento (a cada 5 ciclos) ──
                if apollo and self._ciclo % 5 == 0:
                    await self._enriquecer_leads_apollo(apollo)

                # Pausa entre ciclos — curta se sem leads, normal se fez algo
                if leads:
                    prox = random.randint(25, 45)
                else:
                    prox = random.randint(8, 15)
                self._log(
                    f"Ciclo #{self._ciclo} OK → próximo ciclo em {prox}s"
                )
                await asyncio.sleep(prox)

            except Exception as e:
                self._log(f"Erro no loop principal: {e}", 'erro')
                await asyncio.sleep(60)

    async def _enriquecer_leads_apollo(self, apollo):
        """Enriquece leads LinkedIn sem email usando Apollo."""
        if not HAS_DB:
            return
        try:
            conn = get_connection()
            c = conn.cursor()
            # Busca leads com URL LinkedIn mas sem email
            c.execute("""
                SELECT id, nome, url_perfil FROM leads_linkedin
                WHERE url_perfil IS NOT NULL
                AND url_perfil != ''
                AND url_perfil NOT LIKE '%%/sales/%%'
                ORDER BY encontrado_em DESC
                LIMIT 5
            """)
            leads = c.fetchall()
            conn.close()

            if not leads:
                return

            self._log(
                f"Enriquecendo {len(leads)} leads via Apollo..."
            )
            for lead in leads:
                url = lead['url_perfil']
                dados = await apollo.enriquecer_lead(
                    linkedin_url=url
                )
                if dados and dados.get('email'):
                    self._log(
                        f"  Enriquecido: {lead['nome']} → "
                        f"{dados['email']}"
                    )
        except Exception as e:
            self._log(f"Erro enriquecimento: {e}", 'aviso')

    def _horario_mensagens(self, now: datetime) -> bool:
        """Retorna True se pode enviar DMs/respostas (seg-sex, 8h-22h BRT)."""
        if now.weekday() not in DIAS_ATIVOS:
            return False
        return HORARIO_INICIO <= now.hour < 22

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
    bot = LinkedInBot()

    async def main():
        try:
            await bot.iniciar()
            await bot.executar()
        finally:
            await bot.fechar()

    asyncio.run(main())
