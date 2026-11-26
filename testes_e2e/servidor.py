# -*- coding: utf-8 -*-
"""Sobe o app só em 127.0.0.1 para os testes E2E (Fase 2 do Prompt 3).

Ambiente isolado: banco descartável (DATABASE_URL vindo do conftest), base
sintética das páginas /empresas (PSEO_SQLITE), robô desligado e e-mails
gravados em E2E_CAIXA (um JSON por linha) em vez de enviados. Nada de
produção é tocado.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import app as A  # noqa: E402

A._ligar_robo_primeira_vez_ao_fundo = lambda schema: None
CAIXA = os.environ['E2E_CAIXA']


def _capturar(para, assunto, html):
    with open(CAIXA, 'a', encoding='utf-8') as f:
        f.write(json.dumps({'para': para, 'assunto': assunto, 'html': html}) + '\n')
    return True


A._send_system_email = _capturar
A.app.config['SESSION_COOKIE_SECURE'] = False     # http://127.0.0.1 no teste
A.limiter.enabled = False
for nome, valor in (('PSEO_MIN_EMPRESAS', 2), ('PSEO_MIN_INDEX', 3), ('PSEO_ESTADO_INDEX', 3),
                    ('PSEO_CIDADE_HUB_INDEX', 1)):
    setattr(A, nome, valor)
A.app.run('127.0.0.1', int(os.environ['E2E_PORTA']), threaded=True, use_reloader=False)
