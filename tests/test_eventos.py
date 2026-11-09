# -*- coding: utf-8 -*-
"""Instrumentação do funil (Fase 1 do Prompt 2): primeiro e último toque em
cookies próprios sem dado pessoal, respeito à recusa do banner e eventos do
navegador só da lista fechada."""
import json
import os
import sys

import pytest

if not os.environ.get('DATABASE_URL'):
    pytest.skip('precisa de DATABASE_URL (mesmo falsa) para importar o app', allow_module_level=True)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import app  # noqa: E402

CHROME = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36'


@pytest.fixture
def fila(monkeypatch):
    itens = []
    monkeypatch.setattr(app, '_traf_enfileirar', lambda tipo, v: itens.append((tipo, v)))
    return itens


def _cookie(resp, nome):
    for h in resp.headers.getlist('Set-Cookie'):
        if h.startswith(nome + '='):
            return h
    return None


def test_primeiro_e_ultimo_toque(fila):
    c = app.app.test_client()
    r = c.get('/precos?utm_source=linkedin&utm_campaign=post-1',
              headers={'User-Agent': CHROME, 'Referer': 'https://www.google.com/'})
    assert _cookie(r, 'tv_ft') and _cookie(r, 'tv_lt') and 'HttpOnly' in _cookie(r, 'tv_ft')
    with app.app.test_request_context('/', headers={'Cookie': f"tv_ft={c.get_cookie('tv_ft').value}"}):
        primeiro, ultimo = app._toques_do_visitante()
    assert primeiro['lp'] == '/precos' and primeiro['ref'] == 'www.google.com'
    assert primeiro['us'] == 'linkedin' and primeiro['uc'] == 'post-1' and ultimo is None
    # navegação interna não troca o primeiro toque nem cria último
    r2 = c.get('/blog', headers={'User-Agent': CHROME, 'Referer': 'https://www.turbovenda.com.br/precos'})
    assert not _cookie(r2, 'tv_ft') and not _cookie(r2, 'tv_lt')


def test_recusa_no_banner_nao_grava_e_apaga(fila):
    c = app.app.test_client()
    c.set_cookie('tv_consent', 'rejected')
    c.set_cookie('tv_ft', json.dumps({'lp': '/x'}))
    r = c.get('/precos', headers={'User-Agent': CHROME, 'Referer': 'https://www.google.com/'})
    ft = _cookie(r, 'tv_ft')
    assert ft and ('Max-Age=0' in ft or 'expires=Thu, 01 Jan 1970' in ft.lower() or 'Expires=Thu, 01 Jan 1970' in ft)
    assert not _cookie(r, 'tv_lt')


def test_eventos_do_navegador_so_da_lista(fila):
    c = app.app.test_client()
    c.post('/api/t/evento', json={'nome': 'paywall_viewed', 'origem': 'modal_painel'})
    c.post('/api/t/evento', json={'nome': 'payment_succeeded'})   # compra só nasce no servidor
    evs = [v for t, v in fila if t == 'ev']
    assert [e[0] for e in evs] == ['paywall_viewed']
    assert evs[0][2].adapted == {'origem': 'modal_painel', 'plano': ''}


def test_experimento_estavel_por_visitante_e_respeita_recusa():
    vistas = set()
    for i in range(40):
        with app.app.test_request_context('/', headers={'Cookie': f'tv_vid=visitante{i}'}):
            v1 = app.variante('pseo_cta')
            assert app.variante('pseo_cta') == v1            # mesma pessoa, mesma versão
            assert app.g.experimentos == {'pseo_cta': v1}    # exposição registrada
            vistas.add(v1)
    assert vistas == {'a', 'b'}                              # as duas versões aparecem
    with app.app.test_request_context('/', headers={'Cookie': 'tv_consent=rejected; tv_vid=x'}):
        assert app.variante('pseo_cta') == 'a'
    with app.app.test_request_context('/'):
        assert app.variante('pseo_cta', registrar=False) is None   # sem visitante, sem atribuição
        assert not hasattr(app.g, 'experimentos')


def test_descadastro_em_um_clique(monkeypatch, fila):
    feitos = []

    class Banco:
        def cursor(self):
            return self

        def execute(self, sql, params=None):
            feitos.append((' '.join(sql.split()), params))

        def commit(self):
            pass

        def close(self):
            pass
    monkeypatch.setattr(app, '_conn', lambda *a, **k: Banco())
    c = app.app.test_client()
    assert 'Link inválido' in c.get('/descadastrar/7.adulterado').get_data(as_text=True)
    assert not feitos
    r = c.get('/descadastrar/' + app._token_descadastro(7))
    assert 'não vai mais receber' in r.get_data(as_text=True)
    assert feitos == [('UPDATE users SET emails_marketing_off = TRUE WHERE id = %s', (7,))]
    assert [v[0] for t, v in fila if t == 'ev'] == ['email_unsubscribed']


def test_link_de_indicacao_assinado_e_capturado(fila):
    codigo = app._codigo_indicacao(42)
    assert app._quem_indicou(codigo) == 42
    assert app._quem_indicou('42-falso') is None and app._quem_indicou('') is None
    c = app.app.test_client()
    r = c.get(f'/?indica={codigo}', headers={'User-Agent': CHROME})
    assert _cookie(r, 'tv_lt')
    with app.app.test_request_context('/', headers={'Cookie': f"tv_lt={c.get_cookie('tv_lt').value}"}):
        assert app._toques_do_visitante()[1]['in'] == codigo
