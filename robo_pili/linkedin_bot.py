# -*- coding: utf-8 -*-
"""
LinkedIn Bot — Pili Equipamentos
Estratégia:
  1. Busca responsáveis por operações em cerealistas/cooperativas/silos
  2. Envia pedido de conexão com nota personalizada (IA)
  3. Após aceite, envia DM com pitch de tombadores/coletores + link demo
  4. Exporta contatos para pipeline WhatsApp
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
    from database import (
        get_connection, salvar_lead_linkedin, registrar_log
    )
    HAS_DB = True
except ImportError:
    HAS_DB = False

# Fuso horário de Brasília (UTC-3)
_BRT = timezone(timedelta(hours=-3))

SESSION_DIR = './linkedin_session'
LINKEDIN_URL = 'https://www.linkedin.com'


class LinkedInBot:
    """
    Automação LinkedIn para Pili Equipamentos.
    Foca em responsáveis por operações em cerealistas, cooperativas e silos.
    """

    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None
        self._pw = None
        self.conectado = False
        self.conexoes_hoje = 0
        self.msgs_hoje = 0
        self._msgs_respondidas: set = set()
        self._ciclo = 0
        self.ai = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) \
            if HAS_AI and ANTHROPIC_API_KEY else None

    # =========================================================================
    # SESSÃO
    # =========================================================================

    async def iniciar(self):
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
        self._log("LinkedIn bot Pili iniciado (headless)")

    async def fechar(self):
        if self.context:
            await self.context.close()
        if self._pw:
            await self._pw.stop()

    # =========================================================================
    # LOGIN
    # =========================================================================

    async def fazer_login(self) -> bool:
        self._log("Verificando sessão LinkedIn...")
        await self.page.goto(
            f'{LINKEDIN_URL}/feed/', wait_until='domcontentloaded'
        )
        await asyncio.sleep(random.uniform(2, 4))

        if '/feed' in self.page.url or '/in/' in self.page.url:
            self.conectado = True
            self._log(
                "Sessão LinkedIn ativa — login não necessário", 'sucesso'
            )
            return True

        email_conf = (
            LINKEDIN_EMAIL[:4] + '***' if LINKEDIN_EMAIL else '(não definido)'
        )
        self._log(f"Fazendo login com {email_conf}...")
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

            if '/feed' in self.page.url:
                self.conectado = True
                self._log("Login LinkedIn OK — feed carregado", 'sucesso')
                return True
            elif '/checkpoint' in self.page.url:
                self.conectado = True
                self._log(
                    "Login OK (checkpoint — verifique o email/app)", 'aviso'
                )
                return True
            else:
                self._log(
                    f"Falha no login — URL atual: {self.page.url}", 'erro'
                )
                return False
        except Exception as e:
            self._log(f"Erro no login: {e}", 'erro')
            return False

    # =========================================================================
    # BUSCA
    # =========================================================================

    async def buscar_pessoas(self, termo: str, pagina: int = 1) -> list[dict]:
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
            await self.page.evaluate('window.scrollTo(0, 800)')
            await asyncio.sleep(1)

            cards = await self.page.query_selector_all(
                'li.reusable-search__result-container'
            )
            self._log(f"  {len(cards)} perfis encontrados na página")

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
                    url_perfil = (
                        await link_el.get_attribute('href')
                        if link_el else ''
                    )

                    if not nome or 'LinkedIn Member' in nome:
                        continue
                    if not self._cargo_alvo(cargo):
                        continue

                    self._log(f"  → {nome} | {cargo} @ {empresa}")
                    resultados.append({
                        'nome': nome,
                        'cargo': cargo,
                        'empresa': empresa,
                        'url_perfil': (
                            url_perfil.split('?')[0] if url_perfil else ''
                        ),
                        'termo_busca': termo,
                    })
                except Exception:
                    continue

            self._log(
                f"Resultado: {len(resultados)} leads qualificados "
                f"(cargo-alvo) de {len(cards)} perfis"
            )
        except Exception as e:
            self._log(f"Erro na busca: {e}", 'erro')
        return resultados

    def _cargo_alvo(self, cargo: str) -> bool:
        cargo_lower = cargo.lower()
        return any(c.lower() in cargo_lower for c in LINKEDIN_CARGOS_ALVO)

    # =========================================================================
    # CONEXÃO
    # =========================================================================

    async def enviar_conexao(self, perfil: dict) -> bool:
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

            conectar_btn = await self.page.query_selector(
                'button[aria-label*="Conectar"], button[aria-label*="Connect"]'
            )
            if not conectar_btn:
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
                self._log(
                    f"  Botão Conectar não encontrado para {nome}", 'aviso'
                )
                return False

            await conectar_btn.click()
            await asyncio.sleep(random.uniform(1, 2))

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

            enviar_btn = await self.page.query_selector(
                'button[aria-label*="Enviar"], button[aria-label*="Send"]'
            )
            if enviar_btn:
                await enviar_btn.click()
                self.conexoes_hoje += 1
                self._log(
                    f"✓ Conexão #{self.conexoes_hoje}/{LINKEDIN_MAX_CONEXOES_DIA}"
                    f" enviada: {nome} @ {empresa}",
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
                        "de conexao no LinkedIn para responsável por "
                        "operações em cerealista/cooperativa. Mencione Pili "
                        "Equipamentos (tombadores e coletores de graos). "
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
                return r.content[0].text.strip()[:295]
            except Exception:
                pass

        return (
            f"Oi {nome}, vi que você atua em {cargo} na {empresa}. "
            "Trabalho com tombadores e coletores de graos — ajudo "
            "cerealistas a reduzir perdas no recebimento. Vamos conectar?"
        )[:295]

    # =========================================================================
    # DM PÓS-CONEXÃO
    # =========================================================================

    async def enviar_dm_novos_contatos(self):
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
            self._log(
                f"Inbox: {len(threads)} threads — verificando DMs iniciais"
            )

            enviadas = 0
            for thread in threads[:5]:
                try:
                    preview = await thread.query_selector(
                        '.msg-conversation-card__message-snippet'
                    )
                    preview_txt = (
                        await preview.inner_text() if preview else ''
                    )
                    if preview_txt.startswith('Você:'):
                        continue

                    await thread.click()
                    await asyncio.sleep(random.uniform(1, 2))

                    nome_el = await self.page.query_selector(
                        '.msg-entity-lockup__entity-title'
                    )
                    nome = (await nome_el.inner_text()).strip() \
                        if nome_el else 'contato'

                    self._log(f"  Enviando DM inicial para {nome}...")
                    msg = self._gerar_dm_inicial(nome)
                    await self._digitar_e_enviar(msg)
                    self.msgs_hoje += 1
                    enviadas += 1
                    self._log(
                        f"  ✓ DM #{self.msgs_hoje}/{LINKEDIN_MAX_MENSAGENS_DIA}"
                        f" enviada para {nome}",
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
            f"Oi {primeiro}, obrigado por conectar! 🌾\n\n"
            "Trabalho com a Pili Equipamentos — tombadores e coletores de "
            "graos para cerealistas e cooperativas.\n\n"
            "Nossos equipamentos reduzem perdas no recebimento em mais de 30%"
            " e o ROI acontece em menos de 1 safra.\n\n"
            f"Posso te mandar mais detalhes? Ou agenda uma demo rapida:\n"
            f"📅 {DEMO_CAL_LINK}"
        )

    async def _digitar_e_enviar(self, texto: str):
        caixa = await self.page.query_selector(
            'div.msg-form__contenteditable'
        )
        if not caixa:
            return
        await caixa.click()
        for linha in texto.split('\n'):
            await caixa.type(linha, delay=random.randint(20, 60))
            await self.page.keyboard.press('Shift+Enter')
        await self.page.keyboard.press('Backspace')
        await asyncio.sleep(0.5)
        await self.page.keyboard.press('Enter')
        await asyncio.sleep(random.uniform(1, 2))

    # =========================================================================
    # MONITORAR INBOX — RESPOSTAS DOS LEADS
    # =========================================================================

    async def monitorar_inbox(self):
        """
        Varre o inbox buscando respostas de leads.
        Gera reply via Claude Haiku com foco em marcar demo/reunião.
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
            self._log(f"Monitorando inbox: {len(threads)} threads")

            replies = 0
            for thread in threads[:20]:
                try:
                    preview_el = await thread.query_selector(
                        '.msg-conversation-card__message-snippet'
                    )
                    preview = (await preview_el.inner_text()).strip() \
                        if preview_el else ''

                    if preview.startswith('Você:') or not preview:
                        continue

                    await thread.click()
                    await asyncio.sleep(random.uniform(1.5, 2.5))

                    nome_el = await self.page.query_selector(
                        '.msg-entity-lockup__entity-title'
                    )
                    nome = (await nome_el.inner_text()).strip() \
                        if nome_el else 'contato'

                    self._log(
                        f"  Resposta de {nome}: \"{preview[:70]}\""
                    )

                    historico = await self._ler_conversa()
                    if not historico:
                        continue

                    ultima = historico[-1]
                    if ultima.get('de_nos'):
                        continue

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
                        f"  ✓ Reply enviado para {nome}: "
                        f"\"{resposta[:60]}...\"",
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
        """Extrai histórico do thread aberto via JavaScript."""
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
        """Gera resposta via Claude Haiku com foco em demo Pili."""
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
                        "Você é Marcos, vendedor da Pili Equipamentos — "
                        "tombadores e coletores de grãos para cerealistas "
                        "e cooperativas. Benefícios: reduz perdas no "
                        "recebimento em 30%+ e ROI em menos de 1 safra. "
                        f"Link para demo: {DEMO_CAL_LINK}\n"
                        "OBJETIVO: Agendar uma demo/visita.\n"
                        "REGRAS: resposta curta (2-3 frases), natural e "
                        "focada em resultado. Interesse → peça pra agendar. "
                        "Objeção preço → fale do ROI < 1 safra. "
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
            "Que tal uma demo rápida para ver os equipamentos ao vivo? "
            f"ROI em menos de 1 safra. Agende aqui: {DEMO_CAL_LINK}"
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
        ok = await self.fazer_login()
        if not ok:
            self._log(
                "Não foi possível logar no LinkedIn. Abortando.", 'erro'
            )
            return

        self._log(
            f"LinkedIn bot Pili ativo — "
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
                    if now.minute == 0:
                        self._log(
                            f"Fora do horário ativo "
                            f"({now.strftime('%H:%M')} BRT). "
                            f"Ativo: seg-sex "
                            f"{HORARIO_INICIO:02d}h–{HORARIO_FIM:02d}h"
                        )
                    await asyncio.sleep(60)
                    continue

                if now.hour == HORARIO_INICIO and now.minute < 5:
                    self.conexoes_hoje = 0
                    self.msgs_hoje = 0
                    self._log("Reset diário — contadores zerados para hoje")

                self._ciclo += 1
                self._log(
                    f"━━━ Ciclo #{self._ciclo} "
                    f"| {now.strftime('%H:%M')} BRT "
                    f"| Conexões: {self.conexoes_hoje}"
                    f"/{LINKEDIN_MAX_CONEXOES_DIA} "
                    f"| DMs: {self.msgs_hoje}"
                    f"/{LINKEDIN_MAX_MENSAGENS_DIA} ━━━"
                )

                # ── Fase 1: busca + conexões ──
                if self.conexoes_hoje < LINKEDIN_MAX_CONEXOES_DIA:
                    termo = termos[termo_idx % len(termos)]
                    termo_idx += 1
                    pagina = random.randint(1, 4)
                    leads = await self.buscar_pessoas(termo, pagina)

                    if leads:
                        self._log(
                            f"Fase 1: {len(leads)} leads — enviando conexões..."
                        )
                        for lead in leads:
                            if self.conexoes_hoje >= LINKEDIN_MAX_CONEXOES_DIA:
                                self._log(
                                    "Limite de conexões do dia atingido"
                                )
                                break
                            await self.enviar_conexao(lead)
                            pausa = random.randint(45, 120)
                            self._log(
                                f"Aguardando {pausa}s antes do próximo..."
                            )
                            await asyncio.sleep(pausa)
                    else:
                        self._log(
                            "Fase 1: nenhum lead qualificado nesta busca"
                        )
                else:
                    self._log(
                        "Fase 1: limite de conexões já atingido hoje"
                    )

                # ── Fase 2: DMs para novas conexões ──
                if self.msgs_hoje < LINKEDIN_MAX_MENSAGENS_DIA:
                    self._log(
                        "Fase 2: verificando DMs iniciais p/ novas conexões..."
                    )
                    await self.enviar_dm_novos_contatos()
                else:
                    self._log(
                        "Fase 2: limite de DMs já atingido hoje — pulando"
                    )

                # ── Fase 3: monitorar respostas e reply via IA ──
                self._log("Fase 3: monitorando inbox para respostas...")
                await self.monitorar_inbox()

                prox = random.randint(300, 600)
                self._log(
                    f"Ciclo #{self._ciclo} concluído. "
                    f"Próximo em {prox // 60} min {prox % 60}s."
                )
                await asyncio.sleep(prox)

            except Exception as e:
                self._log(f"Erro no loop: {e}", 'erro')
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
        print(f"[LI/Pili {ts}] {icone} {msg}", flush=True)
        if HAS_DB:
            try:
                registrar_log(tipo, f"[LinkedIn] {msg}")
            except Exception:
                pass


if __name__ == '__main__':
    import sys
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    bot = LinkedInBot()

    async def main():
        await bot.iniciar()
        await bot.executar()

    asyncio.run(main())
