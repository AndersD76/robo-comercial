# -*- coding: utf-8 -*-
"""
Limpa contato lixo já gravado nos leads de todos os clientes.

A coleta antiga gravou press@google.com e telefones falsos (IDs e avaliações
do Google lidos como telefone, DDD de outro estado). O painel já esconde
esses valores; este script os apaga do banco para que nenhum envio, export
ou integração os use.

Uso:
    python scripts/limpar_contatos_lixo.py            # só conta (não altera)
    python scripts/limpar_contatos_lixo.py --aplicar  # apaga os valores lixo

Precisa de DATABASE_URL (ex.: `railway run python scripts/...`).
"""

import argparse
import os
import sys

import psycopg2
import psycopg2.extras
from psycopg2 import sql

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from validacao_contato import limpar_contatos  # noqa: E402

CAMPOS = ('email', 'telefone', 'telefone2', 'whatsapp')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--aplicar', action='store_true',
                    help='grava a limpeza (sem isto, só mostra as contagens)')
    args = ap.parse_args()

    dsn = os.environ.get('DATABASE_URL', '')
    if dsn.startswith(('postgres://', 'psql://')):
        dsn = 'postgresql://' + dsn.split('://', 1)[1]
    if not dsn:
        sys.exit('DATABASE_URL não definido')
    conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    c = conn.cursor()
    c.execute("SELECT schema_name FROM users WHERE schema_name ~ '^emp_[0-9]+$' "
              "ORDER BY id")
    schemas = [r['schema_name'] for r in c.fetchall()]

    tot = {'leads': 0, 'afetados': 0, **{k: 0 for k in CAMPOS}}
    for schema in schemas:
        c.execute("SELECT to_regclass(%s) AS t", (f'{schema}.empresas',))
        if not c.fetchone()['t']:
            continue
        c.execute("SELECT column_name FROM information_schema.columns "
                  "WHERE table_schema = %s AND table_name = 'empresas'", (schema,))
        existentes = {r['column_name'] for r in c.fetchall()}
        cols = [k for k in CAMPOS if k in existentes]
        c.execute(sql.SQL("SELECT id, estado, {} FROM {}.empresas").format(
            sql.SQL(', ').join(map(sql.Identifier, cols)), sql.Identifier(schema)))
        linhas = c.fetchall()
        afetados = 0
        por_campo = {k: 0 for k in cols}
        for r in linhas:
            antes = dict(r)
            depois = limpar_contatos(dict(r))
            mudou = [k for k in cols if antes.get(k) and not depois.get(k)]
            if not mudou:
                continue
            afetados += 1
            for k in mudou:
                por_campo[k] += 1
            if args.aplicar:
                c.execute(sql.SQL("UPDATE {}.empresas SET {} WHERE id = %s").format(
                    sql.Identifier(schema),
                    sql.SQL(', ').join(sql.SQL('{} = NULL').format(sql.Identifier(k))
                                       for k in mudou)), (r['id'],))
        if args.aplicar:
            conn.commit()
        tot['leads'] += len(linhas)
        tot['afetados'] += afetados
        for k, v in por_campo.items():
            tot[k] += v
        if afetados:
            print(f'{schema}: {afetados} de {len(linhas)} leads com contato lixo '
                  + ' '.join(f'{k}={v}' for k, v in por_campo.items() if v))
    acao = 'LIMPOS' if args.aplicar else 'seriam limpos (rode com --aplicar)'
    print(f"\nTOTAL: {tot['afetados']} de {tot['leads']} leads {acao} — "
          + ', '.join(f'{k}: {tot[k]}' for k in CAMPOS))
    conn.close()


if __name__ == '__main__':
    main()
