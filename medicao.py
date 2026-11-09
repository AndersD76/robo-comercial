"""Medição orgânica (Fase 6 do growth): ingestão de busca, painel e relatório.

- Search Console (conta de serviço, só leitura): consultas × páginas × dia,
  sitemaps (enviadas × indexadas) e inspeção das URLs prioritárias.
- Bing Webmaster (chave de API): consultas e páginas.
- Relatório semanal em Markdown a partir da telemetria do próprio site
  (pageviews, users, share_of_voice) e, quando houver, dos dados de busca.

Tudo grava em tabelas espelho no Postgres do app (padrão do portfólio):
busca_consultas, busca_sitemaps, busca_inspecao, relatorios_semanais.
Variáveis: GSC_CREDENCIAIS_JSON (conteúdo do JSON da conta de serviço),
GSC_PROPRIEDADE (ex. 'sc-domain:turbovenda.com.br' ou
'https://www.turbovenda.com.br/'), BING_API_KEY.
"""
import json
import re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

SITE = 'https://www.turbovenda.com.br'
URLS_PRIORITARIAS = [
    '/', '/precos', '/ferramentas', '/ferramentas/lista-de-empresas',
    '/ferramentas/calculadora-de-leads', '/ferramentas/gerador-de-mensagem-de-prospeccao',
    '/dados/empresas-ativas-no-brasil', '/alternativas/econodata',
    '/blog/como-prospectar-clientes-b2b', '/blog/base-de-dados-de-empresas-cnpj',
]
DDL = """
CREATE TABLE IF NOT EXISTS busca_consultas (
    fonte TEXT NOT NULL, data DATE NOT NULL, consulta TEXT NOT NULL, pagina TEXT NOT NULL,
    cliques INTEGER, impressoes INTEGER, posicao REAL,
    PRIMARY KEY (fonte, data, consulta, pagina));
CREATE TABLE IF NOT EXISTS busca_sitemaps (
    fonte TEXT NOT NULL, coletado_em DATE NOT NULL, sitemap TEXT NOT NULL,
    enviadas INTEGER, indexadas INTEGER, PRIMARY KEY (fonte, coletado_em, sitemap));
CREATE TABLE IF NOT EXISTS busca_inspecao (
    coletado_em DATE NOT NULL, url TEXT NOT NULL, veredito TEXT, estado TEXT,
    ultimo_rastreio TEXT, PRIMARY KEY (coletado_em, url));
CREATE TABLE IF NOT EXISTS relatorios_semanais (
    semana DATE PRIMARY KEY, gerado_em TIMESTAMPTZ DEFAULT now(), markdown TEXT NOT NULL);
"""
# CTR orgânico típico por posição (referência para achar título a reescrever);
# é uma régua aproximada, não um dado do site
CTR_ESPERADO = {1: .28, 2: .15, 3: .11, 4: .08, 5: .07, 6: .05, 7: .04, 8: .035, 9: .03, 10: .025}
ORGANICO = r"referrer ~* '(^|\.)(google|bing|duckduckgo)\.'"
IA = r"(referrer ~* 'chatgpt|openai|perplexity|copilot|gemini|claude\.ai' OR utm_source ~* 'chatgpt|perplexity|copilot|gemini')"


def criar_tabelas(cur):
    cur.execute(DDL)


# --- Search Console -----------------------------------------------------------

def _sessao_gsc(credenciais_json):
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    info = json.loads(credenciais_json)
    cred = service_account.Credentials.from_service_account_info(
        info, scopes=['https://www.googleapis.com/auth/webmasters.readonly'])
    return AuthorizedSession(cred)


