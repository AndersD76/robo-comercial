# -*- coding: utf-8 -*-
"""Procura segredos em TODO o histórico do git (todas as branches). Nunca
imprime o valor: só tipo, arquivo, commit (curto) e a data do commit.
Uso: python qa/ferramentas/segredos_historico.py"""
import re
import subprocess
import sys
from collections import OrderedDict

PADROES = OrderedDict([
    ('Mercado Pago (produção)', r'APP_USR-\d{6,}-\d{6}-[0-9a-f]{32}-\d{6,}'),
    ('Mercado Pago (teste)', r'TEST-\d{6,}-\d{6}-[0-9a-f]{32}-\d{6,}'),
    ('Anthropic', r'sk-ant-[A-Za-z0-9_\-]{20,}'),
    ('OpenAI', r'sk-(?:proj-)?[A-Za-z0-9]{32,}'),
    ('Resend', r're_[A-Za-z0-9]{8,}_[A-Za-z0-9]{16,}'),
    ('Brevo', r'xkeysib-[0-9a-f]{64}-[A-Za-z0-9]{16}'),
    ('AWS', r'AKIA[0-9A-Z]{16}'),
    ('Google API', r'AIza[0-9A-Za-z_\-]{35}'),
    ('GitHub', r'gh[pousr]_[A-Za-z0-9]{36,}'),
    ('Chave privada', r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    ('URL de banco com senha', r'postgres(?:ql)?://[^:\s/]+:[^@\s]{6,}@[^\s/]+'),
    ('Webhook secret', r'whsec_[A-Za-z0-9+/=]{20,}'),
    ('Slack', r'xox[baprs]-[A-Za-z0-9-]{10,}'),
    ('Senha atribuída', r'(?i)(?:password|senha|secret|api_key|apikey|token)\s*[=:]\s*["\'][^"\'\s{}%$]{8,}["\']'),
])
IGNORAR = re.compile(r'(?i)(example|exemplo|placeholder|seu_|sua_|xxxx|\*\*\*|<|changeme|test_token|ci:ci@127)')

proc = subprocess.Popen(['git', 'log', '--all', '-p', '--no-color', '--format=@@COMMIT %h %ad', '--date=short'],
                        stdout=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
commit, data, arquivo = '?', '?', '?'
achados = OrderedDict()
for linha in proc.stdout:
    if linha.startswith('@@COMMIT '):
        _, commit, data = linha.split()[:3]
        continue
    if linha.startswith('+++ b/'):
        arquivo = linha[6:].strip()
        continue
    if not linha.startswith('+') or linha.startswith('+++'):
        continue
    for tipo, padrao in PADROES.items():
        for m in re.finditer(padrao, linha):
            if IGNORAR.search(m.group(0)):
                continue
            chave = (tipo, arquivo, m.group(0)[-6:])     # sufixo só para agrupar, não é impresso
            achados.setdefault(chave, (commit, data))
print(f'{len(achados)} ocorrência(s) distintas (tipo × arquivo × valor)')
for (tipo, arq, _), (c, d) in achados.items():
    print(f'- {tipo} | {arq} | commit {c} ({d})')
