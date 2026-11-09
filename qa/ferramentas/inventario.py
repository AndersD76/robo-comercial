# -*- coding: utf-8 -*-
"""Inventário das rotas do app.py a partir do código (AST): caminho, métodos,
proteção declarada e checagens de sessão dentro da função. Saída em Markdown.
Uso: python qa/ferramentas/inventario.py > qa/rotas.md"""
import ast
import sys

FONTE = sys.argv[1] if len(sys.argv) > 1 else 'app.py'
arvore = ast.parse(open(FONTE, encoding='utf-8').read())


def nome(d):
    if isinstance(d, ast.Call):
        return nome(d.func)
    if isinstance(d, ast.Attribute):
        return f'{nome(d.value)}.{d.attr}'
    if isinstance(d, ast.Name):
        return d.id
    return '?'


linhas = []
for f in ast.walk(arvore):
    if not isinstance(f, ast.FunctionDef):
        continue
    rotas, protecoes, limite = [], [], ''
    for d in f.decorator_list:
        n = nome(d)
        if n.endswith('.route') and isinstance(d, ast.Call) and d.args:
            caminho = d.args[0].value if isinstance(d.args[0], ast.Constant) else '?'
            metodos = ['GET']
            for k in d.keywords:
                if k.arg == 'methods' and isinstance(k.value, (ast.List, ast.Tuple)):
                    metodos = [e.value for e in k.value.elts if isinstance(e, ast.Constant)]
            rotas.append((caminho, metodos))
        elif n in ('login_required', 'admin_required', 'token_required'):
            protecoes.append(n.replace('_required', ''))
        elif n.endswith('limiter.limit') and isinstance(d, ast.Call) and d.args and isinstance(d.args[0], ast.Constant):
            limite = d.args[0].value
    if not rotas:
        continue
    corpo = ast.unparse(f)
    if "session.get('admin_auth')" in corpo and 'admin' not in protecoes:
        protecoes.append('admin (checado no corpo)')
    if "session.get('user_id')" in corpo and 'login' not in protecoes:
        protecoes.append('sessão (checada no corpo)')
    if '_hmac.compare_digest' in corpo:
        protecoes.append('assinatura/HMAC')
    for caminho, metodos in rotas:
        linhas.append((caminho, ','.join(metodos), f.name, ', '.join(protecoes) or '**pública**', limite))

linhas.sort()
print(f'# Rotas do app ({len(linhas)}), geradas de `{FONTE}`\n')
print('| Caminho | Métodos | Função | Proteção | Limite |')
print('|---|---|---|---|---|')
for c, m, fn, p, lim in linhas:
    print(f'| `{c}` | {m} | `{fn}` | {p} | {lim} |')
