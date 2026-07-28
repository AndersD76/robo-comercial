# -*- coding: utf-8 -*-
"""Testes basicos do TurboVenda — infraestrutura inicial."""
import os
import sys
import pytest

# Garante que o diretorio raiz do projeto esta no path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def test_import_app():
    """Verifica que o modulo app pode ser importado sem erro fatal."""
    # Nota: o import pode falhar se DATABASE_URL nao estiver configurado,
    # mas a estrutura do modulo deve ser valida.
    # Em CI, definir DATABASE_URL como variavel de ambiente.
    if not os.environ.get('DATABASE_URL'):
        pytest.skip("DATABASE_URL nao configurado — pulando import test")
    import app
    assert hasattr(app, 'app'), "Flask app nao encontrado no modulo"


def test_get_schema_rejects_unauthenticated():
    """Verifica que _get_schema() retorna 403 sem usuario autenticado."""
    if not os.environ.get('DATABASE_URL'):
        pytest.skip("DATABASE_URL nao configurado — pulando test")
    import app as mod
    with mod.app.test_request_context():
        with pytest.raises(Exception):
            # Sem sessao, deve abortar com 403
            mod._get_schema()


def test_conn_helper_returns_connection():
    """Verifica que _conn() retorna uma conexao valida."""
    if not os.environ.get('DATABASE_URL'):
        pytest.skip("DATABASE_URL nao configurado — pulando test")
    import app as mod
    conn = mod._conn()
    try:
        assert conn is not None
        assert not conn.closed
    finally:
        conn.close()
