# -*- coding: utf-8 -*-
"""Todo fetch POST precisa mandar Content-Type: application/json.

_check_csrf so isenta requisicoes JSON (alem de /webhook/ e /t/). Um
fetch(url, {method:'POST'}) sem corpo nao define Content-Type, entao cai
na verificacao de token, nao acha nenhum e toma 403 — em silencio, porque
o .catch() do front mostra so "erro de conexao".

Ja aconteceu com 10 chamadas de uma vez (conectar/desconectar email,
verificar dominio, enriquecer, requalificar, redes do decisor, admin).
"""
import os
import re

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(RAIZ, 'templates')

# fetch(..., { ... method: 'POST' ... }) — captura o bloco de opcoes
_FETCH_POST = re.compile(
    r"fetch\(\s*[^)]*?\{(?P<opts>[^{}]*(?:\{[^{}]*\}[^{}]*)*)\}\s*\)",
    re.DOTALL)


def _arquivos_html():
    for nome in sorted(os.listdir(TEMPLATES)):
        if nome.endswith('.html'):
            yield nome, os.path.join(TEMPLATES, nome)


def _vars_de_headers_com_json(conteudo):
    """Nomes de variaveis que guardam um objeto de headers com JSON."""
    nomes = set()
    for m in re.finditer(
            r"(?:const|let|var)\s+(\w+)\s*=\s*\{[^}]*content-type[^}]*\}",
            conteudo, re.I):
        nomes.add(m.group(1))
    return nomes


def _posts_sem_content_type(caminho):
    with open(caminho, encoding='utf-8') as f:
        conteudo = f.read()
    vars_ok = _vars_de_headers_com_json(conteudo)
    faltando = []
    for m in _FETCH_POST.finditer(conteudo):
        opts = m.group('opts')
        if not re.search(r"method\s*:\s*['\"]POST['\"]", opts, re.I):
            continue
        if 'content-type' in opts.lower():
            continue
        # headers passado por variavel, ex: {method:'POST',headers,body}
        if any(re.search(rf"\bheaders\s*:\s*{v}\b|\b(?<![:\w]){v}\b\s*,",
                         opts) for v in vars_ok):
            continue
        linha = conteudo[:m.start()].count('\n') + 1
        faltando.append(linha)
    return faltando


@pytest.mark.parametrize('nome,caminho', list(_arquivos_html()))
def test_fetch_post_declara_json(nome, caminho):
    linhas = _posts_sem_content_type(caminho)
    assert not linhas, (
        f'{nome}: fetch POST sem Content-Type nas linhas {linhas}. '
        f"Sem o header o _check_csrf exige token e devolve 403. "
        f"Adicione headers:{{'Content-Type':'application/json'}}.")


def test_webhook_e_isento_de_csrf():
    """O webhook da Unipile chega de fora, sem sessao nem token."""
    with open(os.path.join(RAIZ, 'app.py'), encoding='utf-8') as f:
        app_src = f.read()
    trecho = app_src[app_src.index('def _check_csrf'):]
    trecho = trecho[:trecho.index('app.jinja_env.globals')]
    assert "request.path.startswith('/webhook/')" in trecho
    assert "@app.route('/webhook/unipile'" in app_src
