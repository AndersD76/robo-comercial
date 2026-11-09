# -*- coding: utf-8 -*-
"""Regras puras da conta (cadastro, login, e-mails). Sem banco."""
import ast
import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import contas  # noqa: E402


def _fonte_app():
    with open(os.path.join(RAIZ, 'app.py'), encoding='utf-8') as f:
        return f.read()


# ------------------------------------------------ template de e-mail ------

@pytest.mark.parametrize('email,esperado', [
    ('comercial1@pili.ind.br', True),
    ('  Vendas@PILI.IND.BR ', True),
    ('fulano@gmail.com', False),
    ('pili.ind.br@gmail.com', False),
    ('x@pili.ind.br.fake.com', False),
    ('', False),
    (None, False),
])
def test_template_da_pili_so_para_a_pili(email, esperado):
    assert contas.usa_template_pili(email) is esperado


# ------------------------------------------------------------------ site ---

@pytest.mark.parametrize('entrada,esperado', [
    ('empresa.com.br', 'https://empresa.com.br'),
    ('www.empresa.com.br', 'https://www.empresa.com.br'),
    ('  Empresa.COM.br/  ', 'https://empresa.com.br'),
    ('http://empresa.com.br', 'http://empresa.com.br'),
    ('https://empresa.com.br/loja', 'https://empresa.com.br/loja'),
    ('HTTPS://www.Empresa.com.br/', 'https://www.empresa.com.br'),
    ('empresa.com.br:8080', 'https://empresa.com.br:8080'),
    ('telateste.com.br', 'https://telateste.com.br'),   # caso do teste de tela
])
def test_site_aceita_sem_https(entrada, esperado):
    assert contas.normalizar_site(entrada) == esperado


@pytest.mark.parametrize('entrada', [
    '', '   ', None, 'empresa', 'minha empresa.com.br', 'fulano@empresa.com.br',
    'javascript:alert(1)', 'ftp://empresa.com.br', 'http://', 'empresa.c',
    '..com.br', 'https://-x.com.br',
])
def test_site_invalido_vira_vazio(entrada):
    assert contas.normalizar_site(entrada) == ''


# ----------------------------------------------------------------- login ---

@pytest.mark.parametrize('destino', [
    '/dashboard', '/dashboard?upgrade=starter', '/configurar',
    '/trial-expirado', '/precos#planos',
])
def test_next_relativo_do_site_passa(destino):
    assert contas.next_seguro(destino) == destino


@pytest.mark.parametrize('destino', [
    None, '', 'dashboard', 'https://evil.com/dashboard', '//evil.com',
    '/\\evil.com', '\\\\evil.com', 'javascript:alert(1)', '/login',
    '/login?next=/dashboard', '/logout', '/cadastro', '/dash\nboard',
    '/' + 'a' * 600, ' //evil.com',
])
def test_next_perigoso_ou_em_laco_e_recusado(destino):
    assert contas.next_seguro(destino) is None


def test_send_emails_nao_usa_template_da_pili_para_cliente():
    """email_pili.html só pode aparecer dentro de _template_email_cliente,
    e essa função precisa checar usa_template_pili antes."""
    fonte = _fonte_app()
    arvore = ast.parse(fonte)
    funcs = {n.name: n for n in ast.walk(arvore)
             if isinstance(n, ast.FunctionDef)}
    alvo = funcs['_template_email_cliente']
    linhas = fonte.splitlines()
    for i, linha in enumerate(linhas, start=1):
        if 'email_pili.html' in linha and not linha.lstrip().startswith('#'):
            assert alvo.lineno <= i <= alvo.end_lineno, (
                f'app.py:{i} usa email_pili.html fora do template do cliente')
    corpo = '\n'.join(linhas[alvo.lineno - 1:alvo.end_lineno])
    assert 'usa_template_pili' in corpo
    envio = funcs['api_send_emails']
    corpo_envio = '\n'.join(linhas[envio.lineno - 1:envio.end_lineno])
    assert '_template_email_cliente' in corpo_envio


# ------------------------------------------------------ senha esquecida ---

def test_hash_do_token_nao_e_o_token():
    token = 'abc123-token-aleatorio'
    h = contas.hash_token(token)
    assert h != token and len(h) == 64
    assert h == contas.hash_token(token)            # determinístico
    assert h != contas.hash_token(token + 'x')


def test_email_de_senha_tem_link_e_validade():
    html = contas.html_redefinir_senha(
        'https://www.turbovenda.com.br/redefinir-senha/TOKEN')
    assert 'https://www.turbovenda.com.br/redefinir-senha/TOKEN' in html
    assert '1 hora' in html
    assert 'wa.me/5554999648368' in html            # suporte sem MX


def test_rotas_de_senha_guardam_so_o_hash():
    fonte = _fonte_app()
    assert "@app.route('/esqueci-senha'" in fonte
    assert "@app.route('/redefinir-senha/<token>')" in fonte
    assert "@app.route('/redefinir-senha', methods=['GET', 'POST'])" in fonte
    inicio = fonte.index('def _enviar_link_senha')
    trecho = fonte[inicio:fonte.index('def _token_senha_valido')]
    assert 'hash_token(token)' in trecho
    assert "INTERVAL '1 hour'" in trecho


@pytest.mark.parametrize('nome', ['esqueci_senha.html', 'redefinir_senha.html',
                                  'login.html'])
def test_forms_de_senha_tem_csrf(nome):
    with open(os.path.join(RAIZ, 'templates', nome), encoding='utf-8') as f:
        html = f.read()
    assert 'name="_csrf"' in html and 'csrf_token()' in html


def test_login_tem_link_esqueci_senha():
    with open(os.path.join(RAIZ, 'templates', 'login.html'),
              encoding='utf-8') as f:
        assert 'href="/esqueci-senha"' in f.read()


# --------------------------------------------------------- boas-vindas ---

def test_boas_vindas_tem_login_proximo_passo_e_whatsapp():
    html = contas.html_boas_vindas('Acme <Ltda>',
                                   'https://www.turbovenda.com.br/login')
    assert 'https://www.turbovenda.com.br/login' in html
    assert 'Acme &lt;Ltda&gt;' in html               # nome escapado
    assert 'Configurar tudo' in html
    assert 'wa.me/5554999648368' in html
    assert '(54) 99964-8368' in html
    com_termos = contas.html_boas_vindas('Acme', 'https://x/login',
                                         tem_termos=True)
    assert 'já sabe o que procurar' in com_termos
