# -*- coding: utf-8 -*-
"""Painel interno /admin/crescimento: SEO, GEO, conversão, filas e custos.

Cada seção é uma consulta isolada: se uma falhar (tabela ainda vazia, por
exemplo), o painel mostra as outras.
"""
import json

from flask import redirect, request

import crescimento as cfg
import conteudo_motor as cm
import iscas

ROBOS_IA = ('GPTBot', 'OAI-SearchBot', 'ChatGPT-User', 'ClaudeBot', 'Claude-SearchBot', 'Claude-User',
            'PerplexityBot', 'Perplexity-User', 'Google-Extended', 'Applebot')
CTR_ESPERADO = {1: .28, 2: .15, 3: .11, 4: .08, 5: .07, 6: .05, 7: .04, 8: .035, 9: .03, 10: .025}
_IA_REF = r"chatgpt|openai|perplexity|copilot|gemini|claude\.ai"
_BUSCA_REF = r"(^|\.)(google|bing|duckduckgo)\."


def caminho(url):
    return (url or '').replace(cfg.SITE, '').split('?')[0].split('#')[0] or '/'


def cluster_da_url(url, mapa_paginas):
    p = caminho(url)
    if p in mapa_paginas:
        return mapa_paginas[p]
    for prefixo, cl in (('/cnae', 'cnae'), ('/empresas', 'listas'), ('/lgpd', 'lgpd'), ('/alternativas', 'ferramentas'),
                        ('/comparar', 'ferramentas'), ('/glossario', 'gestao'), ('/modelos', 'abordagem'),
                        ('/dados', 'listas'), ('/para/', 'setores'), ('/setores', 'setores')):
        if p.startswith(prefixo):
            return cl
    if p.startswith('/ferramentas/'):
        isca_id = iscas.POR_SLUG.get(p.split('/')[2])
        return iscas.ISCAS[isca_id]['cluster'] if isca_id else 'ferramentas'
    if p.startswith('/blog/'):
        try:
            import links_internos
            slug = p.split('/')[2]
            for k, v in links_internos.CLUSTERS.items():
                if slug == v['pilar'] or slug in v['satelites']:
                    return k
        except Exception:
            pass
        return 'prospeccao'
    return 'marca' if p in ('/', '/precos', '/cadastro') else 'outros'