def ingerir_gsc(conn, credenciais_json, propriedade, dias=5, sessao=None):
    """Últimos `dias` disponíveis (o GSC atrasa ~2 dias). Idempotente."""
    s = sessao or _sessao_gsc(credenciais_json)
    base = f'https://www.googleapis.com/webmasters/v3/sites/{quote(propriedade, safe="")}'
    fim = date.today() - timedelta(days=2)
    ini = fim - timedelta(days=dias - 1)
    cur = conn.cursor()
    criar_tabelas(cur)
    linhas, inicio = 0, 0
    while True:
        r = s.post(f'{base}/searchAnalytics/query', json={
            'startDate': ini.isoformat(), 'endDate': fim.isoformat(),
            'dimensions': ['date', 'query', 'page'], 'rowLimit': 25000, 'startRow': inicio})
        r.raise_for_status()
        rows = r.json().get('rows', [])
        for row in rows:
            d, q, p = row['keys']
            cur.execute("""INSERT INTO busca_consultas VALUES ('google', %s, %s, %s, %s, %s, %s)
                           ON CONFLICT (fonte, data, consulta, pagina) DO UPDATE SET
                           cliques = EXCLUDED.cliques, impressoes = EXCLUDED.impressoes,
                           posicao = EXCLUDED.posicao""",
                        (d, q[:500], p.replace(SITE, '') or '/', int(row.get('clicks', 0)),
                         int(row.get('impressions', 0)), float(row.get('position', 0))))
        linhas += len(rows)
        if len(rows) < 25000:
            break
        inicio += 25000
    r = s.get(f'{base}/sitemaps')
    r.raise_for_status()
    hoje = date.today()
    for sm in r.json().get('sitemap', []):
        conteudo = sm.get('contents') or [{}]
        env = sum(int(c.get('submitted', 0) or 0) for c in conteudo)
        idx = sum(int(c.get('indexed', 0) or 0) for c in conteudo)
        cur.execute("""INSERT INTO busca_sitemaps VALUES ('google', %s, %s, %s, %s)
                       ON CONFLICT DO NOTHING""", (hoje, sm.get('path', ''), env, idx))
    for caminho in URLS_PRIORITARIAS:
        r = s.post('https://searchconsole.googleapis.com/v1/urlInspection/index:inspect',
                   json={'inspectionUrl': SITE + caminho, 'siteUrl': propriedade})
        if r.status_code != 200:
            continue
        st = r.json().get('inspectionResult', {}).get('indexStatusResult', {})
        cur.execute("""INSERT INTO busca_inspecao VALUES (%s, %s, %s, %s, %s)
                       ON CONFLICT DO NOTHING""",
                    (hoje, caminho, st.get('verdict'), st.get('coverageState'), st.get('lastCrawlTime')))
    conn.commit()
    return linhas


# --- Bing Webmaster -----------------------------------------------------------

def _data_bing(valor):
    m = re.search(r'/Date\((\d+)', valor or '')
    return datetime.fromtimestamp(int(m.group(1)) / 1000, tz=timezone.utc).date() if m else None


def ingerir_bing(conn, chave, sessao=None):
    """GetQueryStats (consulta × semana) e GetPageStats (página × semana)."""
    import requests
    s = sessao or requests.Session()
    cur = conn.cursor()
    criar_tabelas(cur)
    total = 0
    for metodo, campo in (('GetQueryStats', 'consulta'), ('GetPageStats', 'pagina')):
        r = s.get(f'https://ssl.bing.com/webmaster/api.svc/json/{metodo}',
                  params={'siteUrl': SITE + '/', 'apikey': chave}, timeout=60)
        r.raise_for_status()
        for x in r.json().get('d', []):
            d = _data_bing(x.get('Date'))
            if not d:
                continue
            chave_linha = x.get('Query', '')[:500]
            consulta, pagina = ((chave_linha, '*') if campo == 'consulta'
                                else ('*', chave_linha.replace(SITE, '') or '/'))
            cur.execute("""INSERT INTO busca_consultas VALUES ('bing', %s, %s, %s, %s, %s, %s)
                           ON CONFLICT (fonte, data, consulta, pagina) DO UPDATE SET
                           cliques = EXCLUDED.cliques, impressoes = EXCLUDED.impressoes,
                           posicao = EXCLUDED.posicao""",
                        (d, consulta, pagina, int(x.get('Clicks', 0)), int(x.get('Impressions', 0)),
                         float(x.get('AvgImpressionPosition', 0) or 0)))
            total += 1
    conn.commit()
    return total


