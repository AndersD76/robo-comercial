"""Crawl de SEO do TurboVenda simulando o Googlebot mobile.

Lê o HTML que o servidor entrega (o app é renderizado no servidor, em
Flask/Jinja), que é o que o Googlebot indexa na primeira passada.

    python growth/ferramentas/crawl.py --amostra 50 --saida growth/dados

Sementes: todas as URLs de sitemap-pages.xml, uma amostra aleatória de cada
sitemap-empresas-N.xml e os links internos achados nessas páginas (para
encontrar o que está linkado mas fora do sitemap). Grava crawl.csv e
crawl-resumo.json.
"""
import argparse
import concurrent.futures as cf
import csv
import json
import os
import random
import re
import time
from collections import Counter, defaultdict
from urllib.parse import urljoin, urlparse, urldefrag

import requests
from bs4 import BeautifulSoup

BASE = 'https://www.turbovenda.com.br'
UA = ('Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36 '
      '(compatible; Googlebot/2.1; +http://www.google.com/bot.html)')
NAO_PAGINA = re.compile(r'\.(png|jpe?g|webp|avif|svg|ico|css|js|xml|txt|json|pdf)$', re.I)
AREA_LOGADA = ('/dashboard', '/configurar', '/api/', '/admin', '/logout', '/assinar',
               '/trial-expirado', '/pagamento/', '/agendar/')


def sitemap(url, s):
    r = s.get(url, timeout=120)
    return re.findall(r'<loc>([^<]+)</loc>', r.text)


def normalizar(href, base):
    if href.strip().lower().startswith(('mailto:', 'tel:', 'javascript:', 'whatsapp:')):
        return None
    url = urldefrag(urljoin(base, href))[0]
    p = urlparse(url)
    if p.netloc not in ('www.turbovenda.com.br', ''):
        return None
    if NAO_PAGINA.search(p.path) or p.path.startswith(AREA_LOGADA):
        return None
    return f'{BASE}{p.path}' + (f'?{p.query}' if p.query else '')


