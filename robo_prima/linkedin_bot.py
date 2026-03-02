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
from datetime import datetime

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
        self.ai = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) \
            if HAS_AI and ANTHROPIC_API_KEY else None

    # =========================================================================
    # SESSÃO
    # =========================================================================

    async def iniciar(self):
        """Abre browser com sessão persistente."""
        import os
        from playwright.async_api import async_playwright

        self._pw = await async_playwright().start()
        os.makedirs(SESSION_DIR, exist_ok=True)

        self.context = await self._pw.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR,
            headless=True,
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
        self._log("LinkedIn bot iniciado")

    async def fechar(self):
        if self.context:
            await self.context.close()
        if self._pw:
            await self._pw.stop()

    # =========================================================================
    # LOGIN
    # =========================================================================

    async def fazer_login(self) -> bool:
        """
        Faz login se não estiver autenticado.
        Retorna True se já estava logado ou logou com sucesso.
        """
        await self.page.goto(
            f'{LINKEDIN_URL}/feed/', wait_until='domcontentloaded'
        )
        await asyncio.sleep(random.uniform(2, 4))

        # Verifica se já está logado (feed carregou)
        if '/feed' in self.page.url or '/in/' in self.page.url:
            self.conectado = True
            self._log("Sessão LinkedIn ativa (sem login necessário)")
            return True

        # Precisa logar
        self._log("Fazendo login no LinkedIn...")
        try:
            await self.page.goto(
                f'{LINKEDIN_URL}/login', wait_until='domcontentloaded'
            )
            await asyncio.sleep(random.uniform(1, 2))

            await self.page.fill('#username', LINKEDIN_EMAIL)
            await asyncio.sleep(random.uniform(0.5, 1.2))
            await self.page.fill('#password', LINKEDIN_PASSWORD)
            await asyncio.sleep(random.uniform(0.5, 1))
            await self.page.press('#password', 'Enter')
            await asyncio.sleep(random.uniform(3, 5))

            if '/feed' in self.page.url or '/checkpoint' in self.page.url:
                self.conectado = True
                self._log("Login LinkedIn OK")
                return True
            else:
                self._log(f"Falha no login — URL: {self.page.url}", 'erro')
                return False
        except Exception as e:
            self._log(f"Erro no login: {e}", 'erro')
            return False

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
            await self.page.goto(url, wait_until='domcontentloaded')
            await asyncio.sleep(random.uniform(2, 4))

            # Scroll para carregar lazy items
            await self.page.evaluate('window.scrollTo(0, 800)')
            await asyncio.sleep(1)

            cards = await self.page.query_selector_all(
                'li.reusable-search__result-container'
            )
            for card in cards[:10]:
                try:
                    nome_el = await card.query_selector(
                        'span.entity-result__title-text a'
                    )
                    cargo_el = await card.query_selector(
                        '.entity-result__primary-subtitle'
                    )
                    empresa_el = await card.query_selector(
                        '.entity-result__secondary-subtitle'
                    )
                    link_el = await card.query_selector(
                        'a.app-aware-link[href*="/in/"]'
                    )

                    nome = (
                        (await nome_el.inner_text()).strip()
                        if nome_el else ''
                    )
                    cargo = (
                        (await cargo_el.inner_text()).strip()
                        if cargo_el else ''
                    )
                    empresa = (await empresa_el.inner_text()).strip() \
                        if empresa_el else ''
                    url = (
                        await link_el.get_attribute('href')
                        if link_el else ''
                    )

                    # Filtra: "LinkedIn Member" = perfil privado, pula
                    if not nome or 'LinkedIn Member' in nome:
                        continue

                    # Verifica se cargo é alvo
                    if not self._cargo_alvo(cargo):
                        continue

                    resultados.append({
                        'nome': nome,
                        'cargo': cargo,
                        'empresa': empresa,
                        'url_perfil': url.split('?')[0] if url else '',
                        'termo_busca': termo,
                    })
                except Exception:
                    continue

            self._log(
                f"Busca '{termo}' p.{pagina}: {len(resultados)} encontrados"
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
                self._log(f"Botão conectar não encontrado: {url}", 'aviso')
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
                    f"Conexao enviada: {perfil['nome']} ({perfil['empresa']})",
                    'sucesso'
                )
                if HAS_DB:
                    salvar_lead_linkedin(perfil, 'conexao_enviada')
                await asyncio.sleep(random.uniform(3, 7))
                return True

        except Exception as e:
            self._log(f"Erro ao conectar {url}: {e}", 'erro')
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
            threads = await self.page.query_selector_all(
                'li.msg-conversation-listitem'
            )
            for thread in threads[:5]:
                try:
                    preview = await thread.query_selector(
                        '.msg-conversation-card__message-snippet'
                    )
                    preview_txt = await preview.inner_text() if preview else ''

                    # Se o preview é da nossa conta, já mandamos — pula
                    # (heurística: se começa com "Você:", já enviamos)
                    if preview_txt.startswith('Você:'):
                        continue

                    await thread.click()
                    await asyncio.sleep(random.uniform(1, 2))

                    nome_el = await self.page.query_selector(
                        '.msg-entity-lockup__entity-title'
                    )
                    nome = (await nome_el.inner_text()).strip() \
                        if nome_el else 'contato'

                    msg = self._gerar_dm_inicial(nome)
                    await self._digitar_e_enviar(msg)
                    self.msgs_hoje += 1
                    self._log(f"DM enviada para {nome}", 'sucesso')

                    if self.msgs_hoje >= LINKEDIN_MAX_MENSAGENS_DIA:
                        break
                    await asyncio.sleep(random.uniform(30, 60))
                except Exception:
                    continue
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
        caixa = await self.page.query_selector(
            'div.msg-form__contenteditable'
        )
        if not caixa:
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

            threads = await self.page.query_selector_all(
                'li.msg-conversation-listitem'
            )
            for thread in threads[:20]:
                try:
                    preview_el = await thread.query_selector(
                        '.msg-conversation-card__message-snippet'
                    )
                    preview = (await preview_el.inner_text()).strip() \
                        if preview_el else ''

                    # Pula se última msg foi nossa ou thread vazia
                    if preview.startswith('Você:') or not preview:
                        continue

                    await thread.click()
                    await asyncio.sleep(random.uniform(1.5, 2.5))

                    nome_el = await self.page.query_selector(
                        '.msg-entity-lockup__entity-title'
                    )
                    nome = (await nome_el.inner_text()).strip() \
                        if nome_el else 'contato'

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
                        continue

                    resposta = await self._gerar_resposta_inbox(
                        nome, historico
                    )
                    if not resposta:
                        continue

                    await self._digitar_e_enviar(resposta)
                    self.msgs_hoje += 1
                    self._msgs_respondidas.add(msg_hash)
                    self._log(
                        f"Reply IA para {nome}: {resposta[:60]}...", 'sucesso'
                    )
                    self._atualizar_resposta_db(nome, ultima['texto'])

                    if self.msgs_hoje >= LINKEDIN_MAX_MENSAGENS_DIA:
                        break
                    await asyncio.sleep(random.uniform(20, 40))

                except Exception:
                    continue
        except Exception as e:
            self._log(f"Erro no monitoramento do inbox: {e}", 'erro')

    async def _ler_conversa(self) -> list[dict]:
        """
        Extrai histórico de mensagens do thread aberto via JavaScript.
        Retorna lista de dicts: {texto: str, de_nos: bool}
        """
        try:
            await asyncio.sleep(1)
            dados = await self.page.evaluate("""() => {
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

        self._log("LinkedIn bot iniciado com sucesso")
        termos = LINKEDIN_TERMOS_BUSCA.copy()
        random.shuffle(termos)
        termo_idx = 0

        while True:
            try:
                now = datetime.now()
                if not self._horario_ativo(now):
                    await asyncio.sleep(60)
                    continue

                # Reset diário
                if now.hour == HORARIO_INICIO and now.minute < 5:
                    self.conexoes_hoje = 0
                    self.msgs_hoje = 0

                # Fase 1: busca + conexões
                if self.conexoes_hoje < LINKEDIN_MAX_CONEXOES_DIA:
                    termo = termos[termo_idx % len(termos)]
                    termo_idx += 1
                    pagina = random.randint(1, 4)
                    leads = await self.buscar_pessoas(termo, pagina)

                    for lead in leads:
                        if self.conexoes_hoje >= LINKEDIN_MAX_CONEXOES_DIA:
                            break
                        await self.enviar_conexao(lead)
                        pausa = random.randint(45, 120)
                        await asyncio.sleep(pausa)

                # Fase 2: DMs para novas conexões
                if self.msgs_hoje < LINKEDIN_MAX_MENSAGENS_DIA:
                    await self.enviar_dm_novos_contatos()

                # Fase 3: monitorar respostas e reply via IA
                await self.monitorar_inbox()

                # Pausa entre ciclos
                await asyncio.sleep(random.randint(300, 600))  # 5–10 min

            except Exception as e:
                self._log(f"Erro no loop principal: {e}", 'erro')
                await asyncio.sleep(60)

    def _horario_ativo(self, now: datetime) -> bool:
        if now.weekday() not in DIAS_ATIVOS:
            return False
        return HORARIO_INICIO <= now.hour < HORARIO_FIM

    def _log(self, msg: str, tipo: str = 'info'):
        ts = datetime.now().strftime('%H:%M:%S')
        print(f"[LinkedIn/Prisma {ts}] [{tipo.upper()}] {msg}")
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
