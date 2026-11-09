# -*- coding: utf-8 -*-
"""Pagamento (Mercado Pago): a compra só vale depois de conferida no próprio
MP, libera o plano uma vez só e não depende do navegador."""
import os
import sys

import pytest

if not os.environ.get('DATABASE_URL'):
    pytest.skip('precisa de DATABASE_URL (mesmo falsa) para importar o app', allow_module_level=True)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import app  # noqa: E402


class Banco:
    """Conexão falsa: lembra quais pagamentos já liberaram plano."""
    def __init__(self):
        self.aplicados, self.log = set(), []

    def __call__(self, *a, **k):
        return self

    def cursor(self):
        return self

    def execute(self, sql, params=None):
        self.log.append((' '.join(sql.split()), params))
        self._ret = None
        if 'SET aplicado_em' in sql:
            pid = params[0]
            if pid not in self.aplicados:
                self.aplicados.add(pid)
                self._ret = {'id': 1}

    def fetchone(self):
        return self._ret

    def commit(self):
        pass

    def close(self):
        pass

    def planos_liberados(self):
        return [p for s, p in self.log if s.startswith('UPDATE users SET plano')]


def _pix(status='approved', valor=97.0, uid=7, plano='starter', pid=111):
    return {'id': pid, 'status': status, 'transaction_amount': valor,
            'metadata': {'user_id': uid, 'plano': plano}}


def test_dono_pelo_metadata_pela_referencia_e_pelo_valor():
    assert app._mp_dono(_pix()) == (7, 'starter')
    assert app._mp_dono({'external_reference': 'user_9_pro', 'transaction_amount': 297}) == (9, 'pro')
    assert app._mp_dono({'metadata': {'user_id': '5'}, 'transaction_amount': 297.0}) == (5, 'pro')
    assert app._mp_dono({'transaction_amount': 97}) == (None, None)


def test_aprovado_libera_o_plano_uma_vez_so(monkeypatch):
    banco = Banco()
    monkeypatch.setattr(app, '_conn', banco)
    assert app._mp_aplicar(_pix()) == ('approved', 'starter')
    app._mp_aplicar(_pix())                       # webhook repetido / tela do Pix de novo
    assert banco.planos_liberados() == [('starter', 7)]
    # renovação: conta do fim do plano pago em vigor, do teste ou vencido conta de agora
    sql = [s for s, _ in banco.log if s.startswith('UPDATE users SET plano')][0]
    assert "WHEN plano = 'trial'" in sql and 'ELSE plano_expira END' in sql


def test_pendente_valor_menor_ou_dono_errado_nao_libera(monkeypatch):
    banco = Banco()
    monkeypatch.setattr(app, '_conn', banco)
    app._mp_aplicar(_pix(status='pending', pid=1))
    app._mp_aplicar(_pix(valor=1.0, pid=2))
    assert app._mp_aplicar(_pix(pid=3), uid_esperado=8) == ('approved', None)
    assert banco.planos_liberados() == []


def test_boleto_saiu_e_status_exige_login():
    c = app.app.test_client()
    assert c.post('/api/pagamento/boleto', json={'plano': 'starter'}).status_code in (404, 405)
    r = c.get('/api/pagamento/status/123')
    assert r.status_code in (302, 401)
