# -*- coding: utf-8 -*-
"""Fluxos do back contra banco real: conta, isolamento entre clientes,
senha, pagamento, cota, e-mails, LGPD e saúde."""
import re
from datetime import datetime, timedelta

import app as A
from conftest import cliente_logado, esperar, sql


def test_health_e_ready_com_banco_de_verdade():
    c = A.app.test_client()
    for rota in ('/health', '/ready'):
        r = c.get(rota)
        assert r.status_code == 200 and r.get_json()['db'] == 'ok'


def test_cadastro_cria_conta_schema_e_configuracao():
    c, uid, schema, email = cliente_logado()
    assert re.fullmatch(r'emp_\d+', schema)
    cfg = sql('SELECT descricao, estados_atuacao FROM bot_config', schema=schema)[0]
    assert cfg['descricao'] == 'vendemos uniformes para indústrias'
    u = sql('SELECT plano, plano_expira, password_hash FROM users WHERE id = %s', (uid,))[0]
    assert u['plano'] == 'trial' and u['plano_expira'] > datetime.now()
    assert u['password_hash'].startswith('$2')          # bcrypt, nunca a senha
    assert c.get('/api/meu-plano').status_code == 200


def test_cadastro_sem_o_que_vende_e_recusado():
    c = A.app.test_client()
    with c.session_transaction() as s:
        s['_csrf'] = 'x'
    r = c.post('/cadastro', data={'_csrf': 'x', 'email': 'sem-segmento@teste.com.br', 'senha': 'senha-forte-123',
                                  'empresa_nome': 'X', 'segmento': ''})
    assert r.status_code == 200 and 'o que você vende' in r.get_data(as_text=True)
    assert not sql("SELECT 1 FROM users WHERE email = 'sem-segmento@teste.com.br'")


def test_login_errado_nao_entra_e_certo_entra():
    _, _, _, email = cliente_logado(senha='senha-certa-1')
    c = A.app.test_client()
    with c.session_transaction() as s:
        s['_csrf'] = 'y'
    ruim = c.post('/login', data={'_csrf': 'y', 'email': email, 'senha': 'errada'})
    assert ruim.status_code == 200 and c.get('/api/meu-plano').status_code == 401
    bom = c.post('/login', data={'_csrf': 'y', 'email': email, 'senha': 'senha-certa-1'})
    assert bom.status_code == 302 and c.get('/api/meu-plano').status_code == 200
    c.get('/logout')
    assert c.get('/api/meu-plano').status_code == 401


def test_cliente_nao_le_nem_altera_nem_apaga_lead_de_outro():
    ca, _, sa, _ = cliente_logado()
    cb, _, sb, _ = cliente_logado()
    sql("INSERT INTO empresas (nome_fantasia, email, telefone, status) VALUES "
        "('Lead do A', 'contato@lead-a.com.br', '5554999990000', 'novo')", schema=sa)
    id_a = sql("SELECT id FROM empresas WHERE nome_fantasia = 'Lead do A'", schema=sa)[0]['id']
    # B não vê o lead do A
    assert 'Lead do A' not in cb.get('/api/busca/leads').get_data(as_text=True)
    assert 'Lead do A' in ca.get('/api/busca/leads').get_data(as_text=True)
    # B tenta editar e apagar pelo mesmo id: o schema vem da sessão dele
    cb.put(f'/api/busca/lead/{id_a}', json={'nome_fantasia': 'invadido', 'status': 'perdido'})
    cb.delete(f'/api/busca/lead/{id_a}')
    lead = sql('SELECT nome_fantasia, status FROM empresas WHERE id = %s', (id_a,), schema=sa)
    assert lead and lead[0]['nome_fantasia'] == 'Lead do A' and lead[0]['status'] == 'novo'
    # campo fora da lista fechada é ignorado (mass assignment)
    ca.put(f'/api/busca/lead/{id_a}', json={'id': 999, 'score': 5, 'nome_fantasia': 'Lead do A editado'})
    assert sql('SELECT id FROM empresas WHERE id = %s', (id_a,), schema=sa)


def test_recuperacao_de_senha_ponta_a_ponta(emails):
    c_antiga, uid, _, email = cliente_logado(senha='senha-velha-1')
    c = A.app.test_client()
    with c.session_transaction() as s:
        s['_csrf'] = 'z'
    # resposta igual para e-mail com e sem conta
    r1 = c.post('/esqueci-senha', data={'_csrf': 'z', 'email': 'ninguem@nada.com.br'})
    r2 = c.post('/esqueci-senha', data={'_csrf': 'z', 'email': email})
    assert r1.get_data(as_text=True) == r2.get_data(as_text=True)
    assert esperar(lambda: any(e[0] == email for e in emails))
    link = re.search(r'/redefinir-senha/([A-Za-z0-9_\-]+)', [e for e in emails if e[0] == email][0][2]).group(1)
    assert not any(e[0] == 'ninguem@nada.com.br' for e in emails)
    # banco guarda só o hash
    assert not sql('SELECT 1 FROM senha_reset WHERE token_hash = %s', (link,))
    c.get(f'/redefinir-senha/{link}')
    r = c.post('/redefinir-senha', data={'_csrf': 'z', 'senha': 'senha-nova-2', 'senha2': 'senha-nova-2'})
    assert r.status_code == 302
    # token não serve de novo
    c2 = A.app.test_client()
    c2.get(f'/redefinir-senha/{link}')
    assert 'inválid' in c2.get('/redefinir-senha').get_data(as_text=True).lower()
    # a sessão aberta antes da troca caiu; a senha nova entra
    A._sessoes_cache.clear()
    assert c_antiga.get('/api/meu-plano').status_code == 401
    c3 = A.app.test_client()
    with c3.session_transaction() as s:
        s['_csrf'] = 'w'
    assert c3.post('/login', data={'_csrf': 'w', 'email': email, 'senha': 'senha-nova-2'}).status_code == 302


