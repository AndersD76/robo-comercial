# -*- coding: utf-8 -*-
"""Guarda de SEO: o CI falha se uma página indexável perder título,
descrição, canonical, JSON-LD ou ganhar noindex sem querer.

Roda sem banco de verdade (DATABASE_URL numa porta fechada): cobre as
páginas que renderizam sem consulta. As programáticas (/empresas) dependem
do banco e são conferidas no crawl de produção (growth/ferramentas/crawl.py).
"""
import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

if not os.environ.get('DATABASE_URL'):
    # O app sai na importação sem DATABASE_URL; o CI roda este arquivo num
    # passo próprio, com um endereço de banco que não existe (ver ci.yml)
    pytest.skip('DATABASE_URL não definido', allow_module_level=True)

import app as A  # noqa: E402

BASE = 'https://www.turbovenda.com.br'


@pytest.fixture(scope='module')
def client():
    A.app.config['TESTING'] = True
    A.limiter.enabled = False
    with A.app.test_client() as c:
        yield c


def _paginas_publicas():
    paginas = ['/', '/precos', '/cadastro', '/blog', '/termos', '/privacidade',
               '/alternativas', '/ferramentas']
    paginas += [f"/blog/{p['slug']}" for p in A.BLOG_POSTS]
    paginas += [f"/para/{s['slug']}" for s in A.SEGMENTOS]
    paginas += [f"/alternativas/{a['slug']}" for a in A.ALTERNATIVAS]
    return paginas


def _extrair(html):
    def um(padrao):
        m = re.search(padrao, html, re.S)
        return m.group(1).strip() if m else None
    import html as h
    return {
        'title': h.unescape(um(r'<title>(.*?)</title>') or ''),
        'description': h.unescape(um(r'<meta name="description" content="(.*?)">') or ''),
        'canonical': um(r'<link rel="canonical" href="(.*?)"'),
        'robots': um(r'<meta name="robots" content="(.*?)"') or '',
        'h1': len(re.findall(r'<h1[\s>]', html)),
        'ld': re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S),
    }


@pytest.fixture(scope='module')
def renderizadas(client):
    paginas = {}
    for caminho in _paginas_publicas():
        r = client.get(caminho)
        if r.status_code == 500:
            continue   # depende do banco: coberta pelo crawl de produção
        paginas[caminho] = (r.status_code, _extrair(r.get_data(as_text=True)))
    assert len(paginas) >= 40, f'poucas páginas renderizaram sem banco: {len(paginas)}'
    return paginas


def test_paginas_publicas_respondem_200(renderizadas):
    ruins = {c: s for c, (s, _) in renderizadas.items() if s != 200}
    assert not ruins


def test_title_e_description_no_tamanho_do_google(renderizadas):
    longos = {c: (len(d['title']), d['title']) for c, (_, d) in renderizadas.items()
              if not d['title'] or len(d['title']) > A.TITULO_MAX}
    assert not longos
    desc = {c: len(d['description']) for c, (_, d) in renderizadas.items()
            if not d['description'] or len(d['description']) > A.DESCRICAO_MAX}
    assert not desc


def test_titles_unicos(renderizadas):
    vistos = {}
    for c, (_, d) in renderizadas.items():
        vistos.setdefault(d['title'], []).append(c)
    assert not {t: cs for t, cs in vistos.items() if len(cs) > 1}


def test_canonical_absoluto_e_sem_noindex(renderizadas):
    for c, (_, d) in renderizadas.items():
        assert d['canonical'] and d['canonical'].startswith(BASE), (c, d['canonical'])
        assert 'noindex' not in d['robots'].lower(), c


def test_json_ld_valido_e_um_h1(renderizadas):
    for c, (_, d) in renderizadas.items():
        assert d['h1'] == 1, (c, d['h1'])
        for bloco in d['ld']:
            json.loads(bloco)   # quebra se o JSON-LD estiver inválido


def test_toda_pagina_tem_trilha(renderizadas):
    """BreadcrumbList em todas as páginas públicas, menos a raiz."""
    sem = []
    for c, (_, d) in renderizadas.items():
        tipos = []
        for bloco in d['ld']:
            j = json.loads(bloco)
            tipos += [i.get('@type') for i in (j if isinstance(j, list) else j.get('@graph', [j]))]
        if c != '/' and 'BreadcrumbList' not in tipos:
            sem.append(c)
    assert not sem


def test_blog_tem_schema_blog(renderizadas):
    tipos = [json.loads(b).get('@type') for b in renderizadas['/blog'][1]['ld']]
    assert 'Blog' in tipos and 'BreadcrumbList' in tipos


def test_robots_libera_buscadores_e_bloqueia_area_logada(client):
    txt = client.get('/robots.txt').get_data(as_text=True)
    for agente in ('Googlebot', 'Bingbot', 'OAI-SearchBot', 'ChatGPT-User', 'GPTBot',
                   'PerplexityBot', 'ClaudeBot', 'Claude-SearchBot', 'Applebot',
                   'Google-Extended'):
        assert f'User-agent: {agente}\n' in txt, agente
    # Um grupo só: nenhum agente escapa do bloqueio da área logada
    assert txt.count('Allow: /\n') == 1 and 'Disallow: /dashboard\n' in txt
    assert 'Sitemap: https://www.turbovenda.com.br/sitemap.xml' in txt


