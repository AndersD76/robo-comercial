# -*- coding: utf-8 -*-
"""
Buscador de Leads v2 - PrismaBiz
Usa Playwright (Chrome real) para buscar no Bing/DuckDuckGo sem ser bloqueado
"""

import re
import random
import asyncio
from urllib.parse import quote_plus, urlparse, parse_qs, unquote

from config import (
    TERMOS_BUSCA, INTERVALO_BUSCA_MIN, INTERVALO_BUSCA_MAX,
    PALAVRAS_POSITIVAS, PALAVRAS_NEGATIVAS, ESTADOS_PRIORIDADE
)


class Buscador:
    """Busca leads via Bing/DuckDuckGo usando Playwright com Chrome real"""

    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None
        self._pw = None
        self.sites_ignorar = {
            'facebook.com', 'instagram.com', 'linkedin.com', 'twitter.com',
            'youtube.com', 'wikipedia.org', 'reclameaqui.com.br', 'olx.com.br',
            'mercadolivre.com.br', 'amazon.com.br', 'catho.com.br',
            'indeed.com', 'infojobs.com.br', 'glassdoor.com.br',
            'gupy.io', 'vagas.com.br', 'google.com', 'bing.com',
            'gov.br', 'jusbrasil.com.br', 'duckduckgo.com',
            'pinterest.com', 'tiktok.com',
        }
        self.ddds_validos = {
            '11', '12', '13', '14', '15', '16', '17', '18', '19',
            '21', '22', '24', '27', '28',
            '31', '32', '33', '34', '35', '37', '38',
            '41', '42', '43', '44', '45', '46', '47', '48', '49',
            '51', '52', '53', '54', '55', '61', '62', '63', '64', '65',
            '66', '67', '68', '69', '71', '73', '74', '75', '77',
            '79', '81', '82', '83', '84', '85', '86', '87', '88',
            '89', '91', '92', '93', '94', '95', '96', '97', '98', '99',
        }

    async def iniciar(self):
        """Inicia browser Playwright usando Chrome instalado"""
        from playwright.async_api import async_playwright
        self._pw = await async_playwright().start()

        # Usa Chromium do Playwright (compatível com Railway/Linux)
        self.browser = await self._pw.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-dev-shm-usage',
            ]
        )
        self.context = await self.browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            locale='pt-BR',
            viewport={'width': 1920, 'height': 1080},
        )
        self.page = await self.context.new_page()

        # Anti-detecção
        await self.page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['pt-BR', 'pt', 'en-US', 'en']});
            window.chrome = {runtime: {}};
        """)
        print("  [OK] Browser iniciado (Chrome)")

    async def fechar(self):
        """Fecha browser"""
        if self.browser:
            await self.browser.close()
        if self._pw:
            await self._pw.stop()

    # =========================================================================
    # BUSCA GOOGLE (motor principal)
    # =========================================================================

    async def buscar_google(self, termo, max_resultados=20):
        """Busca no Google Brasil via JS — melhor cobertura para .com.br"""
        resultados = []
        try:
            url = (
                f'https://www.google.com.br/search'
                f'?q={quote_plus(termo)}&num={max_resultados}&hl=pt-BR&gl=br'
            )
            await self.page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(random.uniform(3, 5))

            # Detecta CAPTCHA / bloqueio
            pg_url = self.page.url
            if 'sorry' in pg_url or 'captcha' in pg_url.lower():
                print('  [AVISO] Google pediu CAPTCHA — pulando para Bing')
                return []

            # Extrai via JS: mais robusto que CSS (Google muda classes constantemente)
            dados = await self.page.evaluate("""() => {
                const items = [];
                const seen = new Set();
                document.querySelectorAll('#search a[href^="http"]').forEach(a => {
                    const href = a.href;
                    if (!href || href.includes('google.com') || seen.has(href)) return;
                    seen.add(href);
                    const h3 = a.closest('div')?.querySelector('h3') || a.querySelector('h3');
                    const titulo = (h3?.textContent || a.textContent || '').trim();
                    const container = a.closest('[data-hveid]') || a.closest('div.g');
                    let snippet = '';
                    if (container) {
                        const texts = [...container.querySelectorAll('span')]
                            .filter(e => !e.children.length && e.textContent.trim().length > 30)
                            .map(e => e.textContent.trim());
                        snippet = texts.slice(0, 3).join(' ');
                    }
                    if (titulo.length > 3) {
                        items.push({
                            url: href,
                            titulo: titulo.slice(0, 200),
                            snippet: snippet.slice(0, 500)
                        });
                    }
                });
                return items.slice(0, 20);
            }""")

            for d in (dados or []):
                url_real = d.get('url', '')
                if not url_real:
                    continue
                try:
                    dominio = urlparse(url_real).netloc.lower()
                except Exception:
                    continue
                if any(s in dominio for s in self.sites_ignorar):
                    continue
                titulo = d.get('titulo', '')
                snippet = d.get('snippet', '')
                telefones = self._extrair_telefones(snippet + ' ' + titulo)
                resultados.append({
                    'url': url_real,
                    'dominio': dominio,
                    'titulo': titulo,
                    'snippet': snippet,
                    'telefones': telefones,
                    'fonte': 'google',
                })
        except Exception as e:
            print(f'  [ERRO] Google: {e}')
        return resultados

    # =========================================================================
    # BUSCA BING (motor principal)
    # =========================================================================

    async def buscar_bing(self, termo, max_resultados=20):
        """Busca no Bing — locale BR, JS evaluate"""
        resultados = []
        try:
            termo_bing = termo.strip()
            url = (
                f'https://www.bing.com/search?q={quote_plus(termo_bing)}'
                f'&count={max_resultados}&cc=BR&setlang=pt-BR&FORM=QBLH'
            )
            await self.page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(random.uniform(2, 4))

            dados = await self.page.evaluate("""() => {
                const items = [];
                document.querySelectorAll('li.b_algo').forEach(li => {
                    const a = li.querySelector('h2 a');
                    if (!a || !a.href) return;
                    const titulo = a.textContent.trim();
                    const snipEl = li.querySelector('.b_caption p, p.b_algoSlug, .b_algoSlug');
                    const snippet = snipEl ? snipEl.textContent.trim() : '';
                    if (titulo.length > 3) {
                        items.push({
                            url: a.href,
                            titulo: titulo.slice(0, 200),
                            snippet: snippet.slice(0, 500)
                        });
                    }
                });
                return items;
            }""")

            for d in (dados or []):
                url_real = d.get('url', '')
                if not url_real or not url_real.startswith('http'):
                    continue
                try:
                    dominio = urlparse(url_real).netloc.lower()
                except Exception:
                    continue
                if any(s in dominio for s in self.sites_ignorar):
                    continue
                titulo  = d.get('titulo', '')
                snippet = d.get('snippet', '')
                telefones = self._extrair_telefones(snippet + ' ' + titulo)
                resultados.append({
                    'url': url_real,
                    'dominio': dominio,
                    'titulo': titulo,
                    'snippet': snippet,
                    'telefones': telefones,
                    'fonte': 'bing',
                })
        except Exception as e:
            print(f"  [ERRO] Bing: {e}")
        return resultados

    # =========================================================================
    # BUSCA DUCKDUCKGO LITE (fallback)
    # =========================================================================

    async def buscar_duckduckgo(self, termo, max_resultados=15):
        """Busca no DuckDuckGo Lite — região BR"""
        resultados = []
        try:
            termo_ddg = termo.strip()
            url = (
                f'https://lite.duckduckgo.com/lite/'
                f'?q={quote_plus(termo_ddg)}&kl=br-pt'
            )
            await self.page.goto(
                url, wait_until='domcontentloaded', timeout=20000
            )
            await asyncio.sleep(random.uniform(2, 4))

            dados = await self.page.evaluate("""() => {
                const items = [];
                document.querySelectorAll('a.result-link').forEach(a => {
                    const href = a.getAttribute('href') || '';
                    const titulo = a.textContent.trim();
                    let url_real = href;
                    if (href.includes('uddg=')) {
                        try {
                            const base = href.startsWith('//')
                                ? 'https:' + href : href;
                            const p = new URL(base);
                            url_real = p.searchParams.get('uddg') || href;
                        } catch(e) {}
                    }
                    if (!url_real.startsWith('http')) return;
                    const row = a.closest('tr');
                    const nextRow = row ? row.nextElementSibling : null;
                    const snippet = nextRow
                        ? nextRow.textContent.trim() : '';
                    if (titulo.length > 3) {
                        items.push({
                            url: url_real,
                            titulo: titulo.slice(0, 200),
                            snippet: snippet.slice(0, 500)
                        });
                    }
                });
                return items;
            }""")

            for d in (dados or []):
                url_real = d.get('url', '')
                if not url_real or not url_real.startswith('http'):
                    continue
                try:
                    dominio = urlparse(url_real).netloc.lower()
                except Exception:
                    continue
                if any(s in dominio for s in self.sites_ignorar):
                    continue
                titulo  = d.get('titulo', '')
                snippet = d.get('snippet', '')
                telefones = self._extrair_telefones(snippet + ' ' + titulo)
                resultados.append({
                    'url': url_real,
                    'dominio': dominio,
                    'titulo': titulo,
                    'snippet': snippet,
                    'telefones': telefones,
                    'fonte': 'duckduckgo',
                })
        except Exception as e:
            print(f"  [ERRO] DuckDuckGo: {e}")
        return resultados

    # =========================================================================
    # BUSCA PRINCIPAL
    # =========================================================================

    async def buscar_leads(self, termo=None, max_resultados=20):
        """Busca leads: Bing → Google → DuckDuckGo.
        Bing primeiro pois Google bloqueia com CAPTCHA em IPs de servidor."""
        if not termo:
            termo = random.choice(TERMOS_BUSCA)

        print(f"\n  Buscando: '{termo}'")

        # Bing primeiro (não bloqueia com CAPTCHA em servidor)
        resultados = await self.buscar_bing(termo, max_resultados)
        if resultados:
            print(f"  Bing: {len(resultados)} resultados")

        # Google como complemento (pode dar CAPTCHA)
        if len(resultados) < 10:
            resultados_g = await self.buscar_google(termo, max_resultados)
            if resultados_g:
                print(f"  Google: +{len(resultados_g)} resultados")
                urls_vistas = {r['url'] for r in resultados}
                for r in resultados_g:
                    if r['url'] not in urls_vistas:
                        resultados.append(r)

        # Fallback DuckDuckGo
        if len(resultados) < 5:
            print("  Complementando com DuckDuckGo...")
            resultados_ddg = await self.buscar_duckduckgo(termo, max_resultados)
            urls_vistas = {r['url'] for r in resultados}
            for r in resultados_ddg:
                if r['url'] not in urls_vistas:
                    resultados.append(r)

        # Filtra e pontua
        leads = []
        for r in resultados:
            relevancia = self._calcular_relevancia(r)
            if relevancia >= 0:
                r['relevancia'] = relevancia
                leads.append(r)

        leads.sort(key=lambda x: x['relevancia'], reverse=True)

        print(f"  Encontrados: {len(leads)} resultados relevantes")
        return leads

    async def buscar_multiplos(self, termos=None, max_por_termo=15):
        """Busca múltiplos termos com delay entre buscas"""
        if not termos:
            termos = random.sample(TERMOS_BUSCA, min(5, len(TERMOS_BUSCA)))

        todos_leads = []
        urls_vistas = set()

        for i, termo in enumerate(termos):
            print(f"\n[{i+1}/{len(termos)}] Buscando: {termo}")

            leads = await self.buscar_leads(termo, max_por_termo)

            for lead in leads:
                if lead['url'] not in urls_vistas:
                    urls_vistas.add(lead['url'])
                    todos_leads.append(lead)

            # Delay entre buscas
            if i < len(termos) - 1:
                delay = random.uniform(INTERVALO_BUSCA_MIN, INTERVALO_BUSCA_MAX)
                print(f"  Aguardando {delay:.0f}s...")
                await asyncio.sleep(delay)

        print(f"\n  Total: {len(todos_leads)} leads unicos")
        return todos_leads

    # =========================================================================
    # UTILIDADES
    # =========================================================================

    def _extrair_telefones(self, texto):
        """Extrai telefones brasileiros de um texto"""
        telefones = []
        patterns = [
            r'\((\d{2})\)\s*(\d{4,5})[-.\s]?(\d{4})',
            r'(\d{2})\s?(\d{4,5})[-.\s](\d{4})',
        ]
        for pattern in patterns:
            for match in re.findall(pattern, texto):
                numero = ''.join(match)
                validado = self.validar_telefone(numero)
                if validado and validado not in telefones:
                    telefones.append(validado)
        return telefones

    def validar_telefone(self, telefone):
        """Valida telefone brasileiro"""
        if not telefone:
            return None
        numeros = re.sub(r'\D', '', str(telefone))
        if numeros.startswith('55') and len(numeros) >= 12:
            numeros = numeros[2:]
        if len(numeros) not in [10, 11]:
            return None
        ddd = numeros[:2]
        if ddd not in self.ddds_validos:
            return None
        numero = numeros[2:]
        if len(numero) == 9 and not numero.startswith('9'):
            return None
        if len(set(numero)) == 1:
            return None
        return numeros

    def validar_cnpj(self, cnpj):
        """Valida CNPJ brasileiro"""
        if not cnpj:
            return None
        cnpj = re.sub(r'\D', '', str(cnpj))
        if len(cnpj) != 14 or len(set(cnpj)) == 1:
            return None

        def calc_digito(cnpj, peso):
            soma = sum(int(cnpj[i]) * peso[i] for i in range(len(peso)))
            resto = soma % 11
            return '0' if resto < 2 else str(11 - resto)

        peso1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        peso2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]

        if cnpj[12] != calc_digito(cnpj[:12], peso1):
            return None
        if cnpj[13] != calc_digito(cnpj[:13], peso2):
            return None
        return cnpj

    def validar_email(self, email):
        """Valida email"""
        if not email or len(email) > 100:
            return None
        email = email.lower().strip()
        invalidos = ['example', 'teste', 'test', '@localhost', 'sentry',
                     'wix', 'wordpress', 'jquery', '.png', '.jpg', '.gif',
                     '.js', '.css', 'noreply', 'no-reply', 'mailer-daemon']
        for inv in invalidos:
            if inv in email:
                return None
        if not re.match(r'^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$', email):
            return None
        return email

    def _calcular_relevancia(self, resultado):
        """Calcula relevancia de um resultado de busca"""
        texto = (resultado.get('titulo', '') + ' ' + resultado.get('snippet', '')).lower()
        score = 0

        for palavra in PALAVRAS_POSITIVAS:
            if palavra in texto:
                score += 5

        for palavra in PALAVRAS_NEGATIVAS:
            if palavra in texto:
                score -= 20

        if resultado.get('telefones'):
            score += 10

        if '.com.br' in resultado.get('dominio', ''):
            score += 3

        for estado in ESTADOS_PRIORIDADE:
            e = estado.lower()
            if f' {e} ' in texto or f' {e},' in texto:
                score += 2
                break

        return score
