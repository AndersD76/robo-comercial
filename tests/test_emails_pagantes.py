# -*- coding: utf-8 -*-
"""Avisos de quem pagou ou tentou pagar (emails_funil.rodar_pagantes):
um aviso por vencimento, um lembrete de PIX por pessoa, nada de boleto."""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import emails_funil as ef  # noqa: E402

AGORA = datetime(2026, 11, 20, 12, 0)
PRECOS = {'starter': 97.0, 'pro': 297.0}


class Banco:
    """Cursor falso que responde às consultas de rodar_pagantes."""
    def __init__(self, usuarios, pendentes):
        self.usuarios, self.pendentes = usuarios, pendentes
        self.lembrados, self._r = set(), None

    def cursor(self):
        return self

    def commit(self):
        pass

    def execute(self, sql, params=None):
        s = ' '.join(sql.split())
        self._r = None
        if s.startswith('SELECT NOW()'):
            self._r = [{'agora': AGORA}]
        elif "FROM users WHERE plano IN ('starter', 'pro')" in s:
            self._r = [dict(u) for u in self.usuarios]
        elif s.startswith('UPDATE users SET renovacao_'):
            coluna = s.split()[3]
            u = next(x for x in self.usuarios if x['id'] == params[1])
            if u[coluna] != params[0]:
                u[coluna] = params[0]
                self._r = [{'id': u['id']}]
            else:
                self._r = []
        elif s.startswith('SELECT p.mp_payment_id'):
            self._r = [dict(p) for p in self.pendentes]
        elif s.startswith('UPDATE pagamentos SET lembrete_em = %s'):
            uid = params[1]
            novos = [p for p in self.pendentes if p['uid'] == uid and p['mp_payment_id'] not in self.lembrados]
            self.lembrados.update(p['mp_payment_id'] for p in novos)
            self._r = [{'mp_payment_id': p['mp_payment_id']} for p in novos]
        else:
            self._r = []

    def fetchone(self):
        return self._r[0] if self._r else None

    def fetchall(self):
        return self._r or []


def _usuario(uid, expira, plano='starter'):
    return {'id': uid, 'email': f'c{uid}@empresa.com.br', 'empresa_nome': f'Cliente {uid}',
            'schema_name': f'emp_{uid}', 'plano': plano, 'plano_expira': expira,
            'renovacao_aviso_para': None, 'renovacao_vencido_para': None}


def test_um_aviso_por_vencimento_e_um_pix_por_pessoa(monkeypatch):
    monkeypatch.setattr(ef, 'migrar', lambda cur: None)
    monkeypatch.setattr(ef, 'resumo_leads', lambda cur, s: {'validos': 12, 'cnpj': 9, 'decisor': 4})
    banco = Banco(
        [_usuario(1, AGORA + timedelta(days=2)), _usuario(2, AGORA - timedelta(days=1), 'pro')],
        [{'mp_payment_id': '10', 'plano': 'starter', 'valor': 97, 'uid': 3,
          'email': 'c3@empresa.com.br', 'empresa_nome': 'Cliente 3'},
         {'mp_payment_id': '11', 'plano': 'starter', 'valor': 97, 'uid': 3,
          'email': 'c3@empresa.com.br', 'empresa_nome': 'Cliente 3'}])
    enviados = []
    envio = lambda para, assunto, html: enviados.append((para, assunto, html)) or True  # noqa: E731
    assert ef.rodar_pagantes(banco, envio, 'https://www.turbovenda.com.br', PRECOS) == \
        {'renova': 1, 'vencido': 1, 'pix': 1, 'falhas': 0}
    # segunda passada no mesmo ciclo: nada de novo
    assert ef.rodar_pagantes(banco, envio, 'https://www.turbovenda.com.br', PRECOS) == \
        {'renova': 0, 'vencido': 0, 'pix': 0, 'falhas': 0}
    assuntos = {para: assunto for para, assunto, _ in enviados}
    assert assuntos['c1@empresa.com.br'].startswith('Seu plano Starter vence em')
    assert assuntos['c2@empresa.com.br'] == 'Seu plano Pro venceu e o robô pausou'
    assert assuntos['c3@empresa.com.br'] == 'Seu PIX do TurboVenda não foi pago'
    for _, _, html in enviados:
        assert 'boleto' not in html.lower()
        assert '/assinar?plano=' in html


def test_falha_no_envio_desfaz_a_marca(monkeypatch):
    monkeypatch.setattr(ef, 'migrar', lambda cur: None)
    banco = Banco([_usuario(1, AGORA + timedelta(days=1))], [])
    assert ef.rodar_pagantes(banco, lambda *a: False, 'https://x', PRECOS)['falhas'] == 1
    assert banco.usuarios[0]['renovacao_aviso_para'] is None


def test_textos_de_renovacao_sao_honestos():
    assunto, html = ef.email_renova('ACME', 'starter', 97.0, AGORA + timedelta(days=3), 'https://x')
    assert 'nada é cobrado sem você pagar' in html and 'assinatura do TurboVenda' in html
