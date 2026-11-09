# -*- coding: utf-8 -*-
"""Regressões de segurança do Prompt 3 (qa/RELATORIO-QUALIDADE-SEGURANCA.md).
Cada teste falhava antes da correção correspondente."""
import os
import sys
import time

import pytest

if not os.environ.get('DATABASE_URL'):
    pytest.skip('precisa de DATABASE_URL (mesmo falsa) para importar o app', allow_module_level=True)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import app  # noqa: E402


@pytest.fixture
def fila(monkeypatch):
    itens = []
    monkeypatch.setattr(app, '_traf_enfileirar', lambda tipo, v: itens.append((tipo, v)))
    return itens


# QA-SEC-001: webhook da Unipile trocava a conta de e-mail de qualquer cliente
def test_webhook_unipile_recusa_nome_sem_assinatura(monkeypatch):
    gravou = []
    monkeypatch.setattr(app, '_conn', lambda *a, **k: gravou.append(a) or pytest.fail('não devia gravar'))
    c = app.app.test_client()
    for nome in ('emp_7', 'emp_7:9999999999:assinaturafalsa', ''):
        r = c.post('/webhook/unipile', json={'status': 'CREATION_SUCCESS', 'account_id': 'acc_x', 'name': nome})
        assert r.status_code == 403
    assert not gravou


def test_nome_unipile_assinado_e_com_validade():
    nome = app._nome_unipile('emp_7')
    assert app._schema_do_nome_unipile(nome) == 'emp_7'
    assert app._schema_do_nome_unipile(nome.replace('emp_7', 'emp_8', 1)) is None   # outro cliente
    assert app._schema_do_nome_unipile(nome, agora=time.time() + 3 * 3600) is None    # vencido


# QA-SEC-002: rotas públicas de agendamento sem limite (cada acesso varre todos os clientes)
def test_rotas_de_agendamento_tem_limite(monkeypatch):
    monkeypatch.setattr(app, '_find_lead_by_token', lambda token: (None, None))
    antes = app.limiter.enabled
    app.limiter.enabled = True
    try:
        app.limiter.reset()
        c = app.app.test_client()
        codigos = [c.get('/api/agendar/token-qualquer/slots?data=2026-11-20').status_code for _ in range(31)]
    finally:
        app.limiter.enabled = antes
        app.limiter.reset()
    assert codigos[0] == 404 and codigos[-1] == 429


# QA-SEC-004: sem CSP nenhuma
def test_cabecalhos_de_seguranca():
    r = app.app.test_client().get('/precos')
    h = r.headers
    assert "object-src 'none'" in h['Content-Security-Policy']
    assert "frame-ancestors 'self'" in h['Content-Security-Policy']
    assert 'report-uri /api/csp-report' in h['Content-Security-Policy-Report-Only']
    assert h['X-Content-Type-Options'] == 'nosniff' and h['X-Frame-Options'] == 'SAMEORIGIN'
    assert app.app.config['MAX_CONTENT_LENGTH'] <= 2 * 1024 * 1024


def test_relatorio_de_csp_aceito_sem_csrf(fila):
    r = app.app.test_client().post(
        '/api/csp-report', data='{"csp-report": {"blocked-uri": "https://mal.example/x.js?a=1", '
        '"effective-directive": "script-src-elem", "document-uri": "https://www.turbovenda.com.br/precos?q=1"}}',
        content_type='application/csp-report')
    assert r.status_code == 204
    ev = [v for t, v in fila if t == 'ev'][-1]
    assert ev[0] == 'csp_violation'
    assert ev[2].adapted == {'diretiva': 'script-src-elem', 'bloqueado': 'mal.example', 'pagina': '/precos'}
