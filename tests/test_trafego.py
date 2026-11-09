# -*- coding: utf-8 -*-
"""Telemetria: página só pré-carregada pelo Chrome (resultados do Google,
"Sec-Purpose: prefetch") não conta como visita; conta quando é aberta, pelo
aviso /api/t/pv. Antes disso a telemetria contava ~2,4x os cliques do GSC."""
import os
import sys

import pytest

if not os.environ.get('DATABASE_URL'):
    pytest.skip('precisa de DATABASE_URL (mesmo falsa) para importar o app', allow_module_level=True)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import app  # noqa: E402

CHROME = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36'


@pytest.fixture
def gravados(monkeypatch):
    itens = []
    monkeypatch.setattr(app, '_traf_enfileirar', lambda tipo, v: itens.append((tipo, v)))
    return itens


def _cliente():
    return app.app.test_client()


def test_visita_normal_do_google_conta_como_entrada(gravados):
    r = _cliente().get('/precos', headers={'User-Agent': CHROME, 'Referer': 'https://www.google.com/'})
    assert r.status_code == 200
    path, ref, _, _, _, is_bot, entrada, robo, _, _ = gravados[-1][1]
    assert (path, ref, is_bot, entrada, robo) == ('/precos', 'https://www.google.com/', False, True, '')
    assert '/api/t/pv' not in r.get_data(as_text=True)


def test_precarregamento_nao_conta_e_leva_o_aviso(gravados):
    r = _cliente().get('/precos', headers={'User-Agent': CHROME, 'Referer': 'https://www.google.com/',
                                           'Sec-Purpose': 'prefetch;anonymous-client-ip'})
    assert r.status_code == 200
    _, _, _, _, _, is_bot, entrada, robo, _, _ = gravados[-1][1]
    assert (is_bot, entrada, robo) == (True, False, 'precarregamento')
    assert '/api/t/pv' in r.get_data(as_text=True)


def test_aviso_de_abertura_registra_a_entrada(gravados):
    r = _cliente().post('/api/t/pv', json={'path': '/precos', 'ref': 'https://www.google.com/'},
                        headers={'User-Agent': CHROME})
    assert r.status_code == 204
    path, ref, _, _, _, is_bot, entrada, robo, _, _ = gravados[-1][1]
    assert (path, ref, is_bot, entrada, robo) == ('/precos', 'https://www.google.com/', False, True, '')


def test_aviso_ignora_robo_e_area_logada(gravados):
    c = _cliente()
    c.post('/api/t/pv', json={'path': '/precos'}, headers={'User-Agent': 'Googlebot/2.1'})
    c.post('/api/t/pv', json={'path': '/admin/organico'}, headers={'User-Agent': CHROME})
    assert not [v for t, v in gravados if t == 'pv']