def test_barra_no_final_redireciona_301(client):
    r = client.get('/precos/?utm_source=x')
    assert r.status_code == 301 and r.headers['Location'].endswith('/precos?utm_source=x')
    assert client.get('/').status_code == 200


def test_cabe_e_titulo_seo():
    assert A._titulo_seo('Curto | TurboVenda') == 'Curto | TurboVenda'
    longo = 'Como Prospectar Escritórios de Contabilidade: Vendas B2B — TurboVenda Blog'
    assert A._titulo_seo(longo) == 'Como Prospectar Escritórios de Contabilidade: Vendas B2B'
    t = A._cabe(['x' * 70, 'Metalúrgicas em Caxias do Sul - RS: 312 empresas'])
    assert t == 'Metalúrgicas em Caxias do Sul - RS: 312 empresas'
    cortado = A._cortar('palavra ' * 30, 60)
    assert len(cortado) <= 60 and cortado.endswith('…') and ' palavr…' not in cortado


def test_ip_real_do_visitante_atras_do_nginx():
    # Railway põe o IP do visitante; o nginx acrescenta o do proxy do Railway.
    # O limitador conta por esse IP: errar aqui junta todo mundo num limite só.
    from werkzeug.middleware.proxy_fix import ProxyFix
    from werkzeug.test import EnvironBuilder
    pf = A.app.wsgi_app
    assert isinstance(pf, ProxyFix) and pf.x_for == 2
    visto = {}

    def interno(environ, start_response):
        visto['ip'] = environ['REMOTE_ADDR']
        return [b'']
    env = EnvironBuilder(path='/', headers={'X-Forwarded-For': '200.10.20.30, 100.64.0.7'},
                         environ_base={'REMOTE_ADDR': '127.0.0.1'}).get_environ()
    ProxyFix(interno, x_for=pf.x_for)(env, lambda *a: None)
    assert visto['ip'] == '200.10.20.30'


def test_buscador_so_isento_com_dns_confirmado(monkeypatch):
    chamadas = []

    def falso_dns(ip, dominios):
        chamadas.append(ip)
        return ip == '66.249.66.1'
    monkeypatch.setattr(A, '_dns_confere', falso_dns)
    A._buscador_cache.clear()
    ua_google = 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'
    casos = [('GET', ua_google, '66.249.66.1', True),     # Googlebot de verdade
             ('GET', ua_google, '6.6.6.6', False),        # só finge ser Googlebot
             ('POST', ua_google, '66.249.66.1', False),   # isenção só para leitura
             ('GET', 'Mozilla/5.0 Chrome/130', '66.249.66.1', False)]
    for metodo, ua, ip, esperado in casos:
        with A.app.test_request_context('/', method=metodo, headers={'User-Agent': ua},
                                        environ_base={'REMOTE_ADDR': ip}):
            assert A._buscador_verificado() is esperado, (metodo, ua, ip)
    with A.app.test_request_context('/', headers={'User-Agent': ua_google},
                                    environ_base={'REMOTE_ADDR': '66.249.66.1'}):
        A._buscador_verificado()
    assert chamadas.count('66.249.66.1') == 1   # cache: DNS uma vez por IP


def test_links_internos_do_blog(client):
    """Todo post linka o pilar do seu tema e nenhum post fica órfão
    (antes cada post listava os outros 29, sem contexto)."""
    import links_internos
    mapa = A._LINKS_BLOG
    assert not links_internos.orfaos(mapa)
    for p in A.BLOG_POSTS:
        html = client.get(f"/blog/{p['slug']}").get_data(as_text=True)
        bloco = html.split('class="related"', 1)[1]
        alvos = set(re.findall(r'href="/blog/([^"]+)"', bloco))
        info = mapa[p['slug']]
        assert p['slug'] not in alvos
        assert 1 <= len(alvos) <= 15, (p['slug'], len(alvos))
        if info['pilar']:
            assert info['pilar']['slug'] in alvos, p['slug']
        for _, url in info['paginas']:
            assert f'href="{url}"' in bloco, (p['slug'], url)


def test_monitor_de_crawlers(client, monkeypatch):
    """Robô conhecido é gravado com nome e status em qualquer resposta
    (inclusive llms.txt e 404); pessoa lendo llms.txt não conta como visita."""
    gravados = []
    monkeypatch.setattr(A, '_traf_enfileirar', lambda tipo, v: gravados.append(v))
    monkeypatch.setattr(A, '_dns_confere', lambda ip, dominios: True)
    A._buscador_cache.clear()
    gpt = 'Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; GPTBot/1.2; +https://openai.com/gptbot'
    client.get('/llms.txt', headers={'User-Agent': gpt})
    client.get('/llms.txt', headers={'User-Agent': 'Mozilla/5.0 Chrome/130.0'})
    client.get('/precos', headers={'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'})
    client.get('/pagina-que-nao-existe', headers={'User-Agent': 'Mozilla/5.0 (compatible; ClaudeBot/1.0; +claudebot@anthropic.com)'})
    vistos = [(v[0], v[7], v[8], v[9]) for v in gravados]
    assert ('/llms.txt', 'GPTBot', False, 200) in vistos
    assert not any(p == '/llms.txt' and robo == '' for p, robo, _, _ in vistos)
    assert ('/precos', 'Googlebot', True, 200) in vistos
    assert ('/pagina-que-nao-existe', 'ClaudeBot', False, 404) in vistos
