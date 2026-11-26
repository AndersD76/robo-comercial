"""Estatísticas por CNAE (todos os 1.332 códigos) a partir do índice local
completo da Receita, para as páginas /cnae/<código> e /cnae/<código>/<uf>.

Grava só agregados (contagens por UF, porte, ano de abertura e cidades) na
tabela `cnae_estatisticas`. Nenhum dado de empresa individual sai do PC.
Roda depois da atualização mensal (scripts/atualizar_receita.py); à mão:

    python scripts/estatisticas_cnae.py --dsn-arquivo %LOCALAPPDATA%/TurboVenda/database_url.txt
"""
import argparse
import json
import os
import sqlite3
import sys
import time
from collections import defaultdict

DDL = """CREATE TABLE IF NOT EXISTS cnae_estatisticas (
    codigo TEXT PRIMARY KEY, base_mes TEXT, dados JSONB NOT NULL,
    atualizado_em TIMESTAMPTZ DEFAULT now())"""
ANO_INICIAL = 2010
CIDADES_CNAE = 15
CIDADES_UF = 10


def calcular(caminho, log=print):
    """Uma leitura sequencial da tabela, somando em memória. (GROUP BY no
    SQLite com 26 mi de linhas num HD mecânico passava de 50 minutos por
    causa dos arquivos temporários da ordenação.)"""
    c = sqlite3.connect(f'file:{caminho}?mode=ro', uri=True)
    c.execute('PRAGMA cache_size = -200000')
    t0 = time.time()
    base = defaultdict(lambda: {'total': 0, 'com_email': 0, 'com_telefone': 0, 'com_socio': 0,
                                'por_uf': defaultdict(int), 'por_porte': defaultdict(int),
                                'por_ano': defaultdict(int), 'uf_porte': defaultdict(lambda: defaultdict(int)),
                                'uf_ano': defaultdict(lambda: defaultdict(int))})
    por_cidade = defaultdict(int)
    sql = ("SELECT cnae_principal, uf, municipio, porte, substr(data_abertura, 1, 4), "
           "COALESCE(email, '') <> '', COALESCE(telefone, '') <> '', COALESCE(socio_nome, '') <> '' "
           "FROM empresas_publicas")
    lidas = 0
    for cnae, uf, mun, porte, ano, em, tel, soc in c.execute(sql):
        lidas += 1
        if lidas % 2_000_000 == 0:
            log(f'[cnae] {lidas:,} linhas em {time.time() - t0:.0f}s')
        if not cnae:
            continue
        porte = porte or '00'
        d = base[cnae]
        d['total'] += 1
        d['com_email'] += em
        d['com_telefone'] += tel
        d['com_socio'] += soc
        d['por_uf'][uf] += 1
        d['por_porte'][porte] += 1
        d['uf_porte'][uf][porte] += 1
        if ano and ano.isdigit() and int(ano) >= ANO_INICIAL:
            d['por_ano'][ano] += 1
            d['uf_ano'][uf][ano] += 1
        por_cidade[(cnae, uf, mun)] += 1
    c.close()
    log(f'[cnae] {lidas:,} linhas lidas em {time.time() - t0:.0f}s ({len(base)} códigos)')
    cidades = defaultdict(list)
    for (cnae, uf, mun), n in por_cidade.items():
        cidades[cnae].append((n, mun, uf))
    del por_cidade
    saida = {}
    for cnae, d in base.items():
        cs = sorted(cidades.get(cnae, []), reverse=True)
        por_uf_cidades = defaultdict(list)
        for n, mun, uf in cs:
            if len(por_uf_cidades[uf]) < CIDADES_UF:
                por_uf_cidades[uf].append({'municipio': mun, 'n': n})
        saida[cnae] = {
            'total': d['total'], 'com_email': d['com_email'], 'com_telefone': d['com_telefone'],
            'com_socio': d['com_socio'],
            'por_uf': sorted(({'uf': k, 'n': v} for k, v in d['por_uf'].items() if k), key=lambda x: -x['n']),
            'por_porte': sorted(({'porte': k, 'n': v} for k, v in d['por_porte'].items()), key=lambda x: -x['n']),
            'por_ano': [{'ano': int(k), 'n': v} for k, v in sorted(d['por_ano'].items())],
            'cidades': [{'municipio': mun, 'uf': uf, 'n': n} for n, mun, uf in cs[:CIDADES_CNAE]],
            'ufs': {uf: {'porte': dict(d['uf_porte'][uf]),
                         'por_ano': [{'ano': int(k), 'n': v} for k, v in sorted(d['uf_ano'][uf].items())],
                         'cidades': por_uf_cidades[uf]} for uf in d['por_uf'] if uf},
        }
    return saida


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--indice', default='D:/cnpj/indice.sqlite')
    ap.add_argument('--dsn-arquivo', help='arquivo com a DATABASE_URL (senão usa a variável)')
    ap.add_argument('--saida-json', help='também grava tudo neste arquivo')
    args = ap.parse_args()
    try:
        with open(args.indice + '.mes', encoding='utf-8') as f:
            mes = f.read().strip()
    except OSError:
        mes = ''
    dados = calcular(args.indice)
    if args.saida_json:
        with open(args.saida_json, 'w', encoding='utf-8') as f:
            json.dump({'base_mes': mes, 'cnaes': dados}, f, ensure_ascii=False)
    dsn = os.environ.get('DATABASE_URL', '')
    if args.dsn_arquivo:
        with open(os.path.expandvars(args.dsn_arquivo), encoding='utf-8-sig') as f:
            dsn = f.read().strip()
    if not dsn:
        print('[cnae] sem DATABASE_URL: só o JSON foi gerado')
        return 0
    import psycopg2
    import psycopg2.extras
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    cur.execute(DDL)
    psycopg2.extras.execute_values(
        cur, """INSERT INTO cnae_estatisticas (codigo, base_mes, dados, atualizado_em) VALUES %s
                ON CONFLICT (codigo) DO UPDATE SET base_mes = EXCLUDED.base_mes, dados = EXCLUDED.dados,
                atualizado_em = now()""",
        [(k, mes, json.dumps(v, ensure_ascii=False)) for k, v in dados.items()],
        template='(%s, %s, %s, now())', page_size=200)
    conn.commit()
    conn.close()
    print(f'[cnae] {len(dados)} códigos gravados no banco (base {mes or "?"})')
    return 0


if __name__ == '__main__':
    sys.exit(main())