def dados_painel(c, filtro=None):
    filtro = filtro or {}
    d = {}

    def secao(nome, fn):
        try:
            d[nome] = fn()
        except Exception as e:  # tabela ainda não existe, por exemplo
            c.connection.rollback()
            d[nome] = []
            d.setdefault('_erros', []).append(f'{nome}: {type(e).__name__}')

    def todos(sql, params=()):
        c.execute(sql, params)
        return [dict(r) for r in c.fetchall()]

    onde, params = ['1=1'], []
    if filtro.get('tipo'):
        onde.append('tipo = %s')
        params.append(filtro['tipo'])
    if filtro.get('cluster'):
        onde.append('cluster = %s')
        params.append(filtro['cluster'])
    w = ' AND '.join(onde)

    secao('status', lambda: todos(f'SELECT tipo, status, COUNT(*) AS n FROM conteudo_paginas WHERE {w} '
                                  'GROUP BY 1, 2 ORDER BY 1, 2', params))
    secao('ondas', lambda: todos('SELECT * FROM conteudo_ondas ORDER BY id DESC LIMIT 15'))
    secao('pausas', lambda: todos('SELECT * FROM conteudo_pausas ORDER BY pausado_em DESC'))
    secao('indexacao', lambda: todos("""SELECT sitemap, enviadas, indexadas FROM busca_sitemaps WHERE fonte = 'gsc'
                                        AND coletado_em = (SELECT MAX(coletado_em) FROM busca_sitemaps WHERE fonte = 'gsc')
                                        ORDER BY sitemap"""))

    def mapa_paginas():
        c.execute('SELECT url, cluster FROM conteudo_paginas')
        return {r['url']: r['cluster'] for r in c.fetchall()}

    def seo_clusters():
        mp = mapa_paginas()
        c.execute("""SELECT pagina, SUM(cliques) AS cliques, SUM(impressoes) AS impressoes,
                            SUM(posicao * impressoes) / NULLIF(SUM(impressoes), 0) AS pos
                     FROM busca_consultas WHERE fonte = 'gsc' AND consulta = '*' AND data > current_date - 28
                     GROUP BY pagina""")
        por = {}
        for r in c.fetchall():
            cl = cluster_da_url(r['pagina'], mp)
            x = por.setdefault(cl, {'cluster': cl, 'paginas': 0, 'cliques': 0, 'impressoes': 0, 'pos_peso': 0.0})
            x['paginas'] += 1
            x['cliques'] += r['cliques'] or 0
            x['impressoes'] += r['impressoes'] or 0
            x['pos_peso'] += float(r['pos'] or 0) * (r['impressoes'] or 0)
        for x in por.values():
            x['ctr'] = round(100 * x['cliques'] / x['impressoes'], 2) if x['impressoes'] else 0
            x['posicao'] = round(x['pos_peso'] / x['impressoes'], 1) if x['impressoes'] else None
            x['nome'] = cfg.CLUSTERS.get(x['cluster'], {}).get('nome', x['cluster'])
        lista = sorted(por.values(), key=lambda x: -x['cliques'])
        if filtro.get('cluster'):
            lista = [x for x in lista if x['cluster'] == filtro['cluster']]
        return lista
    secao('seo_clusters', seo_clusters)
    secao('consultas_novas', lambda: todos("""SELECT consulta, SUM(impressoes) AS impressoes, SUM(cliques) AS cliques,
                                                    ROUND(AVG(posicao)::numeric, 1) AS posicao
                                             FROM busca_consultas WHERE fonte = 'gsc' AND consulta <> '*'
                                             GROUP BY consulta HAVING MIN(data) > current_date - 10
                                             ORDER BY 2 DESC LIMIT 25"""))
    secao('oportunidades', lambda: todos("""SELECT consulta, pagina, SUM(impressoes) AS impressoes, SUM(cliques) AS cliques,
                                                  ROUND((SUM(posicao * impressoes) / NULLIF(SUM(impressoes), 0))::numeric, 1) AS posicao
                                           FROM busca_consultas WHERE fonte = 'gsc' AND consulta <> '*' AND data > current_date - 28
                                           GROUP BY 1, 2 HAVING SUM(impressoes) >= 30
                                              AND SUM(posicao * impressoes) / NULLIF(SUM(impressoes), 0) BETWEEN 4 AND 15
                                           ORDER BY 3 DESC LIMIT 30"""))

    def ctr_baixo():
        c.execute("""SELECT pagina, SUM(impressoes) AS impressoes, SUM(cliques) AS cliques,
                            SUM(posicao * impressoes) / NULLIF(SUM(impressoes), 0) AS posicao
                     FROM busca_consultas WHERE fonte = 'gsc' AND consulta = '*' AND data > current_date - 28
                     GROUP BY 1 HAVING SUM(impressoes) >= 200""")
        saida = []
        for r in c.fetchall():
            pos = round(float(r['posicao'] or 99))
            esperado = CTR_ESPERADO.get(pos)
            ctr = (r['cliques'] or 0) / r['impressoes']
            if esperado and ctr < esperado / 2:
                saida.append({'pagina': caminho(r['pagina']), 'impressoes': r['impressoes'], 'ctr': round(ctr * 100, 2),
                              'esperado': round(esperado * 100, 1), 'posicao': pos})
        return sorted(saida, key=lambda x: -x['impressoes'])[:25]
    secao('ctr_baixo', ctr_baixo)
    secao('sem_impressao', lambda: todos(f"""SELECT p.url, p.tipo, p.publicado_em FROM conteudo_paginas p
                                             WHERE p.status = 'publicada' AND p.publicado_em < now() - interval '30 days'
                                               AND {w.replace('tipo', 'p.tipo').replace('cluster', 'p.cluster')}
                                               AND NOT EXISTS (SELECT 1 FROM busca_consultas b WHERE b.fonte = 'gsc'
                                                   AND b.consulta = '*' AND b.pagina = %s || p.url AND b.impressoes > 0)
                                             ORDER BY p.publicado_em LIMIT 30""", params + [cfg.SITE]))
    secao('geo_robos', lambda: todos("""SELECT path, robo, COUNT(*) AS n, MAX(created_at) AS ultimo FROM pageviews
                                        WHERE robo = ANY(%s) AND created_at > now() - interval '28 days'
                                        GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 40""", (list(ROBOS_IA),)))
    secao('geo_visitas', lambda: todos(f"""SELECT path, COUNT(*) AS n FROM pageviews WHERE entrada AND NOT is_bot
                                          AND created_at > now() - interval '28 days' AND referrer ~* '{_IA_REF}'
                                          GROUP BY 1 ORDER BY 2 DESC LIMIT 25"""))
    secao('geo_sov', lambda: todos("""SELECT rodada, COUNT(*) AS perguntas, SUM(CASE WHEN citou THEN 1 ELSE 0 END) AS citado,
                                             SUM(CASE WHEN nos_resultados THEN 1 ELSE 0 END) AS nos_resultados
                                      FROM share_of_voice GROUP BY 1 ORDER BY 1 DESC LIMIT 6"""))

    def funil_iscas():
        c.execute("""SELECT props->>'isca_id' AS isca, nome, COUNT(*) AS n FROM eventos
                     WHERE criado_em > now() - interval '28 days'
                       AND nome IN ('isca_vista', 'isca_iniciada', 'isca_concluida', 'lead_capturado', 'cta_produto_clicado')
                     GROUP BY 1, 2""")
        por = {}
        for r in c.fetchall():
            if r['isca']:
                por.setdefault(r['isca'], {})[r['nome']] = r['n']
        saida = []
        for k, v in iscas.ISCAS.items():
            if filtro.get('isca') and filtro['isca'] != k:
                continue
            x = por.get(k, {})
            vistas = x.get('isca_vista', 0)
            saida.append({'isca': k, 'nome': v['nome'], 'vistas': vistas, 'iniciadas': x.get('isca_iniciada', 0),
                          'concluidas': x.get('isca_concluida', 0), 'leads': x.get('lead_capturado', 0),
                          'cta': x.get('cta_produto_clicado', 0),
                          'conv': round(100 * x.get('lead_capturado', 0) / vistas, 1) if vistas else None})
        return sorted(saida, key=lambda x: -(x['vistas'] or 0))
    secao('funil_iscas', funil_iscas)
    secao('funil_organico', lambda: todos(f"""
        WITH v AS (SELECT COUNT(*) AS n FROM pageviews WHERE entrada AND NOT is_bot AND created_at > now() - interval '28 days'
                   AND (referrer ~* '{_BUSCA_REF}' OR referrer ~* '{_IA_REF}')),
             e AS (SELECT nome, COUNT(*) AS n FROM eventos WHERE criado_em > now() - interval '28 days' GROUP BY 1),
             u AS (SELECT COUNT(*) AS n FROM users WHERE criado_em > now() - interval '28 days'
                   AND COALESCE(first_touch->>'ref', '') ~* '(google|bing|duckduckgo|chatgpt|perplexity|copilot|gemini|claude)'),
             p AS (SELECT COUNT(DISTINCT e.user_id) AS n FROM eventos e JOIN users us ON us.id = e.user_id
                   WHERE e.nome = 'payment_succeeded' AND e.criado_em > now() - interval '28 days'
                   AND COALESCE(us.first_touch->>'ref', '') ~* '(google|bing|duckduckgo|chatgpt|perplexity|copilot|gemini|claude)')
        SELECT 'Visitas orgânicas (busca + IA)' AS etapa, (SELECT n FROM v) AS n
        UNION ALL SELECT 'Iscas vistas', COALESCE((SELECT n FROM e WHERE nome = 'isca_vista'), 0)
        UNION ALL SELECT 'Iscas concluídas', COALESCE((SELECT n FROM e WHERE nome = 'isca_concluida'), 0)
        UNION ALL SELECT 'Leads', COALESCE((SELECT n FROM e WHERE nome = 'lead_capturado'), 0)
        UNION ALL SELECT 'Cadastros orgânicos', (SELECT n FROM u)
        UNION ALL SELECT 'Pagantes orgânicos', (SELECT n FROM p)"""))
    secao('receita_cluster', lambda: receita_por_cluster(c, mapa_paginas()))
    secao('top_leads', lambda: todos("""SELECT regexp_replace(split_part(pagina, '?', 1), '^https?://[^/]+', '') AS pagina,
                                               COUNT(*) AS leads FROM leads_isca WHERE criado_em > now() - interval '90 days'
                                        GROUP BY 1 ORDER BY 2 DESC LIMIT 20"""))
    secao('top_sem_lead', lambda: todos(f"""SELECT v.path, v.n AS visitas FROM (
                                              SELECT path, COUNT(*) AS n FROM pageviews WHERE entrada AND NOT is_bot
                                              AND created_at > now() - interval '28 days' AND referrer ~* '{_BUSCA_REF}'
                                              GROUP BY 1) v
                                           WHERE NOT EXISTS (SELECT 1 FROM leads_isca l WHERE l.criado_em > now() - interval '28 days'
                                              AND regexp_replace(split_part(l.pagina, '?', 1), '^https?://[^/]+', '') = v.path)
                                           ORDER BY 2 DESC LIMIT 20"""))
    secao('revisao', lambda: todos(f"""SELECT p.url, p.tipo, p.cluster, p.titulo, p.status,
                                              (SELECT motivo FROM conteudo_qualidade q WHERE q.url = p.url
                                               ORDER BY verificado_em DESC LIMIT 1) AS motivo
                                       FROM conteudo_paginas p WHERE p.status IN ('revisao', 'rascunho')
                                         AND {w.replace('tipo', 'p.tipo').replace('cluster', 'p.cluster')}
                                       ORDER BY p.tipo = 'norma' DESC, p.atualizado_em DESC LIMIT 60""", params))
    secao('alvos', lambda: todos("SELECT * FROM alvos_link ORDER BY status = 'novo' DESC, tipo, nome LIMIT 200"))
    secao('pecas', lambda: todos('SELECT id, tipo, titulo, destino, status, LEFT(texto, 400) AS texto FROM pecas_offpage ORDER BY tipo, id'))
    secao('distribuicao', lambda: todos("""SELECT id, url, canal, status, LEFT(texto, 500) AS texto, link_utm
                                           FROM fila_distribuicao ORDER BY status = 'rascunho' DESC, criado_em DESC LIMIT 60"""))
    secao('leads', lambda: todos("""SELECT id, criado_em, email, nome, empresa, isca, cluster, opt_in_marketing, passo_sequencia,
                                           descadastrado_em, resultado->>'resumo' AS resumo,
                                           regexp_replace(split_part(pagina, '?', 1), '^https?://[^/]+', '') AS pagina
                                    FROM leads_isca ORDER BY id DESC LIMIT 50"""))
    secao('anotacoes', lambda: todos('SELECT em, tipo, texto FROM anotacoes ORDER BY em DESC LIMIT 40'))
    secao('linha_base', lambda: todos("""SELECT metrica, MIN(data) AS desde,
                                                (ARRAY_AGG(valor ORDER BY data))[1] AS inicial,
                                                (ARRAY_AGG(valor ORDER BY data DESC))[1] AS atual
                                         FROM linha_base GROUP BY 1 ORDER BY 1"""))
    secao('mapa', lambda: todos("""SELECT cluster, intencao, COUNT(*) AS consultas, COUNT(pagina) AS com_pagina
                                   FROM mapa_buscas GROUP BY 1, 2 ORDER BY 3 DESC"""))
    secao('mapa_total', lambda: todos('SELECT COUNT(*) AS n, COUNT(pagina) AS com_pagina FROM mapa_buscas'))
    secao('mapa_sem_pagina', lambda: todos("""SELECT consulta, cluster, tipo_pagina, intencao, prioridade, impressoes_28d
                                              FROM mapa_buscas WHERE pagina IS NULL ORDER BY prioridade DESC,
                                              impressoes_28d DESC NULLS LAST LIMIT 30"""))
    secao('lotes', lambda: todos('SELECT * FROM conteudo_lotes ORDER BY criado_em DESC LIMIT 15'))
    secao('custo_mes', lambda: todos("""SELECT COALESCE(SUM(custo_usd), 0) AS usd, COALESCE(SUM(concluidos), 0) AS paginas
                                        FROM conteudo_lotes WHERE criado_em >= date_trunc('month', now())"""))
    return d