# --- Painel e relatório -------------------------------------------------------

def _q(cur, sql, params=()):
    cur.execute(sql, params)
    return cur.fetchall()


def _existe(cur, tabela):
    cur.execute('SELECT to_regclass(%s) AS t', (f'public.{tabela}',))
    linha = cur.fetchone()
    return bool(linha['t'] if isinstance(linha, dict) else linha[0])


def tipo_de_pagina(path):
    if path == '/':
        return 'home'
    if path.startswith('/empresas/cidade/'):
        return 'empresas por cidade'
    if re.match(r'^/empresas/[^/]+/estado/', path):
        return 'segmento por estado'
    if re.match(r'^/empresas/[^/]+/[^/]+$', path):
        return 'segmento por cidade'
    if re.match(r'^/empresas/[^/]+$', path):
        return 'segmento'
    return (path.strip('/').split('/')[0] or 'home')


def dados_painel(cur):
    """Tudo o que o /admin/organico mostra. `cur` com RealDictCursor."""
    d = {}
    d['entradas'] = _q(cur, f"""
        SELECT COUNT(*) FILTER (WHERE created_at >= now() - interval '28 days') AS atual,
               COUNT(*) FILTER (WHERE created_at < now() - interval '28 days'
                                  AND created_at >= now() - interval '56 days') AS anterior
        FROM pageviews WHERE NOT is_bot AND entrada AND {ORGANICO}""")[0]
    d['entradas_ia'] = _q(cur, f"""
        SELECT COUNT(*) AS n FROM pageviews WHERE NOT is_bot AND entrada AND {IA}
          AND created_at >= now() - interval '28 days'""")[0]['n']
    linhas = _q(cur, f"""SELECT path, COUNT(*) AS n FROM pageviews
                         WHERE NOT is_bot AND entrada AND {ORGANICO}
                           AND created_at >= now() - interval '28 days' GROUP BY path""")
    por_tipo = {}
    for r in linhas:
        t = tipo_de_pagina(r['path'])
        por_tipo[t] = por_tipo.get(t, 0) + r['n']
    d['por_tipo'] = sorted(por_tipo.items(), key=lambda x: -x[1])
    d['cadastros'] = _q(cur, """
        SELECT COALESCE(NULLIF(utm_source, ''), '(sem utm)') AS origem, COUNT(*) AS n
        FROM users WHERE criado_em >= now() - interval '28 days' GROUP BY 1 ORDER BY 2 DESC""")
    d['robos'] = _q(cur, """
        SELECT robo, COUNT(*) AS n, COUNT(*) FILTER (WHERE status = 429) AS bloqueados
        FROM pageviews WHERE robo <> '' AND created_at >= now() - interval '28 days'
        GROUP BY robo ORDER BY n DESC""")
    d['sov'] = (_q(cur, """SELECT rodada, COUNT(*) AS perguntas, SUM(citou::int) AS citado,
                                  SUM(nos_resultados::int) AS nos_resultados
                           FROM share_of_voice WHERE erro = '' GROUP BY rodada ORDER BY rodada DESC LIMIT 8""")
                if _existe(cur, 'share_of_voice') else [])
    d['gsc'] = _existe(cur, 'busca_consultas') and _q(
        cur, "SELECT COUNT(*) AS n FROM busca_consultas WHERE fonte = 'google'")[0]['n'] > 0
    if d['gsc']:
        d['oportunidades'] = _q(cur, """
            SELECT consulta, pagina, SUM(impressoes) AS imp, SUM(cliques) AS cli,
                   SUM(posicao * impressoes) / NULLIF(SUM(impressoes), 0) AS pos
            FROM busca_consultas WHERE fonte = 'google' AND data >= current_date - 28
            GROUP BY 1, 2 HAVING SUM(impressoes) >= 20
               AND SUM(posicao * impressoes) / NULLIF(SUM(impressoes), 0) BETWEEN 4 AND 15
            ORDER BY imp DESC LIMIT 30""")
        ctr = _q(cur, """
            SELECT pagina, SUM(impressoes) AS imp, SUM(cliques) AS cli,
                   SUM(posicao * impressoes) / NULLIF(SUM(impressoes), 0) AS pos
            FROM busca_consultas WHERE fonte = 'google' AND data >= current_date - 28
            GROUP BY 1 HAVING SUM(impressoes) >= 100""")
        d['ctr_baixo'] = [r for r in ctr if r['pos'] and round(r['pos']) in CTR_ESPERADO
                          and r['cli'] / r['imp'] < 0.6 * CTR_ESPERADO[round(r['pos'])]][:20]
        d['indexacao'] = (_q(cur, """SELECT sitemap, enviadas, indexadas FROM busca_sitemaps
                                     WHERE coletado_em = (SELECT MAX(coletado_em) FROM busca_sitemaps)
                                     ORDER BY sitemap""") if _existe(cur, 'busca_sitemaps') else [])
        d['inspecao'] = (_q(cur, """SELECT url, veredito, estado, ultimo_rastreio FROM busca_inspecao
                                    WHERE coletado_em = (SELECT MAX(coletado_em) FROM busca_inspecao)
                                    ORDER BY url""") if _existe(cur, 'busca_inspecao') else [])
    return d


