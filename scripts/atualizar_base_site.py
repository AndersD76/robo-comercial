#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Atualiza a base de empresas do site (empresas_publicas no Postgres) a partir
do índice local da Receita, sem tirar o site do ar.

Carrega tudo numa tabela nova, cria os mesmos índices e as visões de resumo
das páginas /empresas sobre ela e troca os nomes numa transação só. A tabela
antiga é apagada depois da conferência (o Neon guarda o histórico para
restaurar, se preciso).

Recorte (decisão de 09/11/2026):
  - PR, RS e SC com todos os segmentos (como já estava);
  - resto do Brasil nos 54 segmentos B2B das páginas /empresas, completos
    (antes a carga fora do Sul era parcial: SP tinha 723 mil de 8,2 mi);
  - só empresas ativas com telefone ou e-mail (o índice local já é assim);
  - sócio não sobe (custo de armazenamento; decisão de 09/11/2026).

Uso:
  python scripts/atualizar_base_site.py                 # DSN do arquivo do worker
  python scripts/atualizar_base_site.py --manter-antiga # não apaga a tabela antiga
"""
import argparse
import csv
import io
import os
import re
import sqlite3
import sys
import time

import psycopg2

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from pseo_data import CNAE_CODIGOS  # noqa: E402

TABELA, NOVA, ANTIGA = 'empresas_publicas', 'empresas_publicas_nova', 'empresas_publicas_antiga'
VISOES = ('pseo_resumo_cnae_cidade', 'pseo_resumo_cidade')
SUL = ('PR', 'RS', 'SC')
COLUNAS = ('cnpj_basico', 'razao_social', 'nome_fantasia', 'municipio', 'uf', 'bairro',
           'cnae_principal', 'porte', 'data_abertura', 'situacao', 'telefone', 'telefone2',
           'email')
LOTE = 100_000
_DATA = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def log(msg):
    print(f'{time.strftime("%H:%M:%S")} {msg}', flush=True)


def linhas_do_indice(indice, limite=0):
    """Gera as linhas do recorte, já no formato da tabela do site."""
    con = sqlite3.connect(f'file:{indice}?mode=ro', uri=True)
    marcas = ','.join('?' * len(CNAE_CODIGOS))
    sql = (f"SELECT {', '.join(COLUNAS)} FROM empresas_publicas "
           f"WHERE situacao = '02' AND (uf IN ('PR','RS','SC') OR cnae_principal IN ({marcas}))"
           + (f' LIMIT {int(limite)}' if limite else ''))
    for r in con.execute(sql, list(CNAE_CODIGOS)):
        r = [v.replace('\x00', '') if isinstance(v, str) else v for v in r]
        data = r[8] or ''
        r[8] = data if _DATA.match(data) and data[:4] != '0000' else None
        yield r
    con.close()


def carregar(conn, indice, limite=0):
    c = conn.cursor()
    c.execute(f'DROP TABLE IF EXISTS {NOVA} CASCADE')
    c.execute(f"""CREATE TABLE {NOVA} (
        cnpj_basico TEXT NOT NULL, razao_social TEXT, nome_fantasia TEXT, municipio TEXT,
        uf TEXT, bairro TEXT, cnae_principal TEXT, porte TEXT, data_abertura DATE,
        situacao TEXT, telefone TEXT, telefone2 TEXT, email TEXT,
        socio_nome TEXT, socio_cargo TEXT)""")
    conn.commit()
    copia = f"COPY {NOVA} ({', '.join(COLUNAS)}) FROM STDIN WITH (FORMAT csv)"
    total, buf, w = 0, io.StringIO(), None
    w = csv.writer(buf, lineterminator='\n')
    for linha in linhas_do_indice(indice, limite):
        w.writerow(['' if v is None else v for v in linha])
        total += 1
        if total % LOTE == 0:
            buf.seek(0)
            c.copy_expert(copia, buf)
            conn.commit()
            buf = io.StringIO()
            w = csv.writer(buf, lineterminator='\n')
            if total % 1_000_000 == 0:
                log(f'{total:,} linhas enviadas')
    buf.seek(0)
    c.copy_expert(copia, buf)
    conn.commit()
    log(f'carga terminou: {total:,} linhas')
    return total


def indices_e_visoes(conn):
    """Recria na tabela nova os índices e as visões que existem hoje na antiga,
    com sufixo _nova (lidos do próprio banco, para não divergir do app)."""
    c = conn.cursor()
    c.execute(f'ALTER TABLE {NOVA} ADD CONSTRAINT {NOVA}_pkey PRIMARY KEY (cnpj_basico)')
    conn.commit()
    c.execute("SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public' "
              "AND tablename = %s AND indexname <> %s", (TABELA, f'{TABELA}_pkey'))
    for nome, definicao in c.fetchall():
        d = definicao.replace(f'INDEX {nome} ON', f'INDEX {nome}_nova ON')
        d = d.replace(f'ON public.{TABELA} ', f'ON public.{NOVA} ')
        c.execute(d)
        conn.commit()
        log(f'índice {nome}_nova criado')
    c.execute(f'ANALYZE {NOVA}')
    conn.commit()
    for visao in VISOES:
        c.execute('SELECT definition FROM pg_matviews WHERE schemaname = %s AND matviewname = %s',
                  ('public', visao))
        definicao = c.fetchone()[0].rstrip().rstrip(';')
        definicao = re.sub(rf'\b{TABELA}\b', NOVA, definicao)
        c.execute(f'DROP MATERIALIZED VIEW IF EXISTS {visao}_nova')
        c.execute(f'CREATE MATERIALIZED VIEW {visao}_nova AS {definicao}')
        c.execute("SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public' "
                  "AND tablename = %s", (visao,))
        for nome, definicao_i in c.fetchall():
            novo = nome.replace(visao, f'{visao}_nova', 1)
            c.execute(definicao_i.replace(f'INDEX {nome} ON', f'INDEX {novo} ON')
                      .replace(f'ON public.{visao} ', f'ON public.{visao}_nova '))
        conn.commit()
        log(f'visão {visao}_nova criada')


def trocar(conn):
    """Troca tabela, índices e visões numa transação só."""
    c = conn.cursor()
    c.execute("SET lock_timeout = '15s'")
    c.execute("SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND tablename = %s",
              (TABELA,))
    antigos = [r[0] for r in c.fetchall()]
    c.execute("SELECT tablename, indexname FROM pg_indexes WHERE schemaname = 'public' "
              "AND tablename = ANY(%s)", (list(VISOES),))
    antigos_visoes = c.fetchall()
    c.execute(f'ALTER TABLE {TABELA} RENAME TO {ANTIGA}')
    for nome in antigos:
        c.execute(f'ALTER INDEX {nome} RENAME TO {nome}_antiga')
    for visao in VISOES:
        c.execute(f'ALTER MATERIALIZED VIEW {visao} RENAME TO {visao}_antiga')
    for _visao, nome in antigos_visoes:
        c.execute(f'ALTER INDEX {nome} RENAME TO {nome}_antiga')
    c.execute(f'ALTER TABLE {NOVA} RENAME TO {TABELA}')
    for nome in antigos:
        c.execute(f'ALTER INDEX {nome.replace(TABELA, NOVA, 1) if nome == TABELA + "_pkey" else nome + "_nova"} '
                  f'RENAME TO {nome}')
    for visao in VISOES:
        c.execute(f'ALTER MATERIALIZED VIEW {visao}_nova RENAME TO {visao}')
    for visao, nome in antigos_visoes:
        c.execute(f'ALTER INDEX {nome.replace(visao, visao + "_nova", 1)} RENAME TO {nome}')
    conn.commit()
    log('troca feita: o site já usa a base nova')


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--indice', default='C:/cnpj/indice.sqlite')
    ap.add_argument('--dsn-arquivo', default=os.path.expandvars(
        r'%LOCALAPPDATA%\TurboVenda\database_url.txt'))
    ap.add_argument('--manter-antiga', action='store_true')
    ap.add_argument('--ensaio', action='store_true',
                    help='carrega 200 mil linhas, cria índices e visões e apaga tudo, sem trocar')
    args = ap.parse_args()
    dsn = os.environ.get('DATABASE_URL') or open(args.dsn_arquivo, encoding='utf-8').read().strip()
    conn = psycopg2.connect(dsn, keepalives=1, keepalives_idle=60)
    try:
        c = conn.cursor()
        c.execute(f'SELECT COUNT(*), MAX(data_abertura) FROM {TABELA}')
        antes, base_antes = c.fetchone()
        log(f'base atual: {antes:,} empresas, abertura mais recente {base_antes}')
        total = carregar(conn, args.indice, 200_000 if args.ensaio else 0)
        if args.ensaio:
            indices_e_visoes(conn)
            c = conn.cursor()
            for visao in VISOES:
                c.execute(f'SELECT COUNT(*) FROM {visao}_nova')
                log(f'ensaio: {visao}_nova com {c.fetchone()[0]:,} linhas')
                c.execute(f'DROP MATERIALIZED VIEW {visao}_nova')
            c.execute(f'DROP TABLE {NOVA} CASCADE')
            conn.commit()
            log('ensaio ok: tabela e visões de teste apagadas, nada foi trocado')
            return 0
        if total < 0.8 * antes:
            raise SystemExit(f'carga com {total:,} linhas, bem menos que as {antes:,} atuais: '
                             'nada foi trocado (confira o índice local)')
        indices_e_visoes(conn)
        for tentativa in range(1, 6):
            try:
                trocar(conn)
                break
            except psycopg2.errors.LockNotAvailable:
                conn.rollback()
                log(f'tabela ocupada por uma consulta do site; nova tentativa ({tentativa}/5)')
                time.sleep(20)
        else:
            raise SystemExit('não consegui trocar as tabelas; a nova ficou como empresas_publicas_nova')
        c = conn.cursor()
        c.execute(f'SELECT COUNT(*), MAX(data_abertura) FROM {TABELA}')
        depois, base_depois = c.fetchone()
        log(f'base nova: {depois:,} empresas, abertura mais recente {base_depois}')
        if not args.manter_antiga:
            c.execute(f'DROP TABLE {ANTIGA} CASCADE')
            conn.commit()
            log('tabela antiga apagada')
    finally:
        conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