def receita_por_cluster(c, mapa_paginas):
    c.execute("""SELECT us.first_touch->>'lp' AS lp_primeiro, us.last_touch->>'lp' AS lp_ultimo,
                        COALESCE((e.props->>'valor')::numeric, 0) AS valor
                 FROM eventos e JOIN users us ON us.id = e.user_id
                 WHERE e.nome = 'payment_succeeded' AND e.criado_em > now() - interval '180 days'""")
    por = {}
    for r in c.fetchall():
        for chave, lp in (('primeiro', r['lp_primeiro']), ('ultimo', r['lp_ultimo'])):
            cl = cluster_da_url(lp or '/', mapa_paginas)
            x = por.setdefault(cl, {'cluster': cl, 'primeiro': 0.0, 'ultimo': 0.0})
            x[chave] += float(r['valor'] or 0)
    return sorted(por.values(), key=lambda x: -(x['primeiro'] + x['ultimo']))


def registrar(m, consultar):
    app = m.app

    @app.route('/admin/crescimento')
    @m.admin_required
    def admin_crescimento():
        filtro = {k: request.args.get(k) for k in ('tipo', 'cluster', 'isca') if request.args.get(k)}
        dados = consultar(lambda c: dados_painel(c, filtro), {}) or {}
        return m.render_template('admin_crescimento.html', d=dados, filtro=filtro, tipos=cfg.TIPOS_PAGINA,
                                 clusters=cfg.CLUSTERS, iscas=iscas.ISCAS)

    def acao(fn):
        def gravar(c):
            fn(c)
            c.connection.commit()
        consultar(gravar)
        return redirect(request.referrer or '/admin/crescimento')

    @app.route('/admin/crescimento/pagina', methods=['POST'])
    @m.admin_required
    def admin_crescimento_pagina():
        url, op = request.form.get('url', ''), request.form.get('op', '')
        novo = {'aprovar': 'aprovada', 'recusar': 'recusada', 'despublicar': 'pausada', 'publicar': 'publicada'}.get(op)
        if not novo or not url.startswith('/'):
            return redirect('/admin/crescimento')

        def f(c):
            if novo == 'publicada':
                c.execute("""UPDATE conteudo_paginas SET status = 'publicada', publicado_em = COALESCE(publicado_em, now()),
                             atualizado_em = now() WHERE url = %s""", (url,))
            else:
                c.execute('UPDATE conteudo_paginas SET status = %s, atualizado_em = now() WHERE url = %s', (novo, url))
            cfg.anotar(c, 'revisao', f'{op}: {url}')
        return acao(f)

    @app.route('/admin/crescimento/ver')
    @m.admin_required
    def admin_crescimento_ver():
        """Prévia de uma página em revisão (não publicada)."""
        url = request.args.get('url', '')

        def ler(c):
            return cm.pagina(c, url, so_publicada=False)
        p = consultar(ler)
        if not p:
            return m.render_template('404.html'), 404
        p = dict(p)
        for k in ('faq', 'fontes', 'extra'):
            if isinstance(p.get(k), str):
                p[k] = json.loads(p[k])
        return m.render_template('admin_previa.html', p=p)

    @app.route('/admin/crescimento/onda', methods=['POST'])
    @m.admin_required
    def admin_crescimento_onda():
        return acao(lambda c: cm.publicar_onda(c, limite_total=int(request.form.get('limite') or 400)))

    @app.route('/admin/crescimento/retomar', methods=['POST'])
    @m.admin_required
    def admin_crescimento_retomar():
        tipo = request.form.get('tipo', '')
        return acao(lambda c: (c.execute('DELETE FROM conteudo_pausas WHERE tipo = %s', (tipo,)),
                               cfg.anotar(c, 'pausa', f'Tipo {tipo} retomado manualmente')))

    @app.route('/admin/crescimento/alvo', methods=['POST'])
    @m.admin_required
    def admin_crescimento_alvo():
        status = request.form.get('status', '')
        if status not in ('novo', 'contatado', 'respondeu', 'conseguido', 'recusado', 'descartado'):
            return redirect('/admin/crescimento#links')
        return acao(lambda c: c.execute('UPDATE alvos_link SET status = %s, atualizado_em = now() WHERE id = %s',
                                        (status, int(request.form.get('id') or 0))))

    @app.route('/admin/crescimento/distribuicao', methods=['POST'])
    @m.admin_required
    def admin_crescimento_distribuicao():
        status = request.form.get('status', '')
        if status not in ('rascunho', 'aprovado', 'publicado', 'descartado'):
            return redirect('/admin/crescimento#distribuicao')
        return acao(lambda c: c.execute('UPDATE fila_distribuicao SET status = %s WHERE id = %s',
                                        (status, int(request.form.get('id') or 0))))
