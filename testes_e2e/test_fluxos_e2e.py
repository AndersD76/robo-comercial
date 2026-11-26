# -*- coding: utf-8 -*-
"""Fluxos críticos no navegador. Cada teste roda em Chromium, Firefox e
WebKit, em desktop e celular (fixtures em conftest.py), e falha com erro de
JavaScript ou erro no console."""
import re
import uuid

from conftest import emails_para, sql

SENHA = 'senha-forte-123'


def _cadastrar(pagina, base, email):
    pagina.goto(base + '/cadastro')
    pagina.fill('input[name=empresa_nome]', 'Uniformes Teste Ltda')
    pagina.fill('input[name=segmento]', 'vendemos uniformes para indústrias')
    pagina.fill('input[name=email]', email)
    pagina.fill('input[name=senha]', SENHA)
    pagina.click('button[type=submit]')
    pagina.wait_for_url(re.compile(r'/(configurar|dashboard)'))


def _entrar(pagina, base, email, senha=SENHA):
    pagina.goto(base + '/login')
    pagina.fill('input[name=email]', email)
    pagina.fill('input[name=senha]', senha)
    pagina.click('button[type=submit]')
    pagina.wait_for_url(re.compile(r'/(dashboard|configurar)'))


def _email():
    return f'e2e-{uuid.uuid4().hex[:8]}@empresa-teste.com.br'


def test_paginas_publicas_sem_erro(pagina, ambiente):
    base = ambiente['base']
    sitemap = pagina.request.get(base + '/sitemap-empresas-1.xml').text()
    empresa = re.search(r'<loc>https://www\.turbovenda\.com\.br(/empresas/[^/<]+/(?!estado)[^/<]+)</loc>', sitemap)
    caminhos = ['/', '/precos', '/blog', '/ferramentas/calculadora-de-leads', '/cadastro', '/login',
                '/esqueci-senha', '/privacidade'] + ([empresa.group(1)] if empresa else [])
    for caminho in caminhos:
        r = pagina.goto(base + caminho, wait_until='load')
        assert r.status == 200, caminho
        assert pagina.locator('h1').count() >= 1, caminho
    assert pagina.erros == []


def test_cadastro_sair_e_entrar(pagina, ambiente):
    base, email = ambiente['base'], _email()
    _cadastrar(pagina, base, email)
    pagina.goto(base + '/logout')
    _entrar(pagina, base, email)
    if '/dashboard' not in pagina.url:
        pagina.goto(base + '/dashboard')
    pagina.wait_for_load_state('networkidle')
    assert pagina.locator('#main').is_visible()
    assert pagina.erros == []


def test_painel_nao_executa_html_vindo_de_lead(pagina, ambiente):
    base, email = ambiente['base'], _email()
    _cadastrar(pagina, base, email)
    schema = sql(ambiente['dsn'], 'SELECT schema_name FROM users WHERE email = %s', (email,))[0]['schema_name']
    sql(ambiente['dsn'], f"""INSERT INTO {schema}.empresas (nome_fantasia, email, website, status) VALUES
        ('<img src=x onerror="window.__xss=1">Empresa Maliciosa', 'contato@maliciosa.com.br',
         'javascript:window.__xss=2', 'novo')""")
    pagina.goto(base + '/dashboard', wait_until='networkidle')
    pagina.wait_for_timeout(1500)
    assert pagina.evaluate('window.__xss') is None
    assert 'Empresa Maliciosa' in pagina.content()


def test_recuperar_senha_pela_tela(pagina, ambiente):
    base, email = ambiente['base'], _email()
    _cadastrar(pagina, base, email)
    pagina.goto(base + '/logout')
    pagina.goto(base + '/esqueci-senha')
    pagina.fill('input[name=email]', email)
    pagina.click('button[type=submit]')
    for _ in range(40):
        msgs = emails_para(ambiente['caixa'], email)
        if any('redefinir-senha' in m['html'] for m in msgs):
            break
        pagina.wait_for_timeout(250)
    link = re.search(r'https?://[^"]+(/redefinir-senha/[A-Za-z0-9_\-]+)',
                     [m for m in msgs if 'redefinir-senha' in m['html']][-1]['html']).group(1)
    pagina.goto(base + link)
    pagina.fill('input[name=senha]', 'senha-nova-456')
    pagina.fill('input[name=senha2]', 'senha-nova-456')
    pagina.click('button[type=submit]')
    pagina.wait_for_url(re.compile(r'/login'))
    _entrar(pagina, base, email, 'senha-nova-456')
    assert pagina.erros == []


def test_oferta_no_limite_abre_pagamento_sem_boleto(pagina, ambiente):
    base, email = ambiente['base'], _email()
    _cadastrar(pagina, base, email)
    schema = sql(ambiente['dsn'], 'SELECT schema_name FROM users WHERE email = %s', (email,))[0]['schema_name']
    sql(ambiente['dsn'], f"""INSERT INTO {schema}.empresas (nome_fantasia, email)
        SELECT 'Lead ' || g, 'l' || g || '@x.com.br' FROM generate_series(1, 50) g""")
    pagina.goto(base + '/dashboard', wait_until='networkidle')
    faixa = pagina.locator('#faixa-plano')
    faixa.wait_for(state='visible', timeout=10000)
    assert 'pausou no limite' in faixa.inner_text()
    faixa.locator('button').click()
    modal = pagina.locator('#overlay')
    modal.wait_for(state='visible')
    texto = modal.inner_text()
    assert 'PIX' in texto and 'Cartão' in texto and 'Boleto' not in texto
    assert pagina.erros == []


def test_cadastro_so_com_teclado(pagina, ambiente):
    if pagina.viewport_size and pagina.viewport_size['width'] < 600:
        return                                 # teclado físico: só desktop
    base = ambiente['base']
    pagina.goto(base + '/cadastro')
    pagina.focus('input[name=empresa_nome]')
    pagina.keyboard.type('Empresa Teclado')
    # cada campo obrigatório tem de ser alcançável com Tab, na ordem da tela
    for campo, valor in (('segmento', 'vendemos peças para máquinas'), ('email', _email()), ('senha', SENHA)):
        for _ in range(8):
            pagina.keyboard.press('Tab')
            if pagina.evaluate('document.activeElement.name') == campo:
                break
        assert pagina.evaluate('document.activeElement.name') == campo, f'Tab não chega em {campo}'
        pagina.keyboard.type(valor)
    pagina.keyboard.press('Enter')
    pagina.wait_for_url(re.compile(r'/(configurar|dashboard)'))
