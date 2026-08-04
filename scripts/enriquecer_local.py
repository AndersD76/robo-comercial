#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Worker local: enriquece leads com a base da Receita, sem passar pelo Neon.

Por que local: subir os ~30 milhões de estabelecimentos do Brasil para o
Neon custaria ~10 GB e a ingestão levava dias, porque cada lote é um
round-trip até us-east-1. O índice fica no PC (que já tem os ZIPs e fica
ligado), a consulta é instantânea, e só o resultado — poucos leads — sobe.

O PC não precisa receber conexão nenhuma: ele só SAI para o Neon.

Como usar:
  1) Gerar o índice local a partir dos ZIPs (uma vez por mês de dados):
       python scripts/cnpj_ingest.py --offline --dir E:/cnpj --keep \\
           --sqlite E:/cnpj/indice.sqlite --ufs "*" --todos-cnaes \\
           --so-com-contato
  2) Rodar o worker (a cada 15 min, via Agendador de Tarefas):
       set DATABASE_URL=postgresql://...
       python scripts/enriquecer_local.py --indice E:/cnpj/indice.sqlite

  --uma-vez  processa e sai (padrão, bom para o agendador)
  --limite N máximo de leads por execução (padrão 500)
"""
import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cnpj_match  # noqa: E402

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print('[fatal] psycopg2 nao instalado: pip install psycopg2-binary')
    sys.exit(1)


DDL_HEARTBEAT = """
CREATE TABLE IF NOT EXISTS public.worker_receita (
    id            INTEGER PRIMARY KEY DEFAULT 1,
    ultima_execucao TIMESTAMPTZ,
    leads_processados INTEGER DEFAULT 0,
    leads_enriquecidos INTEGER DEFAULT 0,
    indice_linhas INTEGER,
    detalhe       TEXT
)"""


def abrir_indice(caminho):
    if not os.path.exists(caminho):
        print(f'[fatal] indice nao encontrado: {caminho}')
        print('        gere com: python scripts/cnpj_ingest.py --offline '
              '--dir E:/cnpj --sqlite ' + caminho +
              ' --ufs "*" --todos-cnaes --so-com-contato')
        sys.exit(2)
    con = sqlite3.connect(f'file:{caminho}?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    return con


def schemas_de_clientes(pg):
    c = pg.cursor()
    c.execute("""SELECT schemaname FROM pg_tables WHERE tablename='empresas'
                 AND schemaname LIKE 'emp!_%' ESCAPE '!'
                 ORDER BY schemaname""")
    return [r['schemaname'] for r in c.fetchall()]


def leads_pendentes(pg, schema, limite):
    """Leads que ainda nao passaram pela Receita.

    Criterio: sem CNPJ ou sem decisor — que e exatamente o que a base
    tem para oferecer.
    """
    c = pg.cursor()
    c.execute(f"""
        SELECT e.id, e.nome_fantasia, e.cnpj, e.telefone, e.whatsapp,
               e.estado, e.cidade, e.email
        FROM "{schema}".empresas e
        WHERE e.telefone IS NOT NULL
          AND (e.cnpj IS NULL OR NOT EXISTS (
                SELECT 1 FROM "{schema}".contatos ct
                WHERE ct.empresa_id = e.id AND ct.decisor = 1))
        ORDER BY e.encontrado_em DESC
        LIMIT %s""", (limite,))
    return c.fetchall()


def buscar_oficial(idx, lead):
    """Acha a empresa no indice local. {} se nao identificou."""
    cur = idx.cursor()
    cnpj = ''.join(ch for ch in str(lead.get('cnpj') or '') if ch.isdigit())
    if len(cnpj) == 14:
        cur.execute('SELECT * FROM empresas_publicas WHERE cnpj_basico=?',
                    (cnpj[:8],))
        r = cur.fetchone()
        if r:
            return dict(r)
    variantes = cnpj_match.variantes_telefone(lead)
    if not variantes:
        return {}
    marks = ','.join('?' * len(variantes))
    # LIMIT 2: 23% dos telefones da Receita sao de contador (um deles em
    # 8.783 empresas). Telefone que nao identifica uma empresa so nao vale.
    cur.execute(
        f'SELECT * FROM empresas_publicas WHERE telefone IN ({marks}) '
        f'OR telefone2 IN ({marks}) LIMIT 2',
        variantes + variantes)
    achados = cur.fetchall()
    if len(achados) != 1:
        return {}
    cand = dict(achados[0])
    if not cnpj_match.nome_confere(lead.get('nome_fantasia'), cand):
        return {}
    return cand


def gravar(pg, schema, lead_id, novo):
    c = pg.cursor()
    campos, valores = [], []
    for coluna, chave in (('nome_fantasia', 'nome_fantasia'),
                          ('razao_social', 'razao_social'),
                          ('estado', 'estado'), ('cidade', 'cidade'),
                          ('segmento', 'segmento'), ('email', 'email')):
        if novo.get(chave):
            campos.append(f'{coluna}=%s')
            valores.append(novo[chave])
    if campos:
        valores.append(lead_id)
        c.execute(f'UPDATE "{schema}".empresas SET {", ".join(campos)} '
                  f'WHERE id=%s', valores)
    if novo.get('decisor_nome'):
        c.execute(f'SELECT 1 FROM "{schema}".contatos WHERE empresa_id=%s '
                  f'AND decisor=1 LIMIT 1', (lead_id,))
        if not c.fetchone():
            c.execute(
                f'INSERT INTO "{schema}".contatos '
                f'(empresa_id, nome, cargo, decisor) VALUES (%s,%s,%s,1)',
                (lead_id, novo['decisor_nome'],
                 novo.get('decisor_cargo') or 'Sócio'))


def bater_ponto(pg, processados, enriquecidos, linhas_indice, detalhe=''):
    """Registra que o worker esta vivo, para o app avisar se parar."""
    c = pg.cursor()
    c.execute(DDL_HEARTBEAT)
    c.execute("""INSERT INTO public.worker_receita
                 (id, ultima_execucao, leads_processados, leads_enriquecidos,
                  indice_linhas, detalhe)
                 VALUES (1, NOW(), %s, %s, %s, %s)
                 ON CONFLICT (id) DO UPDATE SET
                   ultima_execucao = NOW(),
                   leads_processados = EXCLUDED.leads_processados,
                   leads_enriquecidos = EXCLUDED.leads_enriquecidos,
                   indice_linhas = EXCLUDED.indice_linhas,
                   detalhe = EXCLUDED.detalhe""",
              (processados, enriquecidos, linhas_indice, detalhe[:400]))
    pg.commit()


def main():
    ap = argparse.ArgumentParser(description='Enriquece leads localmente')
    ap.add_argument('--indice', default=os.environ.get(
        'CNPJ_INDICE', 'E:/cnpj/indice.sqlite'))
    ap.add_argument('--limite', type=int, default=500)
    args = ap.parse_args()

    dsn = os.environ.get('DATABASE_URL', '')
    if not dsn:
        print('[fatal] DATABASE_URL nao definido')
        sys.exit(2)

    idx = abrir_indice(args.indice)
    linhas = idx.execute('SELECT COUNT(*) FROM empresas_publicas').fetchone()[0]
    print(f'[indice] {args.indice}: {linhas:,} empresas')

    pg = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    processados = enriquecidos = 0
    erro = ''
    try:
        for schema in schemas_de_clientes(pg):
            leads = leads_pendentes(pg, schema, args.limite)
            if not leads:
                continue
            ok = 0
            for lead in leads:
                processados += 1
                oficial = buscar_oficial(idx, dict(lead))
                if not oficial:
                    continue
                novo, casou = cnpj_match.aplicar(dict(lead), oficial)
                if not casou:
                    continue
                gravar(pg, schema, lead['id'], novo)
                ok += 1
            pg.commit()
            enriquecidos += ok
            print(f'[{schema}] {len(leads)} pendentes, {ok} enriquecidos')
    except Exception as e:
        pg.rollback()
        erro = f'{type(e).__name__}: {e}'
        print(f'[erro] {erro}')
    finally:
        bater_ponto(pg, processados, enriquecidos, linhas, erro)
        pg.close()
        idx.close()
    print(f'[fim] {processados} processados, {enriquecidos} enriquecidos')


if __name__ == '__main__':
    main()
