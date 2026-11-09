# -*- coding: utf-8 -*-
"""Guarda de SEO das páginas programáticas (/empresas): as ~10 mil páginas
que trazem a maior parte do tráfego do Google.

Usa o modo de desenvolvimento do app (PSEO_SQLITE) com a base sintética do
`cnpj_ingest.py --sample`: renderiza tudo o que está no sitemap e confere
título, descrição, canonical, robots, JSON-LD, H1 e lastmod.
"""
import os
import re
import subprocess
import sys

import pytest

RAIZ = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, RAIZ)

if not os.environ.get('DATABASE_URL'):
    # O app sai na importação sem DATABASE_URL; o CI roda este arquivo num
    # passo próprio, com um endereço de banco que não existe (ver ci.yml)
    pytest.skip('DATABASE_URL não definido', allow_module_level=True)

import app as A  # noqa: E402
from tests.test_seo import _extrair  # noqa: E402

BASE = 'https://www.turbovenda.com.br'


@pytest.fixture(scope='module')
def client(tmp_path_factory, request):
    base = str(tmp_path_factory.mktemp('pseo') / 'pseo.sqlite')
    env = {k: v for k, v in os.environ.items() if k != 'DATABASE_URL'}
    subprocess.run([sys.executable, os.path.join(RAIZ, 'scripts', 'cnpj_ingest.py'),
                    '--sample', '--sqlite', base], env=env, check=True,
                   capture_output=True)
    mp = pytest.MonkeyPatch()
    request.addfinalizer(mp.undo)
    mp.setattr(A, '_PSEO_SQLITE', base)
    # A base sintética tem poucas empresas por cidade: baixa os limiares para
    # que todos os tipos de página entrem no sitemap
    mp.setattr(A, 'PSEO_MIN_EMPRESAS', 2)
    mp.setattr(A, 'PSEO_MIN_INDEX', 3)
    mp.setattr(A, 'PSEO_ESTADO_INDEX', 3)
    mp.setattr(A, 'PSEO_CIDADE_HUB_INDEX', 1)
    mp.setattr(A, 'PSEO_PAGE_SIZE', 2)
    A._pseo_cache['data'] = None
    A._pseo_base_cache['em'] = 0.0
    request.addfinalizer(lambda: A._pseo_cache.update(data=None))
    A.app.config['TESTING'] = True
    A.limiter.enabled = False
    with A.app.test_client() as c:
        yield c


@pytest.fixture(scope='module')
def sitemap_programatico(client):
    r = client.get('/sitemap-empresas-1.xml')
    assert r.status_code == 200
    xml = r.get_data(as_text=True)
    urls = re.findall(r'<loc>([^<]+)</loc>', xml)
    datas = re.findall(r'<lastmod>([^<]+)</lastmod>', xml)
    return urls, datas


def test_sitemap_tem_todos_os_tipos_e_lastmod_real(sitemap_programatico):
    urls, datas = sitemap_programatico
    caminhos = [u.replace(BASE, '') for u in urls]
    assert any(re.match(r'^/empresas/[^/]+$', c) for c in caminhos)
    assert any('/estado/' in c for c in caminhos)
    assert any(c.startswith('/empresas/cidade/') for c in caminhos)
    assert any(re.match(r'^/empresas/(?!cidade/)[^/]+/(?!estado)[^/]+$', c) for c in caminhos)
    # lastmod = data da base (abertura mais recente), igual em todas, nunca o futuro
    assert datas and len(set(datas)) == 1 and re.match(r'^\d{4}-\d{2}-\d{2}$', datas[0])
    assert datas[0] <= A._dt.date.today().isoformat()


def test_paginas_do_sitemap_prontas_para_indexar(client, sitemap_programatico):
    urls, _ = sitemap_programatico
    titulos = {}
    for url in urls:
        r = client.get(url.replace(BASE, ''))
        assert r.status_code == 200, url
        d = _extrair(r.get_data(as_text=True))
        assert d['title'] and len(d['title']) <= A.TITULO_MAX, (url, d['title'])
        assert d['description'] and len(d['description']) <= A.DESCRICAO_MAX, url
        assert d['canonical'] == url, (url, d['canonical'])
        assert 'noindex' not in d['robots'], url
        assert d['h1'] == 1, url
        for bloco in d['ld']:
            A.json.loads(bloco)
        titulos.setdefault(d['title'], []).append(url)
    assert not {t: u for t, u in titulos.items() if len(u) > 1}


def test_paginacao_canonical_proprio_e_noindex(client, sitemap_programatico):
    urls, _ = sitemap_programatico
    combos = [u for u in urls if re.match(rf'^{BASE}/empresas/(?!cidade/)[^/]+/(?!estado)[^/]+$', u)]
    for url in combos:
        r = client.get(url.replace(BASE, '') + '?pagina=2')
        if r.status_code != 200:
            continue
        d = _extrair(r.get_data(as_text=True))
        assert d['canonical'] == url + '?pagina=2'
        assert 'noindex' in d['robots']
        assert '(pág. 2)' in d['title'] and len(d['title']) <= A.TITULO_MAX
        return
    pytest.fail('nenhuma combinação com 2 páginas na base sintética')


def test_combinacao_inexistente_da_404(client):
    assert client.get('/empresas/segmento-que-nao-existe/cidade-xx').status_code == 404


def test_cta_leva_segmento_e_cidade_ao_cadastro(client, sitemap_programatico):
    """Quem clica numa página de segmento × cidade chega ao cadastro com o
    alvo, e a conta nasce com o robô buscando exatamente aquelas empresas."""
    urls, _ = sitemap_programatico
    url = next(u for u in urls if re.match(rf'^{BASE}/empresas/(?!cidade/)[^/]+/(?!estado)[^/]+$', u))
    seg_slug, mun_slug = url.replace(BASE + '/empresas/', '').split('/')
    html = client.get(url.replace(BASE, '')).get_data(as_text=True)
    assert 'data-cta="pseo-topo-a"' in html or 'data-cta="pseo-topo-b"' in html
    assert 'data-cta="pseo-rodape"' in html
    assert f'alvo={seg_slug}&amp;cidade={mun_slug}' in html

    alvo = A._alvo_pseo(seg_slug, mun_slug)
    assert alvo and alvo['seg_slug'] == seg_slug and alvo['n'] >= A.PSEO_MIN_EMPRESAS
    cadastro = client.get(f'/cadastro?alvo={seg_slug}&cidade={mun_slug}').get_data(as_text=True)
    assert 'Seu robô começa por' in cadastro and alvo['municipio'] in cadastro
    assert f'name="alvo" value="{seg_slug}"' in cadastro

    termos = A._termos_do_alvo(alvo)
    assert len(termos) == len(set(termos)) >= 10
    assert all(alvo['municipio'] in t or alvo['uf'] in t for t in termos)
    # alvo inválido não quebra o cadastro
    assert A._alvo_pseo('nao-existe', mun_slug) is None
    assert 'Seu robô começa por' not in client.get('/cadastro?alvo=x&cidade=y').get_data(as_text=True)
