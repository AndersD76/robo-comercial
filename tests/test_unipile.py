# -*- coding: utf-8 -*-
"""O DSN da Unipile chega em varias formas — todas tem que funcionar.

O painel mostra o host sem esquema ("api16.unipile.com:14622") e a
documentacao mostra URLs completas, entao o valor colado na variavel de
ambiente costuma vir com caminho junto. Sem normalizar, a URL final
virava /api/v1/accounts/api/v1/hosted/accounts/link e a Unipile
respondia "Cannot POST".
"""
import ast
import datetime as _dt
import os
import re
from urllib.parse import urlparse

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ESPERADO = 'https://api16.unipile.com:14622'


def _carregar_normalizar_dsn():
    """Extrai a funcao do app.py sem importar o modulo (que abre banco)."""
    caminho = os.path.join(RAIZ, 'app.py')
    with open(caminho, encoding='utf-8') as f:
        fonte = f.read()
    arvore = ast.parse(fonte)
    linhas = fonte.splitlines()
    for no in ast.walk(arvore):
        if isinstance(no, ast.FunctionDef) and no.name == '_normalizar_dsn':
            ns = {'_urlparse': urlparse}
            exec('\n'.join(linhas[no.lineno - 1:no.end_lineno]), ns)
            return ns['_normalizar_dsn']
    raise AssertionError('_normalizar_dsn nao encontrada em app.py')


normalizar = _carregar_normalizar_dsn()


@pytest.mark.parametrize('entrada', [
    'https://api16.unipile.com:14622/api/v1/accounts',  # o caso que quebrou
    'https://api16.unipile.com:14622/api/v1',
    'https://api16.unipile.com:14622/',
    'https://api16.unipile.com:14622',
    'api16.unipile.com:14622',                          # como o painel mostra
    '  api16.unipile.com:14622/api/v1/emails  ',
])
def test_dsn_vira_apenas_host(entrada):
    assert normalizar(entrada) == ESPERADO


@pytest.mark.parametrize('entrada', ['', '   ', None])
def test_dsn_vazio_desliga_integracao(entrada):
    """Sem DSN a Unipile fica desligada — nao pode montar URL quebrada."""
    assert normalizar(entrada) == ''


def _fonte_app():
    with open(os.path.join(RAIZ, 'app.py'), encoding='utf-8') as f:
        return f.read()


# valores aceitos pelo enum da API (o 400 devolveu o schema inteiro).
# A doc em prosa cita "MICROSOFT" e "IMAP", que a API recusa.
PROVIDERS_VALIDOS = {'LINKEDIN', 'WHATSAPP', 'INSTAGRAM', 'MESSENGER',
                     'TELEGRAM', 'GOOGLE', 'OUTLOOK', 'TWITTER', 'MAIL'}
CORINGAS_VALIDOS = {'*', '*:MAILING', '*:MESSAGING', '*:CALENDAR'}


def test_providers_usa_valor_aceito_pela_api():
    fonte = _fonte_app()
    # ha mais de um "payload = {" no app; o do link tem 'type': 'create'
    inicio = fonte.index("'type': 'create'")
    trecho = fonte[inicio:inicio + 600]
    m = re.search(r"'providers':\s*(.+)", trecho)
    assert m, 'campo providers sumiu do payload'
    valor = m.group(1).strip().rstrip(',')
    if valor.startswith('['):
        itens = set(re.findall(r"'([^']+)'", valor))
        invalidos = itens - PROVIDERS_VALIDOS
        assert not invalidos, (
            f'providers invalidos {invalidos}; aceitos: {PROVIDERS_VALIDOS}')
    else:
        assert valor.strip("'\"") in CORINGAS_VALIDOS, (
            f'coringa {valor} nao aceito; use um de {CORINGAS_VALIDOS}')


def test_expiresOn_bate_com_o_padrao_da_api():
    """A API valida com regex: 3 casas decimais e sufixo Z."""
    padrao = re.compile(
        r'^[1-2]\d{3}-[0-1]\d-[0-3]\dT\d{2}:\d{2}:\d{2}\.\d{3}Z$')
    agora = _dt.datetime.now(_dt.timezone.utc)
    gerado = (agora + _dt.timedelta(hours=1)).strftime(
        '%Y-%m-%dT%H:%M:%S.') + f'{agora.microsecond // 1000:03d}Z'
    assert padrao.match(gerado), f'{gerado} nao bate com o padrao da API'
    # o isoformat cru (microssegundos) tem que falhar — foi o bug original
    assert not padrao.match(
        (agora + _dt.timedelta(hours=1)).isoformat().replace('+00:00', 'Z'))


def test_url_final_nao_duplica_prefixo():
    dsn = normalizar('https://api16.unipile.com:14622/api/v1/accounts')
    url = f'{dsn}/api/v1/hosted/accounts/link'
    assert url == f'{ESPERADO}/api/v1/hosted/accounts/link'
    assert url.count('/api/v1') == 1