def gerar_relatorio_semanal(cur, hoje=None):
    """Markdown da semana que terminou ontem, comparada com a anterior."""
    hoje = hoje or date.today()
    fim = hoje - timedelta(days=hoje.weekday())          # segunda desta semana
    ini, ini_ant = fim - timedelta(days=7), fim - timedelta(days=14)
    pags = _q(cur, f"""
        SELECT path,
               COUNT(*) FILTER (WHERE created_at >= %s AND created_at < %s) AS atual,
               COUNT(*) FILTER (WHERE created_at >= %s AND created_at < %s) AS anterior
        FROM pageviews WHERE NOT is_bot AND entrada AND {ORGANICO}
          AND created_at >= %s AND created_at < %s GROUP BY path""",
              (ini, fim, ini_ant, ini, ini_ant, fim))
    atual = sum(r['atual'] for r in pags)
    anterior = sum(r['anterior'] for r in pags)
    subiu = sorted(pags, key=lambda r: r['anterior'] - r['atual'])[:5]
    caiu = sorted(pags, key=lambda r: r['atual'] - r['anterior'])[:5]
    cad = _q(cur, """SELECT COUNT(*) FILTER (WHERE criado_em >= %s AND criado_em < %s) AS atual,
                            COUNT(*) FILTER (WHERE criado_em >= %s AND criado_em < %s) AS anterior
                     FROM users""", (ini, fim, ini_ant, ini))[0]
    ia = _q(cur, f"""SELECT COUNT(*) AS n FROM pageviews WHERE NOT is_bot AND entrada AND {IA}
                     AND created_at >= %s AND created_at < %s""", (ini, fim))[0]['n']
    robos = _q(cur, """SELECT robo, COUNT(*) AS n FROM pageviews WHERE robo <> ''
                       AND created_at >= %s AND created_at < %s GROUP BY robo ORDER BY n DESC LIMIT 8""",
               (ini, fim))
    bloq = sum(r['n'] for r in _q(cur, """SELECT COUNT(*) AS n FROM pageviews WHERE status = 429
                                          AND created_at >= %s AND created_at < %s""", (ini, fim)))
    sov = (_q(cur, """SELECT rodada, COUNT(*) AS n, SUM(citou::int) AS c FROM share_of_voice
                      WHERE erro = '' GROUP BY rodada ORDER BY rodada DESC LIMIT 1""")
           if _existe(cur, 'share_of_voice') else [])
    var = (atual - anterior) / anterior if anterior else None
    robos_txt = (', '.join('%s (%d)' % (r['robo'], r['n']) for r in robos)
                 or 'sem registro no período (o registro por nome começou em 09/11/2026)')
    acoes = []
    if var is not None and var < -0.15:
        acoes.append('Entradas orgânicas caíram mais de 15%: rodar `growth/ferramentas/frescor.py` e revisar as páginas que mais caíram (lista abaixo).')
    if bloq:
        acoes.append(f'{bloq} respostas 429 para robôs na semana: conferir se algum buscador verificado está sendo limitado.')
    if robos and not any(r['robo'] == 'Bingbot' for r in robos):
        acoes.append('Bingbot não apareceu na semana: conferir o Bing Webmaster Tools e o envio do IndexNow.')
    if sov and not sov[0]['c']:
        acoes.append('TurboVenda segue sem citação nas respostas de IA: priorizar perfis em B2B Stack, Capterra, GetApp e SaaSHub.')
    if caiu and caiu[0]['anterior'] - caiu[0]['atual'] >= 5:
        acoes.append(f"Atualizar `{caiu[0]['path']}` (maior queda da semana) e reenviar pelo IndexNow.")
    if subiu and subiu[0]['atual'] - subiu[0]['anterior'] >= 5:
        acoes.append(f"Reaproveitar `{subiu[0]['path']}` (maior alta): gerar rascunhos com `growth/ferramentas/distribuicao.py`.")
    acoes.append('Publicar 1 dos rascunhos aprovados de `growth/fila-distribuicao/` no LinkedIn.')
    linhas = [f'# Relatório semanal de busca orgânica — {ini:%d/%m} a {fim - timedelta(days=1):%d/%m/%Y}', '',
              f'- **Entradas vindas de buscadores:** {atual} (semana anterior: {anterior}'
              + (f', {var:+.0%})' if var is not None else ')'),
              f"- **Cadastros:** {cad['atual']} (semana anterior: {cad['anterior']})",
              f'- **Entradas vindas de assistentes de IA:** {ia}',
              f'- **Robôs mais ativos:** {robos_txt}',
              f'- **Respostas 429 para robôs:** {bloq}']
    if sov:
        linhas.append(f"- **Share of voice em IA (rodada de {sov[0]['rodada']:%d/%m}):** citado em {sov[0]['c']} de {sov[0]['n']}")
    linhas += ['', '## O que subiu', '', '| Página | Antes | Agora |', '|---|---|---|']
    linhas += [f"| `{r['path']}` | {r['anterior']} | {r['atual']} |" for r in subiu if r['atual'] > r['anterior']] or ['| — | | |']
    linhas += ['', '## O que caiu', '', '| Página | Antes | Agora |', '|---|---|---|']
    linhas += [f"| `{r['path']}` | {r['anterior']} | {r['atual']} |" for r in caiu if r['atual'] < r['anterior']] or ['| — | | |']
    linhas += ['', '## 5 ações recomendadas', ''] + [f'{i}. {a}' for i, a in enumerate(acoes[:5], 1)]
    linhas += ['', 'Fonte: telemetria própria (`pageviews`, `users`, `share_of_voice`). '
               'Cliques, impressões e posição entram quando o Search Console estiver conectado.']
    return ini, '\n'.join(linhas) + '\n'


def salvar_relatorio_semanal(conn, hoje=None):
    cur = conn.cursor()
    criar_tabelas(cur)
    semana, md = gerar_relatorio_semanal(cur, hoje)
    cur.execute("""INSERT INTO relatorios_semanais (semana, markdown) VALUES (%s, %s)
                   ON CONFLICT (semana) DO UPDATE SET markdown = EXCLUDED.markdown, gerado_em = now()""",
                (semana, md))
    conn.commit()
    return semana, md
