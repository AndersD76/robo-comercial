# -*- coding: utf-8 -*-
"""Rotas do crescimento orgânico sem banco (mesmo modo da guarda de SEO):
iscas, captura de lead, eventos, institucionais, sitemaps e painel."""
import json
import os
import re
import sys

import pytest

if not os.environ.get('DATABASE_URL'):
    pytest.skip('precisa de DATABASE_URL (mesmo falsa) para importar o app', allow_module_level=True)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import app as A  # noqa: E402
import iscas  # noqa: E402
import sequencias  # noqa: E402


@pytest.fixture
def client():
    A.app.config['TESTING'] = True
    A.limiter.enabled = False
    with A.app.test_client() as c:
        yield c


def test_todas_as_iscas_novas_abrem_com_seo_e_consentimento(client):
    for k in iscas.NOVAS:
        url = iscas.url_de(k)
        r = client.get(url)
        assert r.status_code == 200, url
        html = r.get_data(as_text=True)
        assert f'<link rel="canonical" href="https://www.turbovenda.com.br{url}">' in html
        assert 'content="index, follow"' in html
        assert "gtag('consent','default'" in html and 'id="cookie-accept"' in html
        assert len(re.findall(r'<h1[\s>]', html)) == 1
        for bloco in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
            json.loads(bloco)


def test_resultado_na_url_compartilhavel_e_noindex(client):
    q = '&'.join(f'{k}=sim' for k, *_ in iscas._DIAG)
    r = client.get(f'/ferramentas/diagnostico-de-prospeccao?{q}')
    html = r.get_data(as_text=True)
    assert 'Seu resultado' in html and '100/100' in html
    assert 'content="noindex, follow"' in html                # a versão com parâmetros não concorre com a canônica
    assert '/cadastro?utm_source=site&amp;utm_medium=isca&amp;utm_campaign=diagnostico-prospeccao' in html
    assert 'name="opt_in"' in html and 'checked' not in html.split('name="opt_in"')[1][:40]   # opt-in desmarcado


def test_planilha_baixa_em_csv(client):
    r = client.get('/ferramentas/planilha-de-prospeccao.csv')
    assert r.status_code == 200 and r.mimetype == 'text/csv'
    assert 'attachment' in r.headers['Content-Disposition']


def test_ferramenta_inexistente_e_as_antigas_nao_sao_sequestradas(client):
    assert client.get('/ferramentas/nao-existe').status_code == 404
    r = client.get('/ferramentas/calculadora-de-leads')
    assert r.status_code == 200 and 'diagnostico-de-prospeccao' not in r.request.path


def test_captura_de_lead_valida_antes_de_gravar(client, monkeypatch):
    def proibido(*a, **k):
        raise AssertionError('não devia gravar')
    monkeypatch.setattr(sequencias, 'registrar', proibido)
    assert client.post('/api/isca/nao-existe/lead', json={'email': 'a@b.com.br'}).status_code == 404
    r = client.post('/api/isca/calculadora-cac/lead', json={'email': 'sem-arroba'})
    assert r.status_code == 400
    r = client.post('/api/isca/calculadora-cac/lead', json={'email': 'a@b.com.br', 'params': {}})
    assert r.status_code == 400 and 'Preencha' in r.get_json()['erro']


def test_captura_grava_manda_resultado_e_avisa_o_dono(client, monkeypatch):
    gravados, enviados, eventos = [], [], []

    class Cur:
        connection = None

        def execute(self, *a, **k):
            pass

    class Conn:
        def cursor(self):
            c = Cur()
            c.connection = self
            return c

        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(A, '_conn', lambda *a, **k: Conn())
    monkeypatch.setattr(sequencias, 'registrar', lambda cur, dados: gravados.append(dados) or 77)
    monkeypatch.setattr(A, '_send_system_email', lambda para, assunto, html: enviados.append((para, assunto, html)))
    monkeypatch.setattr(A, '_evento', lambda nome, uid=None, **p: eventos.append((nome, p)))
    monkeypatch.setenv('ALERTAS_EMAIL', 'dono@exemplo.com.br')
    import threading
    monkeypatch.setattr(threading, 'Thread', lambda target, args, daemon: type('T', (), {'start': lambda s: target(*args)})())
    params = {'marketing': '1000', 'vendas': '1000', 'novos': '2', 'ticket': '300'}
    r = client.post('/api/isca/calculadora-cac/lead', json={'email': 'Cliente@Empresa.com.br', 'opt_in': True,
                                                            'params': params, 'consulta': 'calculadora de cac'})
    assert r.status_code == 200 and r.get_json() == {'ok': True}
    assert gravados[0]['opt_in'] is True and gravados[0]['resultado']['dados']['cac'] == 1000.0
    para = [e[0] for e in enviados]
    assert 'Cliente@Empresa.com.br' in para and 'dono@exemplo.com.br' in para
    resultado = next(e for e in enviados if e[0] == 'Cliente@Empresa.com.br')
    assert '/descadastrar/l77.' in resultado[2]
    assert eventos == [('lead_capturado', {'page_type': 'isca', 'cluster': 'gestao', 'consulta_alvo': 'calculadora de cac',
                                           'isca_id': 'calculadora-cac', 'opt_in': True})]


