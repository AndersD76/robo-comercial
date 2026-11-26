# -*- coding: utf-8 -*-
"""Regressões do robô de busca trazidas da branch abandonada (fix/funil-conversao):
pontuação pelo ICP do próprio cliente, paginação do Serper, chave cifrada e
decisores do site gravados no lead novo. Sem banco nem rede."""
import asyncio
import os
import sys

import pytest

RAIZ = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, os.path.join(RAIZ, 'robo_pili'))
sys.path.insert(0, RAIZ)
pytest.importorskip('httpx')
os.environ.setdefault('DATABASE_URL', 'postgresql://ci:ci@127.0.0.1:1/ci')

import buscador as mod_buscador  # noqa: E402
import run_busca  # noqa: E402


def test_palavras_icp_vem_dos_termos_do_cliente():
    termos = ['contabilidade para clínicas em Curitiba PR', 'escritório de contabilidade site:.com.br',
              'contabilidade médica telefone']
    p = mod_buscador.palavras_icp(termos)
    assert p[0] == 'contabilidade'                      # aparece nos 3 termos
    assert 'clinicas' in p and 'curitiba' in p and 'medica' in p
    assert not {'pr', 'telefone', 'para', 'site', 'com'} & set(p)   # UF, formato, operador


def test_pontuacao_nao_usa_mais_as_palavras_do_agro_da_pili():
    b = mod_buscador.Buscador()
    agro = {'titulo': 'Cerealista Silo Soja', 'snippet': 'armazém de grãos', 'dominio': 'x.com.br'}
    contab = {'titulo': 'Contabilidade Médica', 'snippet': 'clínicas em Curitiba', 'dominio': 'x.com.br'}
    b.configurar_icp(mod_buscador.palavras_icp(['contabilidade para clínicas em Curitiba']), ['PR'])
    assert b._calcular_relevancia(agro) == b._calcular_relevancia({'titulo': '', 'snippet': '', 'dominio': 'x.com.br'})
    assert b._calcular_relevancia(contab) >= 5 * 3     # contabilidade + clinicas + curitiba (sem acento)


def test_pontuacao_por_estado_agora_soma():
    b = mod_buscador.Buscador()
    b.configurar_icp([], ['PR'])
    com_uf = {'titulo': 'Empresa X', 'snippet': 'Curitiba - PR, Brasil', 'dominio': 'x.com'}
    sem_uf = {'titulo': 'Empresa X', 'snippet': 'Curitiba, Brasil', 'dominio': 'x.com'}
    assert b._calcular_relevancia(com_uf) == b._calcular_relevancia(sem_uf) + 2


def test_serper_recebe_a_pagina(monkeypatch):
    enviados = []

    class Resp:
        def json(self):
            return {'organic': []}

    class Cliente:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, json=None):
            enviados.append(json)
            return Resp()

    monkeypatch.setenv('SERPER_API_KEY', 'chave-sintetica')
    monkeypatch.setattr(mod_buscador.httpx, 'AsyncClient', Cliente)
    b = mod_buscador.Buscador()
    asyncio.run(b._buscar_serper('termo', 20, pagina=1))
    asyncio.run(b._buscar_serper('termo', 20, pagina=3))
    assert 'page' not in enviados[0] and enviados[1]['page'] == 3


def test_chave_serper_do_cliente_e_decifrada(monkeypatch):
    from cryptography.fernet import Fernet
    chave = Fernet.generate_key().decode()
    monkeypatch.setenv('ENCRYPTION_KEY', chave)
    cifrada = 'ENC:' + Fernet(chave.encode()).encrypt(b'serper-do-cliente').decode()
    assert run_busca._decifrar(cifrada) == 'serper-do-cliente'
    assert run_busca._decifrar('chave-em-claro') == 'chave-em-claro'
    monkeypatch.setenv('ENCRYPTION_KEY', Fernet.generate_key().decode())   # outra chave
    assert run_busca._decifrar(cifrada) == ''      # não manda lixo cifrado ao Serper


def test_decisores_do_site_viram_contatos_sem_repetir(monkeypatch):
    feitos = []
    existentes = {'joão silva'}

    class Cur:
        def __init__(self):
            self._ultimo = None

        def execute(self, sql, params=None):
            feitos.append((' '.join(sql.split()), params))
            self._ultimo = params

        def fetchone(self):
            return (1,) if self._ultimo and str(self._ultimo[-1]).lower() in existentes else None

    class Conn:
        def cursor(self):
            return Cur()

        def commit(self):
            feitos.append(('COMMIT', None))

        def close(self):
            pass

    monkeypatch.setattr(run_busca, '_conn', lambda schema: Conn())
    novos = run_busca._salvar_decisores('emp_1', 42, [
        {'nome': 'João Silva', 'cargo': 'Diretor'},          # já existe (sócio da Receita)
        {'nome': 'Maria Souza', 'cargo': 'Gerente Comercial'},
        {'nome': '  ', 'cargo': 'x'}])
    assert [d['nome'] for d in novos] == ['Maria Souza']
    inserts = [p for s, p in feitos if s.startswith('INSERT INTO contatos')]
    assert inserts == [(42, 'Maria Souza', 'Gerente Comercial')]
    assert run_busca._salvar_decisores('emp_1', None, [{'nome': 'X Y'}]) == []   # sem lead novo


def test_bloco_morto_de_decisores_no_duplicado_saiu():
    src = open(os.path.join(RAIZ, 'robo_pili', 'run_busca.py'), encoding='utf-8').read()
    assert '_salvar_decisores(schema, empresa_id, decisores)' in src
    assert 'if decisores and empresa_id:' not in src


def test_lead_repetido_por_qualquer_numero_ou_email(monkeypatch):
    class Cur:
        def __init__(self, bate):
            self.bate, self.ultimo = bate, None

        def execute(self, sql, params=None):
            self.ultimo = (sql, params)

        def fetchone(self):
            sql, params = self.ultimo
            return {'id': 1} if any(self.bate in str(p) for p in (params or ())) else None

    class Conn:
        def __init__(self, bate):
            self.cur = Cur(bate)

        def cursor(self):
            return self.cur

        def close(self):
            pass

        def commit(self):
            pass

    monkeypatch.setattr(run_busca, '_check_lead_limit_busca', lambda s: True)
    lead = {'website': 'outro-site.com.br', 'telefone': '(41) 3333-4444', 'whatsapp': '5541999998888',
            'email': 'Contato@Empresa.com.br'}
    for ja_existe in ('33334444', '99998888', 'Contato@Empresa.com.br'):
        monkeypatch.setattr(run_busca, '_conn', lambda s, b=ja_existe: Conn(b))
        assert run_busca.salvar_empresa('emp_1', dict(lead)) is None, ja_existe
