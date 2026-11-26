# -*- coding: utf-8 -*-
"""Reparo das tabelas sombra (tabela do public criada dentro de schema de
cliente pelo vazamento de search_path do pooler)."""
import app as A
import reparo_schemas
from conftest import sql


def _executar(*comandos):
    conn = A._conn()
    try:
        c = conn.cursor()
        for cmd in comandos:
            c.execute(cmd)
        conn.commit()
    finally:
        conn.close()


def test_sombras_vao_para_o_public_e_somem_sem_tocar_no_cliente():
    A._init_public_schema()
    _executar(
        'DROP SCHEMA IF EXISTS emp_9001 CASCADE',
        'CREATE SCHEMA emp_9001',
        # tabela legítima do cliente: não pode ser tocada
        'CREATE TABLE emp_9001.empresas (id BIGSERIAL PRIMARY KEY, nome TEXT)',
        "INSERT INTO emp_9001.empresas (nome) VALUES ('Lead do cliente')",
        # sombras: mesma estrutura das públicas (como o CREATE TABLE IF NOT EXISTS cria)
        'CREATE TABLE emp_9001.pageviews (LIKE public.pageviews)',
        "INSERT INTO emp_9001.pageviews (id, path) VALUES (1, '/sombra-1'), (2, '/sombra-2')",
        'CREATE TABLE emp_9001.users (LIKE public.users)',
        'CREATE TABLE IF NOT EXISTS public.indexnow_enviados (url TEXT PRIMARY KEY, lastmod TEXT, enviado_em TIMESTAMPTZ DEFAULT now())',
        "INSERT INTO public.indexnow_enviados (url, lastmod) VALUES ('https://x/a', '1') ON CONFLICT DO NOTHING",
        'CREATE TABLE emp_9001.indexnow_enviados (LIKE public.indexnow_enviados)',
        "INSERT INTO emp_9001.indexnow_enviados (url, lastmod) VALUES ('https://x/a', '1'), ('https://x/b', '2')",
    )
    antes = sql('SELECT COUNT(*) AS n FROM public.pageviews')[0]['n']
    conn = A._conn()
    try:
        feito = reparo_schemas.reparar(conn, log=lambda *_: None)
    finally:
        conn.close()
    reparadas = {(s, t): n for s, t, n in feito}
    assert reparadas[('emp_9001', 'pageviews')] == 2          # ids regenerados: nada colide com o public
    assert reparadas[('emp_9001', 'users')] == 0
    assert reparadas[('emp_9001', 'indexnow_enviados')] == 1  # a repetida não duplica
    assert sql('SELECT COUNT(*) AS n FROM public.pageviews')[0]['n'] == antes + 2
    assert sql("SELECT COUNT(*) AS n FROM public.indexnow_enviados WHERE url IN ('https://x/a', 'https://x/b')")[0]['n'] == 2
    restantes = sql("SELECT table_name FROM information_schema.tables WHERE table_schema = 'emp_9001'")
    assert [r['table_name'] for r in restantes] == ['empresas']
    assert sql('SELECT nome FROM emp_9001.empresas')[0]['nome'] == 'Lead do cliente'
    conn = A._conn()
    try:
        assert [x for x in reparo_schemas.reparar(conn, log=lambda *_: None) if x[0] == 'emp_9001'] == []
    finally:
        conn.close()
    _executar('DROP SCHEMA emp_9001 CASCADE')


def test_lista_de_publicas_nao_inclui_tabela_de_cliente():
    for nome in ('empresas', 'contatos', 'bot_config', 'interacoes', 'buscas', 'leads_linkedin'):
        assert nome not in reparo_schemas.PUBLICAS
    for nome in ('users', 'pagamentos', 'conteudo_paginas', 'cnae_ibge', 'mapa_buscas', 'eventos'):
        assert nome in reparo_schemas.PUBLICAS


def test_url_do_pooler_vira_conexao_direta(monkeypatch):
    import re
    url = 'postgresql://u:s@ep-abc-123-pooler.sa-east-1.aws.neon.tech/db?sslmode=require'
    direto = re.sub(r'(@[^/@:]+?)-pooler\.', r'\1.', url, count=1)
    assert direto == 'postgresql://u:s@ep-abc-123.sa-east-1.aws.neon.tech/db?sslmode=require'