def analisar(url, s):
    t0 = time.time()
    try:
        r = s.get(url, timeout=60, allow_redirects=False)
    except requests.RequestException as e:
        return {'url': url, 'status': 'erro', 'erro': str(e)[:120]}
    ms = int((time.time() - t0) * 1000)
    d = {'url': url, 'status': r.status_code, 'ms': ms,
         'location': r.headers.get('Location', ''),
         'x_robots': r.headers.get('X-Robots-Tag', '')}
    if r.status_code != 200 or 'html' not in r.headers.get('Content-Type', ''):
        return d
    soup = BeautifulSoup(r.text, 'html.parser')
    def meta(nome, attr='name'):
        m = soup.find('meta', attrs={attr: nome})
        return (m.get('content') or '').strip() if m else ''
    can = soup.find('link', rel='canonical')
    title = (soup.title.string or '').strip() if soup.title and soup.title.string else ''
    h1s = [h.get_text(' ', strip=True) for h in soup.find_all('h1')]
    ld_tipos = []
    for sc in soup.find_all('script', type='application/ld+json'):
        try:
            j = json.loads(sc.string or '')
        except Exception:
            ld_tipos.append('JSON-INVALIDO')
            continue
        for item in (j if isinstance(j, list) else j.get('@graph', [j])):
            if isinstance(item, dict):
                t = item.get('@type')
                ld_tipos.extend(t if isinstance(t, list) else [t])
    for tag in soup(['script', 'style', 'noscript', 'svg']):
        tag.decompose()
    corpo = soup.find('main') or soup.body or soup
    texto = corpo.get_text(' ', strip=True) if corpo else ''
    links = set()
    for a in soup.find_all('a', href=True):
        n = normalizar(a['href'], url)
        if n and n != url:
            links.add(n)
    d.update({
        'title': title, 'title_len': len(title),
        'description': meta('description'), 'desc_len': len(meta('description')),
        'robots': meta('robots'), 'canonical': can.get('href', '') if can else '',
        'h1_qtd': len(h1s), 'h1': (h1s[0] if h1s else '')[:120],
        'palavras': len(texto.split()),
        'og_title': bool(meta('og:title', 'property')),
        'og_image': bool(meta('og:image', 'property')),
        'twitter_card': bool(meta('twitter:card')),
        'hreflang': ','.join(l.get('hreflang', '') for l in soup.find_all('link', rel='alternate') if l.get('hreflang')),
        'jsonld': ','.join(sorted(set(str(t) for t in ld_tipos if t))),
        'links_saida': len(links), '_links': sorted(links),
    })
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--amostra', type=int, default=50, help='URLs por sitemap de empresas')
    ap.add_argument('--saida', default='growth/dados')
    ap.add_argument('--threads', type=int, default=4)
    ap.add_argument('--max', type=int, default=600)
    args = ap.parse_args()
    random.seed(42)
    os.makedirs(args.saida, exist_ok=True)
    s = requests.Session()
    s.headers['User-Agent'] = UA

    no_sitemap = set()
    indice = sitemap(f'{BASE}/sitemap.xml', s)
    sementes = []
    for sm in indice:
        urls = sitemap(sm, s)
        no_sitemap.update(urls)
        sementes += urls if 'pages' in sm else random.sample(urls, min(args.amostra, len(urls)))
    print(f'sitemaps: {len(indice)} | URLs no sitemap: {len(no_sitemap)} | sementes: {len(sementes)}')

    vistos, fila, resultados = set(), list(dict.fromkeys(sementes)), {}
    with cf.ThreadPoolExecutor(args.threads) as ex:
        while fila and len(resultados) < args.max:
            lote = [u for u in fila[:args.threads * 4] if u not in vistos]
            fila = fila[args.threads * 4:]
            vistos.update(lote)
            for d in ex.map(lambda u: analisar(u, s), lote):
                resultados[d['url']] = d
                # descobre páginas linkadas a partir das fixas (não das 10 mil programáticas)
                if d['url'] in sementes[:200] or not d['url'].startswith(f'{BASE}/empresas/'):
                    for l in d.get('_links', []):
                        if l not in vistos and l not in fila and len(vistos) + len(fila) < args.max:
                            fila.append(l)
    entrada = defaultdict(int)
    for d in resultados.values():
        for l in d.get('_links', []):
            entrada[l] += 1
    titulos = Counter(d.get('title') for d in resultados.values() if d.get('title'))
    descs = Counter(d.get('description') for d in resultados.values() if d.get('description'))
    campos = ['url', 'tipo', 'status', 'ms', 'location', 'no_sitemap', 'indexavel', 'robots', 'x_robots',
              'canonical', 'canonical_ok', 'title', 'title_len', 'title_dup', 'description', 'desc_len',
              'desc_dup', 'h1_qtd', 'h1', 'palavras', 'thin', 'links_entrada', 'links_saida', 'jsonld',
              'og_title', 'og_image', 'twitter_card', 'hreflang', 'erro']
    linhas = []
    for url, d in sorted(resultados.items()):
        caminho = urlparse(url).path
        tipo = ('empresas-cnae-cidade' if re.match(r'^/empresas/[^/]+/(?!estado/)[^/]+$', caminho) and not caminho.startswith('/empresas/cidade/')
                else 'empresas-cnae-uf' if '/estado/' in caminho
                else 'empresas-cidade' if caminho.startswith('/empresas/cidade/')
                else 'empresas-cnae' if re.match(r'^/empresas/[^/]+$', caminho)
                else caminho.strip('/').split('/')[0] or 'home')
        robots = (d.get('robots', '') + ' ' + d.get('x_robots', '')).lower()
        can = d.get('canonical', '')
        d.update({
            'tipo': tipo, 'no_sitemap': url in no_sitemap,
            'indexavel': d.get('status') == 200 and 'noindex' not in robots and (not can or can == url),
            'canonical_ok': (can == url) if can else False,
            'title_dup': titulos.get(d.get('title'), 0) > 1,
            'desc_dup': descs.get(d.get('description'), 0) > 1,
            'thin': d.get('status') == 200 and d.get('palavras', 0) < 250,
            'links_entrada': entrada.get(url, 0),
        })
        linhas.append(d)
    with open(os.path.join(args.saida, 'crawl.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction='ignore')
        w.writeheader()
        w.writerows(linhas)
    ok = [d for d in linhas if d.get('status') == 200 and 'title' in d]
    resumo = {
        'paginas_crawleadas': len(linhas),
        'status': dict(Counter(str(d.get('status')) for d in linhas)),
        'por_tipo': dict(Counter(d['tipo'] for d in linhas)),
        'indexaveis': sum(d['indexavel'] for d in linhas),
        'sem_title': sum(not d.get('title') for d in ok),
        'title_mais_60': sum(d.get('title_len', 0) > 60 for d in ok),
        'title_duplicado': sum(d['title_dup'] for d in ok),
        'sem_description': sum(not d.get('description') for d in ok),
        'desc_mais_155': sum(d.get('desc_len', 0) > 155 for d in ok),
        'desc_duplicada': sum(d['desc_dup'] for d in ok),
        'sem_canonical': sum(not d.get('canonical') for d in ok),
        'canonical_diferente': sum(bool(d.get('canonical')) and not d['canonical_ok'] for d in ok),
        'h1_ausente': sum(d.get('h1_qtd', 0) == 0 for d in ok),
        'h1_multiplo': sum(d.get('h1_qtd', 0) > 1 for d in ok),
        'thin_menos_250_palavras': sum(d['thin'] for d in ok),
        'sem_jsonld': sum(not d.get('jsonld') for d in ok),
        'jsonld_invalido': sum('JSON-INVALIDO' in d.get('jsonld', '') for d in ok),
        'sem_og_image': sum(not d.get('og_image') for d in ok),
        'sem_twitter_card': sum(not d.get('twitter_card') for d in ok),
        'com_hreflang': sum(bool(d.get('hreflang')) for d in ok),
        'linkadas_fora_do_sitemap': sorted(d['url'] for d in ok if not d['no_sitemap'] and d['indexavel'])[:40],
        'no_sitemap_sem_link_entrada_no_crawl': sum(d['no_sitemap'] and d['links_entrada'] == 0 for d in ok),
        'tempo_ms_p50': sorted(d['ms'] for d in ok)[len(ok) // 2] if ok else None,
        'tempo_ms_p90': sorted(d['ms'] for d in ok)[int(len(ok) * .9)] if ok else None,
        'jsonld_tipos': dict(Counter(t for d in ok for t in d.get('jsonld', '').split(',') if t)),
    }
    with open(os.path.join(args.saida, 'crawl-resumo.json'), 'w', encoding='utf-8') as f:
        json.dump(resumo, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in resumo.items() if k != 'linkadas_fora_do_sitemap'}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
