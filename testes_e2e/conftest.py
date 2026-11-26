# -*- coding: utf-8 -*-
"""E2E com Playwright (Fase 2 do Prompt 3): o app real no navegador, em
Chromium, Firefox e WebKit, desktop e celular, contra um ambiente local
isolado (banco descartável + base sintética). O teste falha com erro de
JavaScript ou erro no console.

Uso: python -m pytest testes_e2e -q   (E2E_NAVEGADORES=chromium para só um)
"""
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from urllib.parse import urlsplit, urlunsplit

import psycopg2
import pytest

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
NAVEGADORES = os.environ.get('E2E_NAVEGADORES', 'chromium,firefox,webkit').split(',')
# Avisos do navegador que não são erro do app: CSP em modo relatório e
# recursos de terceiros (GA, CDN) bloqueados ou fora do ar
_IGNORAR = re.compile(r'Report Only|report-only|Content Security Policy|googletagmanager|google-analytics|'
                      r'cdnjs\.cloudflare|mercadopago|Failed to load resource.*(googletagmanager|cdnjs|mercadopago)',
                      re.I)


def _uri_servidor():
    if os.environ.get('PG_TESTE_URI'):
        return os.environ['PG_TESTE_URI']
    import shutil
    import pgserver
    # Fora da pasta temporária: a limpeza do Windows apagava arquivos e o initdb
    # recusava a pasta. Pasta sem PG_VERSION = corrompida: recria do zero.
    pasta = os.environ.get('PG_TESTE_DIR') or os.path.join(
        os.environ.get('LOCALAPPDATA') or tempfile.gettempdir(), 'TurboVenda', 'pg_teste')
    if os.path.isdir(pasta) and not os.path.exists(os.path.join(pasta, 'PG_VERSION')):
        shutil.rmtree(pasta, ignore_errors=True)
    os.makedirs(os.path.dirname(pasta), exist_ok=True)
    return pgserver.get_server(pasta, cleanup_mode=None).get_uri()


def _porta_livre():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    porta = s.getsockname()[1]
    s.close()
    return porta


@pytest.fixture(scope='session')
def ambiente(tmp_path_factory):
    servidor = _uri_servidor()
    banco = 'tv_e2e_' + uuid.uuid4().hex[:10]
    adm = psycopg2.connect(servidor)
    adm.autocommit = True
    adm.cursor().execute(f'CREATE DATABASE {banco}')
    adm.close()
    p = urlsplit(servidor)
    dsn = urlunsplit((p.scheme, p.netloc, '/' + banco, p.query, p.fragment))
    pasta = tmp_path_factory.mktemp('e2e')
    pseo = str(pasta / 'pseo.sqlite')
    env_sem_banco = {k: v for k, v in os.environ.items() if k != 'DATABASE_URL'}
    subprocess.run([sys.executable, os.path.join(RAIZ, 'scripts', 'cnpj_ingest.py'), '--sample', '--sqlite', pseo],
                   env=env_sem_banco, check=True, capture_output=True)
    porta = _porta_livre()
    caixa = str(pasta / 'caixa.jsonl')
    open(caixa, 'w').close()
    env = {**env_sem_banco, 'DATABASE_URL': dsn, 'PSEO_SQLITE': pseo, 'E2E_PORTA': str(porta),
           'E2E_CAIXA': caixa, 'SECRET_KEY': 'segredo-e2e', 'PYTHONIOENCODING': 'utf-8'}
    env.pop('RAILWAY_ENVIRONMENT_ID', None)
    log = open(pasta / 'servidor.log', 'w', encoding='utf-8')
    proc = subprocess.Popen([sys.executable, os.path.join(RAIZ, 'testes_e2e', 'servidor.py')],
                            env=env, stdout=log, stderr=subprocess.STDOUT, cwd=RAIZ)
    base = f'http://127.0.0.1:{porta}'
    for _ in range(120):
        try:
            if urllib.request.urlopen(base + '/health', timeout=2).status == 200:
                break
        except Exception:
            time.sleep(0.5)
    else:
        proc.kill()
        raise RuntimeError('servidor E2E não subiu: ' + open(pasta / 'servidor.log', encoding='utf-8').read()[-2000:])
    yield {'base': base, 'dsn': dsn, 'caixa': caixa}
    proc.kill()
    proc.wait(timeout=10)
    log.close()
    adm = psycopg2.connect(servidor)
    adm.autocommit = True
    try:
        adm.cursor().execute(f'DROP DATABASE IF EXISTS {banco} WITH (FORCE)')
    finally:
        adm.close()


@pytest.fixture(scope='session')
def playwright_sessao():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        yield pw


@pytest.fixture(scope='session', params=NAVEGADORES)
def navegador(request, playwright_sessao):
    b = getattr(playwright_sessao, request.param).launch()
    yield b
    b.close()


@pytest.fixture(params=['desktop', 'celular'])
def pagina(request, navegador, playwright_sessao):
    if request.param == 'celular':
        disp = dict(playwright_sessao.devices['iPhone 13'])
        if navegador.browser_type.name == 'firefox':
            disp.pop('is_mobile', None)        # Firefox não emula is_mobile
        ctx = navegador.new_context(**disp)
    else:
        ctx = navegador.new_context(viewport={'width': 1366, 'height': 900})
    p = ctx.new_page()
    p.erros = []
    p.on('pageerror', lambda e: p.erros.append(f'pageerror: {e}'))
    p.on('console', lambda m: m.type == 'error' and not _IGNORAR.search(m.text) and p.erros.append(f'console: {m.text}'))
    yield p
    ctx.close()


def sql(dsn, query, params=None):
    import psycopg2.extras
    conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        c = conn.cursor()
        c.execute(query, params)
        linhas = c.fetchall() if c.description else None
        conn.commit()
        return linhas
    finally:
        conn.close()


def emails_para(caixa, email):
    return [json.loads(l) for l in open(caixa, encoding='utf-8') if l.strip() and json.loads(l)['para'] == email]
