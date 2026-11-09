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


# QA-SEC-003: XSS armazenado no painel (dados raspados de sites entravam no HTML sem escape)
def test_nenhuma_interpolacao_de_dado_externo_sem_escape():
    import glob
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'qa', 'ferramentas'))
    import xss_interpolacoes
    raiz = os.path.join(os.path.dirname(__file__), '..', 'templates')
    achados = {os.path.basename(f): xss_interpolacoes.inseguras(f)
               for f in glob.glob(os.path.join(raiz, '*.html')) if 'Notebook' not in f}
    assert {f: r for f, r in achados.items() if r} == {}


def test_painel_define_funcoes_de_escape():
    raiz = os.path.join(os.path.dirname(__file__), '..', 'templates')
    for nome in ('dashboard.html', 'index.html', 'admin.html', 'config.html', 'agendar.html'):
        html = open(os.path.join(raiz, nome), encoding='utf-8').read()
        assert 'function esc(v)' in html and 'function urlSegura(u)' in html, nome


# QA-SEC-006: troca de senha não derrubava as outras sessões (cookie assinado no navegador)
def test_troca_de_senha_derruba_sessoes_antigas(monkeypatch):
    class Banco:
        def cursor(self):
            return self

        def execute(self, sql, params=None):
            pass

        def fetchone(self):
            return {'sessao_versao': 1, 'ativo': True}

        def close(self):
            pass
    monkeypatch.setattr(app, '_conn', lambda *a, **k: Banco())
    app._sessoes_cache.clear()
    c = app.app.test_client()
    with c.session_transaction() as s:
        s['user_id'], s['sv'] = 99, 0          # sessão de antes da troca
    assert c.get('/api/meu-plano').status_code == 401
    with c.session_transaction() as s:
        assert 'user_id' not in s
    with c.session_transaction() as s:
        s['user_id'], s['sv'] = 99, 1          # sessão nova passa do login_required
    assert c.get('/api/meu-plano').status_code != 401
    app._sessoes_cache.clear()


# QA-FUN-001: e-mail de prospecção dos clientes saía com o modelo da Pili Equipamentos
def test_email_do_cliente_nao_usa_modelo_da_pili(monkeypatch):
    monkeypatch.setattr(app, 'get_bot_config', lambda schema: {
        'empresa_nome': 'Uniformes Sul', 'descricao': 'Vendemos uniformes para indústrias.',
        'website': 'uniformessul.com.br'})
    html, assunto = app._template_email_cliente('emp_5', {'email': 'dono@uniformessul.com.br'})
    assert 'Pili' not in html and 'Tombadores' not in html
    assert 'Uniformes Sul' in html and 'Uniformes Sul' in assunto
    html_pili, _ = app._template_email_cliente('emp_1', {'email': 'vendas@pili.ind.br', 'empresa_nome': 'Pili'})
    assert 'Pili' in html_pili


# QA-SEC-007: sessão, QR e status do WhatsApp eram um arquivo só para todos os clientes
def test_whatsapp_e_linkedin_separados_por_cliente():
    from robo_pili import regras
    a, b = regras.caminhos_wa('/robo', 'emp_1'), regras.caminhos_wa('/robo', 'emp_2')
    assert a['qr'] != b['qr'] and a['sessao'] != b['sessao'] and a['status'] != b['status']
    assert 'emp_1' in a['qr'] and 'emp_2' in b['qr']
    for ruim in ('../emp_2', 'emp_1/../../x', ''):
        with pytest.raises(ValueError):
            regras.caminhos_wa('/robo', ruim)
    src = open(os.path.join(os.path.dirname(__file__), '..', 'app.py'), encoding='utf-8').read()
    assert "'robo_pili', 'wa_qr.png'" not in src and "'robo_pili', 'wa_status.json'" not in src


# QA-FUN-003: sem termos próprios, o robô do cliente buscava com os termos da Pili
def test_robo_sem_termos_nao_usa_termos_da_pili():
    raiz = os.path.join(os.path.dirname(__file__), '..', 'robo_pili')
    busca = open(os.path.join(raiz, 'run_busca.py'), encoding='utf-8').read()
    corpo = busca[busca.index('def get_termos'):busca.index('def log_db')]
    assert 'TERMOS_BUSCA' not in corpo.split('# Sem termos do cliente')[0] and corpo.rstrip().endswith('return []')
    buscador = open(os.path.join(raiz, 'buscador.py'), encoding='utf-8').read()
    assert 'random.choice(TERMOS_BUSCA)' not in buscador and 'random.sample(TERMOS_BUSCA' not in buscador


# QA-LGPD-001: logs gravavam e-mail de lead e de cliente
def test_logs_sem_email_cpf_ou_segredo():
    f = app._SemDadoPessoal()
    import logging
    r = logging.LogRecord('t', logging.INFO, __file__, 1,
                          'Unipile OK -> %s | cpf 123.456.789-09 | Authorization: Bearer abc.def | token=xyz123',
                          ('fulano.silva@empresa.com.br',), None)
    f.filter(r)
    m = r.getMessage()
    assert 'fulano.silva' not in m and 'f***@empresa.com.br' in m
    assert '123.456.789-09' not in m and 'abc.def' not in m and 'xyz123' not in m
    assert any(isinstance(fl, app._SemDadoPessoal) for h in logging.getLogger().handlers for fl in h.filters)


# QA-SEC-008: /health devolvia a mensagem do driver (host e usuário do banco)
def test_health_nao_vaza_detalhe_do_banco(monkeypatch):
    def quebra(*a, **k):
        raise RuntimeError('connection to server at "ep-segredo.neon.tech" failed for user "neondb_owner"')
    monkeypatch.setattr(app, '_conn', quebra)
    for rota in ('/health', '/ready'):
        r = app.app.test_client().get(rota)
        assert r.status_code == 503 and 'neon' not in r.get_data(as_text=True)
