# -*- coding: utf-8 -*-
"""Testes de integração (Fase 1 do Prompt 3) contra um PostgreSQL de verdade.

Fica fora de tests/ de propósito: aqui o app é importado com um banco real
(e descartável), o que não pode vazar para a suíte com banco falso.

Banco: PG_TESTE_URI (ex.: service do CI) ou, sem ela, um PostgreSQL local
via pgserver (sem Docker). Cada rodada cria um banco novo, aplica o schema do
zero (o app cria tudo na importação) e apaga no fim. Dados 100% sintéticos.

Uso: python -m pytest testes_integracao -q
"""
import os
import sys
import tempfile
import time
import uuid
from urllib.parse import urlsplit, urlunsplit

import psycopg2
import pytest

RAIZ = os.path.join(os.path.dirname(__file__), '..')


def _uri_servidor():
    if os.environ.get('PG_TESTE_URI'):
        return os.environ['PG_TESTE_URI']
    import pgserver
    pasta = os.environ.get('PG_TESTE_DIR') or os.path.join(tempfile.gettempdir(), 'turbovenda_pg_teste')
    return pgserver.get_server(pasta, cleanup_mode=None).get_uri()


def _com_banco(uri, nome):
    p = urlsplit(uri)
    return urlunsplit((p.scheme, p.netloc, '/' + nome, p.query, p.fragment))


_SERVIDOR = _uri_servidor()
_BANCO = 'tv_teste_' + uuid.uuid4().hex[:10]
_adm = psycopg2.connect(_SERVIDOR)
_adm.autocommit = True
_adm.cursor().execute(f'CREATE DATABASE {_BANCO}')
_adm.close()

os.environ['DATABASE_URL'] = _com_banco(_SERVIDOR, _BANCO)
os.environ.pop('RAILWAY_ENVIRONMENT_ID', None)     # sem threads de fundo
os.environ.setdefault('SECRET_KEY', 'segredo-de-teste-integracao')
sys.path.insert(0, RAIZ)
import app as A  # noqa: E402  (cria o schema público do zero)

A.app.config['TESTING'] = True
A.limiter.enabled = False


def pytest_sessionfinish(session, exitstatus):
    adm = psycopg2.connect(_SERVIDOR)
    adm.autocommit = True
    try:
        adm.cursor().execute(f'DROP DATABASE IF EXISTS {_BANCO} WITH (FORCE)')
    finally:
        adm.close()


@pytest.fixture(autouse=True)
def sem_efeitos_externos(monkeypatch):
    """Nada sai do teste: robô não liga, e-mail é capturado."""
    enviados = []
    monkeypatch.setattr(A, '_ligar_robo_primeira_vez_ao_fundo', lambda schema: None)
    monkeypatch.setattr(A, '_send_system_email', lambda para, assunto, html: enviados.append((para, assunto, html)) or True)
    A._sessoes_cache.clear()
    return enviados


@pytest.fixture
def emails(sem_efeitos_externos):
    return sem_efeitos_externos


def sql(query, params=None, schema=None):
    conn = A._conn(schema) if schema else A._conn()
    try:
        c = conn.cursor()
        c.execute(query, params)
        linhas = c.fetchall() if c.description else None
        conn.commit()
        return linhas
    finally:
        conn.close()


def cliente_logado(email=None, senha='senha-forte-123', empresa='Empresa Teste'):
    """Cria conta pelo formulário real e devolve (client, user_id, schema, email)."""
    email = email or f'{uuid.uuid4().hex[:8]}@empresa-teste.com.br'
    c = A.app.test_client()
    with c.session_transaction() as s:
        s['_csrf'] = 'csrf-teste'
    r = c.post('/cadastro', data={'_csrf': 'csrf-teste', 'email': email, 'senha': senha,
                                  'empresa_nome': empresa, 'segmento': 'vendemos uniformes para indústrias'})
    assert r.status_code == 302, r.get_data(as_text=True)[:300]
    u = sql('SELECT id, schema_name FROM users WHERE email = %s', (email,))[0]
    return c, u['id'], u['schema_name'], email


def esperar(cond, segundos=8):
    fim = time.time() + segundos
    while time.time() < fim:
        if cond():
            return True
        time.sleep(0.1)
    return False
