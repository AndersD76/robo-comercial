# -*- coding: utf-8 -*-
"""IndexNow em fluxo: o Bing Webmaster marca "batch mode" quando o site manda
milhares de URLs de uma vez. Cada envio leva no máximo INDEXNOW_POR_ENVIO URLs
e há uma pausa entre envios."""
import os
import sys

import pytest

if not os.environ.get('DATABASE_URL'):
    pytest.skip('precisa de DATABASE_URL (mesmo falsa) para importar o app', allow_module_level=True)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import app  # noqa: E402


def _fila(n):
    return [(f'https://www.turbovenda.com.br/p{i}', '2026-10-13') for i in range(n)]


def test_envia_em_grupos_pequenos_com_pausa(monkeypatch):
    grupos, pausas = [], []
    monkeypatch.setattr(app, '_indexnow_pendencias', lambda forcar=False: _fila(25))
    monkeypatch.setattr(app, '_indexnow_enviar_grupo', lambda g: grupos.append(g) or 202)
    aceitas, total = app._indexnow_rodada(dormir=pausas.append)
    assert (aceitas, total) == (25, 25)
    assert [len(g) for g in grupos] == [10, 10, 5]
    assert max(len(g) for g in grupos) <= app.INDEXNOW_POR_ENVIO <= 100
    assert pausas == [app.INDEXNOW_INTERVALO] * 3 and app.INDEXNOW_INTERVALO >= 30


def test_para_depois_de_5_falhas_seguidas(monkeypatch):
    chamadas = []
    monkeypatch.setattr(app, '_indexnow_pendencias', lambda forcar=False: _fila(200))
    monkeypatch.setattr(app, '_indexnow_enviar_grupo', lambda g: chamadas.append(g) or 429)
    assert app._indexnow_rodada(dormir=lambda s: None) == (0, 200)
    assert len(chamadas) == 5


def test_fila_vazia_nao_envia(monkeypatch):
    monkeypatch.setattr(app, '_indexnow_pendencias', lambda forcar=False: [])
    monkeypatch.setattr(app, '_indexnow_enviar_grupo', lambda g: pytest.fail('não devia enviar'))
    assert app._indexnow_rodada(dormir=lambda s: None) == (0, 0)
