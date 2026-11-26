# -*- coding: utf-8 -*-
"""Reparo das tabelas "sombra": tabelas que só existem no schema public, mas
foram criadas também dentro de schemas de cliente (emp_N).

Causa: o DATABASE_URL apontava para o pooler do Neon (PgBouncer em modo
transação). Lá, o `SET search_path TO emp_N, public` de um cliente fica na
conexão do servidor e vaza para o próximo cliente que a recebe. A criação de
tabela do app (CREATE TABLE IF NOT EXISTS ...) caiu em emp_N, e parte das
gravações (telemetria, Search Console, IndexNow) foi parar ali em vez do
public. Desde a correção o app usa a conexão direta, sem pooler.

Aqui, para cada sombra de uma lista FECHADA de tabelas públicas: copia as
linhas para o public (sem duplicar; ids seriais são regenerados) e apaga a
sombra, numa transação por tabela. Tabelas legítimas do cliente (empresas,
contatos, bot_config...) nunca são tocadas.
"""
from psycopg2 import sql as S

import crescimento

PUBLICAS = {
    'users', 'pagamentos', 'api_tokens', 'senha_reset', 'eventos', 'pageviews', 'cta_cliques',
    'busca_consultas', 'busca_sitemaps', 'busca_inspecao', 'relatorios_semanais', 'indexnow_enviados',
    'bots_ligados', 'empresas_publicas', 'cnae_estatisticas', 'share_of_voice', 'relatorio_dados',
    'worker_receita', 'conteudo_execucoes', 'mapa_expansao',
} | {sql.split('EXISTS', 1)[1].split('(', 1)[0].strip() for sql in crescimento.DDL if sql.startswith('CREATE TABLE')}
# dependentes primeiro (chaves estrangeiras apontando para users)
ORDEM = ['api_tokens', 'senha_reset', 'pagamentos', 'eventos', 'leads_isca']
TRAVA = 7700507


def sombras(cur):
    cur.execute("""SELECT table_schema, table_name FROM information_schema.tables
                   WHERE table_schema ~ '^emp_[0-9]+$' AND table_type = 'BASE TABLE' AND table_name = ANY(%s)""",
                (sorted(PUBLICAS),))
    achadas = [(r['table_schema'], r['table_name']) for r in cur.fetchall()]
    peso = {t: i for i, t in enumerate(ORDEM)}
    return sorted(achadas, key=lambda x: (peso.get(x[1], len(ORDEM)), x[1] == 'users', x[0], x[1]))


def _colunas(cur, schema, tabela):
    cur.execute("""SELECT column_name, column_default FROM information_schema.columns
                   WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position""", (schema, tabela))
    return [(r['column_name'], r['column_default'] or '') for r in cur.fetchall()]


def reparar(conn, log=print):
    """Devolve [(schema, tabela, linhas_copiadas)] do que foi reparado."""
    cur = conn.cursor()
    cur.execute('SET search_path TO public')
    feito = []
    for schema, tabela in sombras(cur):
        try:
            publicas = _colunas(cur, 'public', tabela)
            if not publicas:
                log(f'[reparo] {schema}.{tabela}: não existe no public, fica como está')
                conn.rollback()
                cur.execute('SET search_path TO public')
                continue
            na_sombra = {c for c, _ in _colunas(cur, schema, tabela)}
            # coluna serial do public é regerada (o id da sombra colidiria)
            cols = [c for c, padrao in publicas if c in na_sombra and not padrao.startswith('nextval(')]
            cur.execute(S.SQL('SELECT COUNT(*) AS n FROM {}.{}').format(S.Identifier(schema), S.Identifier(tabela)))
            n = cur.fetchone()['n']
            copiadas = 0
            if n and cols:
                lista = S.SQL(', ').join(S.Identifier(c) for c in cols)
                cur.execute(S.SQL('INSERT INTO public.{t} ({c}) SELECT {c} FROM {s}.{t} ON CONFLICT DO NOTHING').format(
                    t=S.Identifier(tabela), c=lista, s=S.Identifier(schema)))
                copiadas = cur.rowcount
            cur.execute(S.SQL('DROP TABLE {}.{}').format(S.Identifier(schema), S.Identifier(tabela)))
            conn.commit()
            feito.append((schema, tabela, copiadas))
            log(f'[reparo] {schema}.{tabela}: {copiadas} de {n} linha(s) levadas ao public; sombra apagada')
        except Exception as e:
            conn.rollback()
            cur.execute('SET search_path TO public')
            log(f'[reparo] {schema}.{tabela}: não reparada ({type(e).__name__}: {str(e)[:160]})')
    return feito
