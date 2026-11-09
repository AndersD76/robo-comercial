# -*- coding: utf-8 -*-
"""Cota de leads: o Starter é vendido como "500 leads/mês", então conta só
os últimos 30 dias; o teste grátis conta o período todo."""
import os
import sys

import pytest

if not os.environ.get('DATABASE_URL'):
    pytest.skip('precisa de DATABASE_URL (mesmo falsa) para importar o app', allow_module_level=True)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import app  # noqa: E402


def test_starter_conta_so_os_ultimos_30_dias():
    sql = app._sql_leads_na_cota('starter')
    assert "encontrado_em >= NOW() - INTERVAL '30 days'" in sql
    # o filtro de contato fica entre parênteses para o AND valer para todos
    assert "WHERE (COALESCE(telefone" in sql and "<> '') AND encontrado_em" in sql


def test_teste_gratis_conta_o_periodo_todo():
    assert 'encontrado_em' not in app._sql_leads_na_cota('trial')
    assert app.PLAN_LEAD_LIMITS['starter'] == 500 and app.PLAN_LEAD_LIMITS['trial'] == 50
