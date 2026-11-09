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


def test_resposta_direta_nos_pilares(client):
    """Formato citável: 40-60 palavras logo abaixo do H1 nos pilares."""
    import links_internos
    for c in links_internos.CLUSTERS.values():
        post = next(p for p in A.BLOG_POSTS if p['slug'] == c['pilar'])
        assert post.get('resposta'), c['pilar']
        assert 40 <= len(post['resposta'].split()) <= 60, (c['pilar'], len(post['resposta'].split()))
        html = client.get(f"/blog/{c['pilar']}").get_data(as_text=True)
        cabecalho = html.split('<h1>', 1)[1].split('</header>', 1)[0]
        assert 'class="resposta-direta"' in cabecalho, c['pilar']


def _relatorio_exemplo():
    from datetime import datetime
    return {'gerado_em': datetime(2026, 11, 9, 12, 0), 'base_mes': '2026-10-13', 'dados': {
        'total': 1000, 'com_socio': 330, 'com_telefone': 980, 'com_email': 930,
        'abertura_mais_recente': '2026-10-11',
        'por_uf': [{'uf': 'SP', 'nome': 'São Paulo', 'n': 300}, {'uf': 'RS', 'nome': 'Rio Grande do Sul', 'n': 100}],
        'por_ano': [{'ano': 2024, 'n': 90}, {'ano': 2025, 'n': 120}, {'ano': 2026, 'n': 110}],
        'por_porte': [{'porte': 'Microempresa', 'n': 800}, {'porte': 'Pequena (EPP)', 'n': 200}],
        'por_segmento': [{'codigo': '2512800', 'nome': 'Metalúrgicas', 'slug': 'metalurgicas', 'n': 50}],
        'cidades': [{'municipio': 'SAO PAULO', 'uf': 'SP', 'n': 200}]}}


def test_relatorio_de_dados_e_embed(client, monkeypatch):
    monkeypatch.setattr(A, '_relatorio_dados', _relatorio_exemplo)
    r = client.get('/dados/empresas-ativas-no-brasil')
    assert r.status_code == 200
    d = _extrair(r.get_data(as_text=True))
    assert d['title'] and len(d['title']) <= A.TITULO_MAX and d['h1'] == 1
    tipos = [json.loads(b).get('@type') for b in d['ld']]
    assert 'Dataset' in tipos and 'BreadcrumbList' in tipos
    html = r.get_data(as_text=True)
    assert html.count('<svg') == 4 and 'outubro de 2026' in html and 'São Paulo' in html
    e = client.get('/dados/empresas-ativas-no-brasil/embed/estados')
    assert e.status_code == 200 and 'X-Frame-Options' not in e.headers
    assert 'noindex' in e.get_data(as_text=True) and 'turbovenda.com.br/dados/empresas-ativas-no-brasil' in e.get_data(as_text=True)
    assert client.get('/dados/empresas-ativas-no-brasil/embed/nao-existe').status_code == 404
    assert client.get('/precos').headers.get('X-Frame-Options') == 'SAMEORIGIN'


def test_kit_de_imprensa(client, monkeypatch):
    monkeypatch.setattr(A, '_relatorio_dados', _relatorio_exemplo)
    r = client.get('/imprensa')
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and 'Fonte: TurboVenda' in html and '1.000' in html
    monkeypatch.setattr(A, '_relatorio_dados', lambda: None)
    assert client.get('/imprensa').status_code == 200   # sem relatório, sem números


def test_paginas_de_video(client, monkeypatch):
    """Sem vídeo cadastrado não existe página; com vídeo, VideoObject com
    capítulos (Clip) e transcrição."""
    import videos
    assert client.get('/videos').status_code == 404
    monkeypatch.setattr(videos, 'VIDEOS', [{
        'slug': 'lista-de-empresas-por-cnae', 'titulo': 'Como montar uma lista de empresas por CNAE',
        'descricao': 'Passo a passo com os dados abertos da Receita.', 'youtube_id': 'abc123XYZ00',
        'publicado': '2026-11-20', 'duracao': 'PT6M10S',
        'capitulos': [(0, 'Abertura'), (45, 'O que é CNAE'), (150, 'Filtrando por cidade')],
        'transcricao': 'Primeiro parágrafo.\n\nSegundo parágrafo.',
        'relacionado': '/blog/o-que-e-cnae-prospeccao'}])
    r = client.get('/videos/lista-de-empresas-por-cnae')
    d = _extrair(r.get_data(as_text=True))
    assert r.status_code == 200 and d['h1'] == 1 and len(d['title']) <= A.TITULO_MAX
    video = next(json.loads(b) for b in d['ld'] if json.loads(b).get('@type') == 'VideoObject')
    assert [c['startOffset'] for c in video['hasPart']] == [0, 45, 150]
    assert video['hasPart'][0]['endOffset'] == 45 and 'transcript' in video
    assert client.get('/videos').status_code == 200
    assert client.get('/videos/nao-existe').status_code == 404


def test_painel_organico_so_para_admin(client):
    r = client.get('/admin/organico')
    assert r.status_code == 302   # sem login de admin, vai para o login
    with client.session_transaction() as s:
        s['admin_auth'] = True
    r = client.get('/admin/organico')
    assert r.status_code == 200 and 'Busca orgânica e IA' in r.get_data(as_text=True)
    assert 'noindex' in r.get_data(as_text=True)
    with client.session_transaction() as s:
        s.pop('admin_auth', None)
