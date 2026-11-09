"""Relatório de dados próprios: números agregados da base da Receita.

Calcula a partir do índice local completo (C:/cnpj/indice.sqlite, todos os
estados, empresas ativas com telefone ou e-mail) e grava só o resumo
agregado na tabela `relatorio_dados` do Postgres, de onde a página
/dados/empresas-ativas-no-brasil lê. Nenhum dado de empresa individual sai
do PC.

Roda sozinho depois de cada atualização mensal da base
(scripts/atualizar_receita.py); à mão:

    python scripts/relatorio_dados.py --dsn-arquivo %LOCALAPPDATA%/TurboVenda/database_url.txt
"""
import argparse
import json
import os
import sqlite3
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
from pseo_data import CNAE_POR_CODIGO, PORTE_LABELS, UF_NOMES  # noqa: E402

DDL = """CREATE TABLE IF NOT EXISTS relatorio_dados (
    id BIGSERIAL PRIMARY KEY,
    gerado_em TIMESTAMPTZ DEFAULT now(),
    base_mes TEXT NOT NULL,
    dados JSONB NOT NULL)"""


def calcular(caminho):
    c = sqlite3.connect(f'file:{caminho}?mode=ro', uri=True)
    q = lambda sql: c.execute(sql).fetchall()  # noqa: E731
    t0 = time.time()
    total, com_socio, com_tel, com_email, abertura_max = q(
        "SELECT COUNT(*), "
        "SUM(COALESCE(socio_nome, '') <> ''), SUM(COALESCE(telefone, '') <> ''), "
        "SUM(COALESCE(email, '') <> ''), MAX(CASE WHEN data_abertura <= date('now') "
        "THEN data_abertura END) FROM empresas_publicas")[0]
    por_uf = q("SELECT uf, COUNT(*) FROM empresas_publicas GROUP BY uf ORDER BY 2 DESC")
    por_ano = q("SELECT substr(data_abertura, 1, 4) AS a, COUNT(*) FROM empresas_publicas "
                "WHERE data_abertura >= '2010-01-01' AND data_abertura <= date('now') "
                "GROUP BY a ORDER BY a")
    por_porte = q("SELECT COALESCE(porte, '00'), COUNT(*) FROM empresas_publicas GROUP BY 1 ORDER BY 2 DESC")
    codigos = ','.join(f"'{k}'" for k in CNAE_POR_CODIGO)
    por_cnae = q(f"SELECT cnae_principal, COUNT(*) FROM empresas_publicas "
                 f"WHERE cnae_principal IN ({codigos}) GROUP BY 1 ORDER BY 2 DESC")
    cidades = q("SELECT municipio, uf, COUNT(*) FROM empresas_publicas "
                "GROUP BY municipio, uf ORDER BY 3 DESC LIMIT 20")
    c.close()
    print(f'[relatorio] {total:,} empresas lidas em {time.time() - t0:.0f}s')
    portes = {}
    for k, n in por_porte:
        rotulo = PORTE_LABELS.get(k, 'Não informado')
        portes[rotulo] = portes.get(rotulo, 0) + n
    return {
        'total': total, 'com_socio': com_socio, 'com_telefone': com_tel, 'com_email': com_email,
        'abertura_mais_recente': abertura_max,
        'por_uf': [{'uf': uf, 'nome': UF_NOMES.get(uf, uf), 'n': n} for uf, n in por_uf if uf in UF_NOMES],
        'por_ano': [{'ano': int(a), 'n': n} for a, n in por_ano if a and a.isdigit()],
        'por_porte': [{'porte': k, 'n': n} for k, n in sorted(portes.items(), key=lambda x: -x[1])],
        'por_segmento': [{'codigo': k, 'nome': CNAE_POR_CODIGO[k]['label'],
                          'slug': CNAE_POR_CODIGO[k]['slug'], 'n': n} for k, n in por_cnae],
        'cidades': [{'municipio': m, 'uf': uf, 'n': n} for m, uf, n in cidades],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--indice', default='C:/cnpj/indice.sqlite')
    ap.add_argument('--dsn-arquivo', help='arquivo com a DATABASE_URL (senão usa a variável)')
    ap.add_argument('--saida-json', help='também grava o resumo neste arquivo')
    args = ap.parse_args()
    try:
        with open(args.indice + '.mes', encoding='utf-8') as f:
            mes = f.read().strip()
    except OSError:
        mes = ''
    dados = calcular(args.indice)
    if args.saida_json:
        with open(args.saida_json, 'w', encoding='utf-8') as f:
            json.dump({'base_mes': mes, **dados}, f, ensure_ascii=False, indent=1)
    dsn = os.environ.get('DATABASE_URL', '')
    if args.dsn_arquivo:
        with open(os.path.expandvars(args.dsn_arquivo), encoding='utf-8-sig') as f:
            dsn = f.read().strip()
    if not dsn:
        print('[relatorio] sem DATABASE_URL: só o JSON foi gerado')
        return 0
    import psycopg2
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute(DDL)
    cur.execute('INSERT INTO relatorio_dados (base_mes, dados) VALUES (%s, %s)',
                (mes, json.dumps(dados, ensure_ascii=False)))
    conn.commit()
    conn.close()
    print(f'[relatorio] gravado no banco (base {mes or "?"})')
    return 0


if __name__ == '__main__':
    sys.exit(main())