def test_pagamento_aprovado_libera_uma_vez_e_renova_sem_perder_dias():
    _, uid, _, _ = cliente_logado()
    pay = {'id': 900001, 'status': 'approved', 'transaction_amount': 97.0,
           'metadata': {'user_id': uid, 'plano': 'starter'}}
    assert A._mp_aplicar(pay) == ('approved', 'starter')
    exp1 = sql('SELECT plano, plano_expira FROM users WHERE id = %s', (uid,))[0]
    assert exp1['plano'] == 'starter'
    assert timedelta(days=29) < exp1['plano_expira'] - datetime.now() < timedelta(days=31)
    A._mp_aplicar(pay)                                   # aviso repetido
    assert sql('SELECT plano_expira FROM users WHERE id = %s', (uid,))[0]['plano_expira'] == exp1['plano_expira']
    A._mp_aplicar({**pay, 'id': 900002})                 # renovação antecipada
    exp2 = sql('SELECT plano_expira FROM users WHERE id = %s', (uid,))[0]['plano_expira']
    assert timedelta(days=29) < exp2 - exp1['plano_expira'] < timedelta(days=31)
    A._mp_aplicar({**pay, 'id': 900003, 'transaction_amount': 1.0})   # valor menor
    assert sql('SELECT plano_expira FROM users WHERE id = %s', (uid,))[0]['plano_expira'] == exp2


def test_cota_do_starter_conta_so_30_dias():
    _, uid, schema, _ = cliente_logado()
    sql("UPDATE users SET plano = 'starter', plano_expira = NOW() + INTERVAL '10 days' WHERE id = %s", (uid,))
    sql("INSERT INTO empresas (nome_fantasia, email, encontrado_em) "
        "SELECT 'velho ' || g, 'v' || g || '@x.com.br', NOW() - INTERVAL '40 days' FROM generate_series(1, 600) g",
        schema=schema)
    sql("INSERT INTO empresas (nome_fantasia, email) SELECT 'novo ' || g, 'n' || g || '@x.com.br' "
        "FROM generate_series(1, 10) g", schema=schema)
    conn = A._conn(schema)
    try:
        c = conn.cursor()
        c.execute(A._sql_leads_na_cota('starter'))
        assert c.fetchone()['total'] == 10
        c.execute(A._sql_leads_na_cota('trial'))
        assert c.fetchone()['total'] == 610
    finally:
        conn.close()


def test_funil_de_emails_manda_uma_vez_e_respeita_descadastro(emails):
    _, uid, schema, email = cliente_logado()
    sql("INSERT INTO empresas (nome_fantasia, email) SELECT 'lead ' || g, 'l' || g || '@x.com.br' "
        "FROM generate_series(1, 12) g", schema=schema)
    import emails_funil
    conn = A._conn()
    try:
        r1 = emails_funil.rodar(conn, A._send_system_email, 'https://teste', 97.0, descadastro=A._link_descadastro)
        r2 = emails_funil.rodar(conn, A._send_system_email, 'https://teste', 97.0, descadastro=A._link_descadastro)
    finally:
        conn.close()
    meus = [e for e in emails if e[0] == email]
    assert r1['leads'] >= 1 and len(meus) == 1 and r2['leads'] == 0
    link = re.search(r'(/descadastrar/[^"]+)', meus[0][2]).group(1)
    A.app.test_client().get(link)
    assert sql('SELECT emails_marketing_off FROM users WHERE id = %s', (uid,))[0]['emails_marketing_off'] is True


def test_exportar_e_excluir_os_proprios_dados():
    c, uid, schema, email = cliente_logado()
    r = c.get('/api/meus-dados/exportar')
    assert r.status_code == 200 and email in r.get_data(as_text=True)
    with c.session_transaction() as s:
        s['_csrf'] = 'k'
    r = c.post('/api/meus-dados/excluir', json={'confirmar': True}, headers={'X-CSRF-Token': 'k'})
    assert r.status_code in (200, 204), r.get_data(as_text=True)[:200]
    assert not sql('SELECT 1 FROM users WHERE id = %s', (uid,))
    assert not sql('SELECT 1 FROM information_schema.schemata WHERE schema_name = %s', (schema,))
