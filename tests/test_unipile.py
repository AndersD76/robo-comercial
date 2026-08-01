# -*- coding: utf-8 -*-
"""O DSN da Unipile chega em varias formas — todas tem que funcionar.

O painel mostra o host sem esquema ("api16.unipile.com:14622") e a
documentacao mostra URLs completas, entao o valor colado na variavel de
ambiente costuma vir com caminho junto. Sem normalizar, a URL final
virava /api/v1/accounts/api/v1/hosted/accounts/link e a Unipile
respondia "Cannot POST".
"""
import ast
import os
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


def test_url_final_nao_duplica_prefixo():
    dsn = normalizar('https://api16.unipile.com:14622/api/v1/accounts')
    url = f'{dsn}/api/v1/hosted/accounts/link'
    assert url == f'{ESPERADO}/api/v1/hosted/accounts/link'
    assert url.count('/api/v1') == 1