def test_evento_do_navegador_so_com_props_conferidas(client, monkeypatch):
    eventos = []
    monkeypatch.setattr(A, '_evento', lambda nome, uid=None, **p: eventos.append((nome, p)))
    client.post('/api/t/evento', json={'nome': 'isca_vista', 'path': '/glossario/icp',
                                       'props': {'page_type': 'glossario', 'cluster': 'prospeccao', 'isca_id': 'gerador-icp',
                                                 'consulta_alvo': 'o que é icp', 'lixo': 'x' * 900}})
    client.post('/api/t/evento', json={'nome': 'payment_succeeded', 'props': {'valor': 999}})   # compra nunca do navegador
    client.post('/api/t/evento', json={'nome': 'isca_vista', 'props': {'page_type': '<script>', 'isca_id': 'falsa'}})
    assert eventos[0] == ('isca_vista', {'page_type': 'glossario', 'cluster': 'prospeccao', 'isca_id': 'gerador-icp',
                                         'consulta_alvo': 'o que é icp', 'path': '/glossario/icp'})
    assert eventos[1] == ('isca_vista', {})
    assert len(eventos) == 2


def test_descadastro_do_lead_em_um_clique(client, monkeypatch):
    feitos = []

    class Cur:
        rowcount = 1

        def execute(self, sql, params=None):
            feitos.append((' '.join(sql.split()), params))

        def fetchone(self):
            return {'email': 'x@y.com.br'}

    class Conn:
        def cursor(self):
            return Cur()

        def commit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(A, '_conn', lambda *a, **k: Conn())
    monkeypatch.setattr(A, '_evento', lambda *a, **k: None)
    token = sequencias.token_lead(5, A.app.secret_key)
    r = client.get(f'/descadastrar/{token}')
    assert 'não vai mais receber' in r.get_data(as_text=True)
    assert any(s.startswith('UPDATE leads_isca SET descadastrado_em') for s, _ in feitos)
    r = client.get('/descadastrar/l5.' + 'a' * 24)
    assert 'Link inválido' in r.get_data(as_text=True)


def test_institucionais(client):
    r = client.get('/sobre')
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and 'ANDERS CONSULTORIA' in html and 'suporte@turbovenda.com.br' in html
    r = client.get('/politica-editorial')
    html = r.get_data(as_text=True)
    assert 'Uso de IA' in html and 'Revisão humana' in html
    assert client.get('/autor/qualquer').status_code == 404   # sem autor configurado, sem página de autor


def test_paginas_do_banco_sem_banco_nao_quebram(client):
    assert client.get('/glossario/icp').status_code == 404
    assert client.get('/cnae/4930202').status_code == 404
    assert client.get('/blog/nao-existe-no-banco').status_code == 404
    r = client.get('/glossario')
    assert r.status_code == 200 and 'noindex' in r.get_data(as_text=True)   # hub vazio não é indexado


def test_sitemap_por_tipo_e_indexnow(monkeypatch):
    monkeypatch.setattr(A, '_urls_crescimento', lambda: [('https://www.turbovenda.com.br/glossario/icp', '2026-11-26', 'glossario'),
                                                          ('https://www.turbovenda.com.br/cnae/4930202', '2026-11-26', 'programatica')])
    assert A._sitemaps_crescimento() and A._sitemaps_crescimento()[0].endswith('/sitemap-conteudo.xml')
    todas = A._todas_urls_sitemap()
    assert todas['https://www.turbovenda.com.br/glossario/icp'] == '2026-11-26'   # IndexNow avisa com lastmod real


def test_painel_so_para_admin(client):
    r = client.get('/admin/crescimento')
    assert r.status_code in (302, 401, 403)
    r = client.post('/admin/crescimento/onda', data={'limite': '10'})
    assert r.status_code in (302, 401, 403)
