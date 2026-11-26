# -*- coding: utf-8 -*-
"""Rotas do crescimento orgânico: iscas, páginas do banco, CNAE, hubs,
institucionais, sitemaps por tipo, eventos e o painel /admin/crescimento.

Registrado no fim do app.py: `rotas_crescimento.registrar(sys.modules[__name__])`.
Recebe o módulo do app para usar _conn, render_template, limiter etc. sem
importação circular.
"""
import json
import os
import re
import threading
import time

from flask import Response, jsonify, request, session

import cnae_paginas as cnae
import conteudo_motor as cm
import crescimento as cfg
import iscas
import sequencias as seq

SITE = cfg.SITE
HUBS = {
    'glossario': ('Glossário de vendas B2B', 'Glossário de vendas B2B e prospecção',
                  'Termos de vendas B2B, prospecção, CNPJ, LGPD e gestão comercial, cada um com definição curta e '
                  'exemplo prático.'),
    'modelos': ('Modelos prontos', 'Modelos prontos de prospecção B2B',
                'Modelos de e-mail, mensagem de WhatsApp, roteiro de ligação, proposta e planilha, prontos para copiar '
                'e adaptar.'),
    'lgpd': ('LGPD na prospecção', 'LGPD na prospecção B2B, artigo por artigo',
             'O que a LGPD pede de quem prospecta empresas: cada artigo com o texto oficial, o que ele exige na prática '
             'e os erros comuns. Conteúdo informativo, não é aconselhamento jurídico.'),
    'comparar': ('Comparativos', 'Comparativos de ferramentas de prospecção',
                 'Ferramentas de prospecção e de dados de empresas lado a lado, com preços conferidos e para quem cada '
                 'uma serve melhor.'),
    'setores': ('Prospecção por setor', 'Como prospectar clientes por setor',
                'Guias de prospecção por segmento, com o total de empresas ativas na base da Receita.'),
}
TIPO_DO_HUB = {'glossario': 'glossario', 'modelos': 'modelo', 'lgpd': 'norma', 'comparar': 'comparativo',
               'setores': 'setor'}
HUB_DO_TIPO = {'glossario': ('Glossário', '/glossario'), 'modelo': ('Modelos', '/modelos'),
               'norma': ('LGPD', '/lgpd'), 'comparativo': ('Comparativos', '/comparar'),
               'setor': ('Setores', '/setores'), 'satelite': ('Blog', '/blog'), 'pilar': ('Blog', '/blog')}

_grafo_cache = {'em': 0.0, 'grafo': {}, 'titulos': {}}
_grafo_trava = threading.Lock()


def autor_env():
    nome = os.environ.get('AUTOR_NOME', '').strip()
    if not nome:
        return None
    return {'nome': nome, 'cargo': os.environ.get('AUTOR_CARGO', '').strip(),
            'linkedin': os.environ.get('AUTOR_LINKEDIN', '').strip(), 'bio': os.environ.get('AUTOR_BIO', '').strip(),
            'url': '/autor/' + cm.slugify(nome)}


def registrar(m):
    app = m.app
    render = m.render_template

    # ------------------------------------------------------------------
    # Contexto global: ID do GA4 para o _analytics.html
    # ------------------------------------------------------------------
    @app.context_processor
    def _ctx_crescimento():
        return {'ga_medicao': m.GA_MEASUREMENT_ID}

    def conn_ou_none():
        if not m.DATABASE_URL:
            return None
        try:
            return m._conn()
        except Exception:
            return None

    def consultar(fn, padrao=None):
        conn = conn_ou_none()
        if conn is None:
            return padrao
        try:
            c = conn.cursor()
            return fn(c)
        except Exception:
            m.logger.exception('crescimento: consulta falhou')
            try:
                conn.rollback()
            except Exception:
                pass
            return padrao
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Grafo de links internos (cache de 30 min)
    # ------------------------------------------------------------------
    def grafo():
        if time.time() - _grafo_cache['em'] < 1800:
            return _grafo_cache
        with _grafo_trava:
            if time.time() - _grafo_cache['em'] < 1800:
                return _grafo_cache

            def ler(c):
                c.execute("""SELECT url, tipo, cluster, titulo, LEFT(COALESCE(corpo, resposta, ''), 6000) AS texto
                             FROM conteudo_paginas WHERE status = 'publicada' AND tipo <> 'programatica'""")
                return c.fetchall()
            linhas = consultar(ler, []) or []
            ind = cm.Indice([dict(r) for r in linhas])
            _grafo_cache.update({'em': time.time(), 'grafo': ind.grafo(), 'titulos': {r['url']: r['titulo'] for r in linhas},
                                 'indice': ind})
        return _grafo_cache

    m._crescimento_grafo = grafo

    def ev_props(page_type, cluster, consulta, isca_id):
        return {'page_type': page_type, 'cluster': cluster or '', 'consulta_alvo': (consulta or '')[:120],
                'isca_id': isca_id or ''}

    def isca_ctx(isca_id):
        if isca_id not in iscas.ISCAS:
            isca_id = 'diagnostico-prospeccao'
        i = iscas.ISCAS[isca_id]
        return {'isca_id': isca_id, 'isca': i, 'isca_url': iscas.url_de(isca_id)}

    def segmentos_ctx():
        return {s['slug']: {'codigo': s['codigo'], 'label': s['label']} for s in m.CNAE_B2B}

    def contar_base(codigo, uf=None, porte=None):
        sql = "SELECT COUNT(*) AS n FROM empresas_publicas WHERE situacao = '02' AND cnae_principal = %s"
        params = [codigo]
        if uf:
            sql += ' AND uf = %s'
            params.append(uf)
        if porte:
            sql += ' AND porte = %s'
            params.append(porte)
        r = m._pseo_query(sql, tuple(params))
        return r[0]['n'] if r else None

    def iscas_ctx():
        return {'precos': {k: v['valor'] for k, v in m.MP_PLANOS.items()}, 'segmentos': segmentos_ctx(),
                'ufs': m.UF_NOMES, 'contar': contar_base,
                'buscar_cnae': lambda q, n: consultar(lambda c: cnae.buscar(c, q, n), [])}

    # ------------------------------------------------------------------
    # Iscas
    # ------------------------------------------------------------------
    @app.route('/ferramentas/planilha-de-prospeccao.csv')
    def planilha_prospeccao_csv():
        return Response(iscas.planilha_csv(), mimetype='text/csv; charset=utf-8',
                        headers={'Content-Disposition': 'attachment; filename="planilha-de-prospeccao-turbovenda.csv"'})

    @app.route('/ferramentas/<slug>')
    def ferramenta_isca(slug):
        isca_id = iscas.POR_SLUG.get(slug)
        if not isca_id or iscas.ISCAS[isca_id].get('existente'):
            return render('404.html'), 404
        isca = iscas.ISCAS[isca_id]
        params = iscas.ler_params(isca_id, request.args)
        resultado = None
        if isca.get('sempre') or params:
            resultado = iscas.calcular(isca_id, params, iscas_ctx())
        url = iscas.url_de(isca_id)
        canonical = SITE + url
        cluster = isca['cluster']
        outras = [{'nome': iscas.ISCAS[k]['nome'], 'url': iscas.url_de(k)} for k in iscas.ISCAS if k != isca_id][:8]
        ld = [cfg.json_ld({'@context': 'https://schema.org', '@type': 'WebApplication', 'name': isca['nome'],
                           'url': canonical, 'description': isca['descricao'],
                           'applicationCategory': 'BusinessApplication', 'operatingSystem': 'Web',
                           'inLanguage': 'pt-BR', 'offers': {'@type': 'Offer', 'price': '0', 'priceCurrency': 'BRL'},
                           'publisher': {'@type': 'Organization', 'name': 'TurboVenda', '@id': SITE + '/#organization'}}),
              cfg.json_ld({'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': [
                  {'@type': 'ListItem', 'position': 1, 'name': 'Início', 'item': SITE + '/'},
                  {'@type': 'ListItem', 'position': 2, 'name': 'Ferramentas grátis', 'item': SITE + '/ferramentas'},
                  {'@type': 'ListItem', 'position': 3, 'name': isca['nome'], 'item': canonical}]})]
        # resultado com parâmetros: a página canônica é a ferramenta vazia
        robots = 'noindex, follow' if (params and not isca.get('sempre')) else 'index, follow'
        return render('isca.html', isca=isca, isca_id=isca_id, params=params, resultado=resultado, url=url,
                      titulo=isca['titulo'], descricao=isca['descricao'], canonical=canonical, robots_meta=robots,
                      ld_json=ld, cta=iscas.cta(isca_id), segmentos=m.CNAE_B2B,
                      ufs=sorted(m.UF_NOMES.items(), key=lambda x: x[1]), outras=outras,
                      pilar=cfg.CLUSTERS.get(cluster, {}).get('pilar'), cluster_nome=cfg.CLUSTERS.get(cluster, {}).get('nome', ''),
                      ev=ev_props('isca', cluster, isca['h1'], isca_id))

    @app.route('/api/isca/<isca_id>/lead', methods=['POST'])
    @m.limiter.limit('8 per hour', key_func=m._ip_cliente)
    def api_isca_lead(isca_id):
        if isca_id not in iscas.ISCAS:
            return jsonify({'erro': 'Ferramenta não encontrada.'}), 404
        d = request.get_json(silent=True) or {}
        email = str(d.get('email') or '').strip()
        if not seq.EMAIL_OK.match(email):
            return jsonify({'erro': 'Confira o e-mail.'}), 400
        isca = iscas.ISCAS[isca_id]
        params = iscas.ler_params(isca_id, d.get('params') or {})
        resultado = iscas.calcular(isca_id, params, iscas_ctx()) if isca.get('calcular') else None
        if isca.get('calcular') and not resultado:
            return jsonify({'erro': 'Preencha a ferramenta antes de pedir o resultado.'}), 400
        resultado = resultado or {'resumo': isca['nome'], 'tela': '', 'completo': ''}
        ft, lt = m._toques_do_visitante()
        ref = request.headers.get('Referer', '')
        dados = {'email': email, 'nome': str(d.get('nome') or '').strip()[:120],
                 'empresa': str(d.get('empresa') or '').strip()[:160], 'isca': isca_id, 'cluster': isca.get('cluster'),
                 'pagina': ref[:300], 'consulta': str(d.get('consulta') or '')[:200],
                 'utm': {k: (lt or {}).get(abrev) or '' for k, abrev in
                         (('utm_source', 'us'), ('utm_medium', 'um'), ('utm_campaign', 'uc'))},
                 'first_touch': ft, 'last_touch': lt, 'opt_in': bool(d.get('opt_in')),
                 'resultado': {'resumo': resultado.get('resumo'), 'dados': resultado.get('dados'), 'params': params},
                 'user_id': session.get('user_id')}

        def gravar(c):
            cfg.criar_tabelas(c)
            lead_id = seq.registrar(c, dados)
            c.connection.commit()
            return lead_id
        lead_id = consultar(gravar)
        if not lead_id:
            return jsonify({'erro': 'Não deu certo agora. Tente de novo em instantes.'}), 503
        link = f'{m.APP_URL}/descadastrar/{seq.token_lead(lead_id, m.app.secret_key)}'
        assunto, html = seq.email_resultado(isca_id, resultado, link, m.TRIAL_DAYS)
        threading.Thread(target=m._send_system_email, args=(email, assunto, html), daemon=True).start()
        dono = os.environ.get('ALERTAS_EMAIL', '').strip()
        if dono:
            a, h = seq.alerta_dono(lead_id, dados)
            threading.Thread(target=m._send_system_email, args=(dono, a, h), daemon=True).start()
        m._evento('lead_capturado', session.get('user_id'), page_type='isca', cluster=isca.get('cluster') or '',
                  consulta_alvo=dados['consulta'], isca_id=isca_id, opt_in=dados['opt_in'])
        return jsonify({'ok': True})

    # ------------------------------------------------------------------
    # CNAE
    # ------------------------------------------------------------------
    def faq_cnae(d, total, uf=None):
        onde = m.no_uf(uf) if uf else 'no Brasil'
        n = f'{total:,}'.replace(',', '.')
        return [
            {'pergunta': f'O que significa o CNAE {d["formatado"]}?',
             'resposta': f'É a subclasse da CNAE (IBGE) para {d["nome"].lower()}. O código aparece no cartão CNPJ como '
                         'atividade principal ou secundária.'},
            {'pergunta': f'Quantas empresas têm o CNAE {d["formatado"]} {onde}?',
             'resposta': f'Na base da Receita Federal{(" de " + d["base_mes"]) if d.get("base_mes") else ""}, {n} empresas '
                         f'ativas com telefone ou e-mail público têm esse código como atividade principal {onde}.'},
            {'pergunta': 'Como conseguir a lista dessas empresas?',
             'resposta': 'O TurboVenda monta a lista com telefone, e-mail e sócio a partir da base da Receita e faz o '
                         'primeiro contato. Dá para testar grátis.'},
        ]

    def render_cnae(codigo, uf=None):
        codigo = re.sub(r'\D', '', codigo or '')
        if len(codigo) != 7:
            return render('404.html'), 404
        uf = (uf or '').upper() or None
        if uf and uf not in m.UF_NOMES:
            return render('404.html'), 404
        d = consultar(lambda c: cnae.dados(c, codigo, uf))
        if not d:
            return render('404.html'), 404
        url = f'/cnae/{codigo}' + (f'/{uf.lower()}' if uf else '')
        publicada = consultar(lambda c: bool(cm.pagina(c, url)), False)
        total = d.get('total_uf') if uf else d['total']
        indexa = cnae.indexavel(d, uf) and publicada
        nome = d['nome']
        if uf:
            h1 = f'CNAE {d["formatado"]} {m.no_uf(uf)}: {nome}'
            titulo = m._cabe([f'CNAE {d["formatado"]} {m.no_uf(uf)}: {total:,} empresas'.replace(',', '.'),
                              f'CNAE {d["formatado"]} {uf}: {total:,} empresas'.replace(',', '.')])
            resposta = (f'O CNAE {d["formatado"]} é {nome.lower()}. {m.no_uf(uf).capitalize()} há '
                        f'{total:,}'.replace(',', '.') + ' empresas ativas com telefone ou e-mail público com esse código '
                        'como atividade principal, segundo a base da Receita Federal. Abaixo estão as cidades com mais '
                        'empresas, o porte e o ano de abertura.')
        else:
            h1 = f'CNAE {d["formatado"]}: {nome}'
            titulo = m._cabe([f'CNAE {d["formatado"]}: {nome}', f'CNAE {d["formatado"]}: o que é e empresas ativas',
                              f'CNAE {d["formatado"]}'])
            resposta = (f'O CNAE {d["formatado"]} é a subclasse do IBGE para {nome.lower()}. Na base da Receita Federal há '
                        f'{total:,}'.replace(',', '.') + ' empresas ativas com telefone ou e-mail público com esse código '
                        'como atividade principal. Veja o que a atividade inclui, os estados e as cidades com mais empresas.')
        descricao = m._cortar(f'CNAE {d["formatado"]}: {nome.lower()}. {total:,}'.replace(',', '.')
                              + ' empresas ativas com contato' + (f' {m.no_uf(uf)}' if uf else '')
                              + ', por estado, cidade, porte e ano. Dados da Receita e do IBGE.', 155)
        canonical = SITE + url
        migalhas = [('Início', '/'), ('CNAE', '/cnae')] + ([(d['formatado'], f'/cnae/{codigo}')] if uf else []) + \
                   [(m.UF_NOMES[uf] if uf else d['formatado'], url)]
        faq = faq_cnae(d, total, uf)
        lds = [cfg.json_ld({'@context': 'https://schema.org', '@type': 'Dataset', 'name': h1[:110],
                            'description': descricao, 'url': canonical, 'inLanguage': 'pt-BR',
                            'isAccessibleForFree': True, 'license': 'https://www.gov.br/receitafederal',
                            'creator': {'@type': 'Organization', 'name': 'TurboVenda', '@id': SITE + '/#organization'},
                            'isBasedOn': [cnae.IBGE_FONTE['url'], cnae.RECEITA_FONTE['url']],
                            'spatialCoverage': m.UF_NOMES[uf] if uf else 'Brasil',
                            'variableMeasured': 'Empresas ativas com telefone ou e-mail público'}),
               cfg.json_ld({'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': [
                   {'@type': 'ListItem', 'position': i + 1, 'name': n, 'item': SITE + l}
                   for i, (n, l) in enumerate(migalhas)]}),
               cfg.json_ld({'@context': 'https://schema.org', '@type': 'FAQPage', 'mainEntity': [
                   {'@type': 'Question', 'name': f['pergunta'], 'acceptedAnswer': {'@type': 'Answer', 'text': f['resposta']}}
                   for f in faq]})]
        ctx = isca_ctx('consulta-cnae')
        return render('cnae.html', d=d, uf=uf, uf_nome=m.UF_NOMES.get(uf, ''), total=total or 0, h1=h1,
                      resposta=resposta, titulo=titulo, descricao=descricao, canonical=canonical,
                      robots_meta='index, follow' if indexa else 'noindex, follow', ld_json=lds, faq=faq,
                      relacionados=consultar(lambda c: cnae.relacionados(c, d), []) if not uf else [],
                      portes=cnae.PORTES, ufs_nomes=m.UF_NOMES, limiar_uf=cnae.LIMIAR_CNAE_UF,
                      fonte_ibge=cnae.IBGE_FONTE, fonte_receita=cnae.RECEITA_FONTE,
                      ev=ev_props('programatica', 'cnae', h1, ctx['isca_id']), **ctx)

    @app.route('/cnae/<codigo>')
    def pagina_cnae(codigo):
        return render_cnae(codigo)

    @app.route('/cnae/<codigo>/<uf>')
    def pagina_cnae_uf(codigo, uf):
        return render_cnae(codigo, uf)

    def publicadas_urls(c, prefixo):
        c.execute("SELECT url FROM conteudo_paginas WHERE status = 'publicada' AND url LIKE %s", (prefixo + '%',))
        return {r['url'] for r in c.fetchall()}

    @app.route('/cnae')
    def cnae_hub():
        secoes = consultar(cnae.secoes, []) or []
        pub = consultar(lambda c: publicadas_urls(c, '/cnae/'), set()) or set()
        grupos = []
        for s in secoes:
            itens = [{'url': f"/cnae/{i['codigo']}", 'titulo': f"{i['formatado']} · {i['nome'][:70]}"}
                     for i in s['itens'] if f"/cnae/{i['codigo']}" in pub][:15]
            if itens:
                itens.append({'url': f"/cnae/secao/{s['id'].lower()}", 'titulo': f'Todos os códigos da seção {s["id"]} →'})
                grupos.append({'id': s['id'], 'nome': f"{s['id']} · {s['nome']}", 'itens': itens})
        return render('conteudo_hub.html', hub_id='cnae', hub_nome='CNAE', h1='CNAE: códigos, descrição e empresas ativas',
                      intro='Todas as subclasses da CNAE do IBGE, com a descrição oficial e quantas empresas ativas com '
                            'contato usam cada código como atividade principal, pela base da Receita Federal.',
                      grupos=grupos, titulo='CNAE: lista de códigos, descrição e empresas ativas',
                      descricao='Consulte os códigos CNAE com a descrição oficial do IBGE e o total de empresas ativas '
                                'com contato em cada um, por estado e cidade.',
                      canonical=SITE + '/cnae', ld_json=[])

    @app.route('/cnae/secao/<letra>')
    def cnae_secao(letra):
        letra = (letra or '').upper()[:1]
        secoes = consultar(cnae.secoes, []) or []
        s = next((x for x in secoes if (x['id'] or '') == letra), None)
        if not s:
            return render('404.html'), 404
        pub = consultar(lambda c: publicadas_urls(c, '/cnae/'), set()) or set()
        itens = [{'url': f"/cnae/{i['codigo']}", 'titulo': f"{i['formatado']} · {i['nome'][:80]}"}
                 for i in s['itens'] if f"/cnae/{i['codigo']}" in pub]
        return render('conteudo_hub.html', hub_id='cnae-' + letra.lower(), hub_nome=f'CNAE seção {letra}',
                      h1=f'CNAE seção {letra}: {s["nome"]}',
                      intro=f'Subclasses da seção {letra} da CNAE ({s["nome"].lower()}), da que tem mais empresas ativas '
                            'com contato para a que tem menos.',
                      grupos=[{'id': letra, 'nome': s['nome'], 'itens': itens}] if itens else [],
                      titulo=m._cabe([f'CNAE seção {letra}: {s["nome"]}', f'CNAE seção {letra}']),
                      descricao=m._cortar(f'Lista dos códigos CNAE da seção {letra} ({s["nome"].lower()}), com descrição '
                                          'oficial e empresas ativas.', 155),
                      canonical=SITE + f'/cnae/secao/{letra.lower()}', ld_json=[],
                      robots_meta='index, follow' if itens else 'noindex, follow')

    # ------------------------------------------------------------------
    # Páginas do banco (glossário, modelos, LGPD, comparativos, setores, blog)
    # ------------------------------------------------------------------
    def render_pagina(url):
        p = consultar(lambda c: cm.pagina(c, url))
        if not p:
            return None
        p = dict(p)
        for k in ('faq', 'fontes', 'extra'):
            if isinstance(p.get(k), str):
                p[k] = json.loads(p[k])
        corpo, sumario = cm.com_ancoras(p.get('corpo') or '')
        corpo_1, corpo_2 = cm.dividir_no_meio(corpo)
        g = grafo()
        relacionados = [{'url': u, 'titulo': g['titulos'].get(u, u)} for u in g['grafo'].get(url, [])][:6]
        hub = HUB_DO_TIPO.get(p['tipo'])
        migalhas = [('Início', '/')] + ([hub] if hub else []) + [((p.get('h1') or p['titulo'])[:60], url)]
        autor = autor_env()
        cluster = p.get('cluster') or 'prospeccao'
        info = cfg.CLUSTERS.get(cluster, cfg.CLUSTERS['prospeccao'])
        ctx = isca_ctx(p.get('isca') or info['isca'])
        comercial = cfg.com_utm("/cadastro", 'site', 'organic', f"{p['tipo']}-{cm.slugify(url, 40)}")
        return render('conteudo.html', p=p, corpo_1=corpo_1, corpo_2=corpo_2, sumario=sumario, migalhas=migalhas,
                      relacionados=relacionados, hub=hub, autor=autor, titulo=p['titulo'], descricao=p['descricao'],
                      canonical=SITE + url, robots_meta='index, follow' if p.get('indexavel', True) else 'noindex, follow',
                      ld_json=cm.ld_pagina(p, autor, migalhas),
                      comercial_texto=f'O TurboVenda encontra as empresas certas e faz o primeiro contato. {info["nome"]} '
                                      'sem trabalho manual.',
                      comercial_link=comercial, ev=ev_props(p['tipo'], cluster, p.get('consulta'), ctx['isca_id']), **ctx)

    m._render_pagina_conteudo = render_pagina

    def rota_hub(hub_id):
        nome, h1, intro = HUBS[hub_id]
        tipo = TIPO_DO_HUB[hub_id]
        linhas = consultar(lambda c: cm.publicadas(c, tipo=tipo), []) or []
        grupos = {}
        for r in linhas:
            if hub_id == 'glossario':
                chave = cm.sem_acento((r['titulo'] or '?')[:1]).upper()
                nome_g = chave
            else:
                chave = r['cluster'] or 'geral'
                nome_g = cfg.CLUSTERS.get(chave, {}).get('nome', 'Geral')
            grupos.setdefault(chave, {'id': cm.slugify(chave) or 'x', 'nome': nome_g, 'itens': []})['itens'].append(
                {'url': r['url'], 'titulo': (r.get('extra') or {}).get('termo') if isinstance(r.get('extra'), dict)
                 and (r.get('extra') or {}).get('termo') else r['titulo']})
        lista = [grupos[k] for k in sorted(grupos)]
        return render('conteudo_hub.html', hub_id=hub_id, hub_nome=nome, h1=h1, intro=intro, grupos=lista,
                      titulo=m._cabe([h1, nome]), descricao=m._cortar(intro, 155), canonical=SITE + '/' + hub_id,
                      ld_json=[], robots_meta='index, follow' if lista else 'noindex, follow')

    for _hub in HUBS:
        def _rota_hub(_h=_hub):
            return rota_hub(_h)

        def _rota_pagina(slug, _h=_hub):
            r = render_pagina(f'/{_h}/{slug}')
            return r if r is not None else (render('404.html'), 404)
        app.add_url_rule(f'/{_hub}', f'hub_{_hub}', _rota_hub)
        app.add_url_rule(f'/{_hub}/<slug>', f'pagina_{_hub}', _rota_pagina)

    # ------------------------------------------------------------------
    # Institucionais
    # ------------------------------------------------------------------
    def trilha(*itens):
        return cfg.json_ld({'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': [
            {'@type': 'ListItem', 'position': i + 1, 'name': n, 'item': SITE + l} for i, (n, l) in enumerate(itens)]})

    @app.route('/sobre')
    def sobre():
        cnpj = os.environ.get('MARCA_CNPJ', '').strip()
        return render('sobre.html', razao_social='ANDERS CONSULTORIA EM GESTAO EMPRESARIAL LTDA (AndersTech)',
                      cnpj=cnpj, cidade='Passo Fundo/RS', titulo='Sobre o TurboVenda: quem somos e de onde vêm os dados',
                      descricao='O TurboVenda é um software brasileiro de prospecção B2B da AndersTech, de Passo Fundo/RS. '
                                'Veja de onde vêm os dados e como falar conosco.',
                      canonical=SITE + '/sobre',
                      ld_json=[trilha(('Início', '/'), ('Sobre', '/sobre')), cfg.json_ld({'@context': 'https://schema.org', '@type': 'AboutPage', 'url': SITE + '/sobre',
                                            'mainEntity': {'@type': 'Organization', '@id': SITE + '/#organization',
                                                           'name': 'TurboVenda', 'legalName': 'ANDERS CONSULTORIA EM GESTAO EMPRESARIAL LTDA',
                                                           'taxID': cnpj or None, 'email': 'suporte@turbovenda.com.br',
                                                           'address': {'@type': 'PostalAddress', 'addressLocality': 'Passo Fundo',
                                                                       'addressRegion': 'RS', 'addressCountry': 'BR'}}})])

    @app.route('/politica-editorial')
    def politica_editorial():
        return render('politica_editorial.html', titulo='Política editorial do TurboVenda: como produzimos o conteúdo',
                      descricao='Como o TurboVenda produz, verifica e corrige o conteúdo do site: dados oficiais, uso de IA, '
                                'revisão humana e o que não publicamos.',
                      canonical=SITE + '/politica-editorial',
                      ld_json=[trilha(('Início', '/'), ('Sobre', '/sobre'), ('Política editorial', '/politica-editorial'))])

    @app.route('/autor/<slug>')
    def autor_pagina(slug):
        a = autor_env()
        if not a or a['url'] != f'/autor/{slug}':
            return render('404.html'), 404
        ld = {'@context': 'https://schema.org', '@type': 'ProfilePage', 'mainEntity': {
            '@type': 'Person', 'name': a['nome'], 'jobTitle': a['cargo'] or None, 'description': a['bio'] or None,
            'sameAs': [a['linkedin']] if a['linkedin'] else None,
            'worksFor': {'@type': 'Organization', '@id': SITE + '/#organization'}}}
        return render('autor.html', a=a, titulo=m._cabe([f'{a["nome"]}, {a["cargo"]} no TurboVenda', a['nome']]),
                      descricao=m._cortar(a['bio'] or f'{a["nome"]} escreve sobre prospecção B2B no TurboVenda.', 155),
                      canonical=SITE + a['url'], ld_json=[cfg.json_ld(ld)])

    # ------------------------------------------------------------------
    # Sitemaps por tipo (lastmod real) e o que o IndexNow avisa
    # ------------------------------------------------------------------
    CNAE_POR_SITEMAP = 5000

    def urls_crescimento():
        """[(url absoluta, lastmod, tipo)] de tudo que é indexável e publicado."""
        def ler(c):
            c.execute("""SELECT url, tipo, atualizado_em FROM conteudo_paginas
                         WHERE status = 'publicada' AND indexavel ORDER BY url""")
            return c.fetchall()
        linhas = consultar(ler, []) or []
        saida = [(SITE + r['url'], r['atualizado_em'].date().isoformat() if r['atualizado_em'] else None, r['tipo'])
                 for r in linhas]
        hoje = None
        for k in iscas.NOVAS:
            saida.append((SITE + iscas.url_de(k), hoje, 'ferramenta'))
        for extra in ('/sobre', '/politica-editorial'):
            saida.append((SITE + extra, None, 'institucional'))
        tipos = {r['tipo'] for r in linhas}
        for hub, tipo in TIPO_DO_HUB.items():
            if tipo in tipos:
                saida.append((SITE + '/' + hub, None, 'hub'))
        if 'programatica' in tipos:
            saida.append((SITE + '/cnae', None, 'hub'))
        a = autor_env()
        if a:
            saida.append((SITE + a['url'], None, 'institucional'))
        return saida

    m._urls_crescimento = urls_crescimento

    def urlset(itens):
        return m._render_urlset([(u, lm, 'monthly', '0.6') for u, lm, _ in itens])

    @app.route('/sitemap-conteudo.xml')
    def sitemap_conteudo():
        return urlset([x for x in urls_crescimento() if x[2] != 'programatica'])

    @app.route('/sitemap-cnae-<int:n>.xml')
    def sitemap_cnae(n):
        cn = [x for x in urls_crescimento() if x[2] == 'programatica']
        parte = cn[(n - 1) * CNAE_POR_SITEMAP: n * CNAE_POR_SITEMAP]
        if n < 1 or not parte:
            return render('404.html'), 404
        return urlset(parte)

    def sitemaps_extras():
        cn = sum(1 for x in urls_crescimento() if x[2] == 'programatica')
        nomes = ['sitemap-conteudo.xml'] + [f'sitemap-cnae-{i}.xml' for i in range(1, (cn + CNAE_POR_SITEMAP - 1)
                                                                                     // CNAE_POR_SITEMAP + 1)]
        return [f'{SITE}/{x}' for x in nomes]

    m._sitemaps_crescimento = sitemaps_extras

    # ------------------------------------------------------------------
    # Eventos do navegador (lista fechada, propriedades conferidas)
    # ------------------------------------------------------------------
    TIPOS_VALIDOS = set(cfg.TIPOS_PAGINA) | {'isca', 'blog', 'pseo', 'hub'}

    def props_evento(p):
        p = p if isinstance(p, dict) else {}
        saida = {}
        if p.get('page_type') in TIPOS_VALIDOS:
            saida['page_type'] = p['page_type']
        if p.get('cluster') in cfg.CLUSTERS:
            saida['cluster'] = p['cluster']
        if p.get('isca_id') in iscas.ISCAS:
            saida['isca_id'] = p['isca_id']
        for k, lim in (('consulta_alvo', 120), ('cta', 60), ('origem', 40)):
            if p.get(k):
                saida[k] = str(p[k])[:lim]
        return saida

    m._props_evento_crescimento = props_evento

    def blog_do_banco():
        def ler(c):
            c.execute("""SELECT url, titulo FROM conteudo_paginas WHERE status = 'publicada' AND indexavel
                         AND tipo IN ('pilar', 'satelite') ORDER BY tipo = 'pilar' DESC, publicado_em DESC LIMIT 400""")
            return [dict(r) for r in c.fetchall()]
        return consultar(ler, []) or []

    m._crescimento_blog = blog_do_banco

    # ------------------------------------------------------------------
    # Painel
    # ------------------------------------------------------------------
    import painel_crescimento
    painel_crescimento.registrar(m, consultar)
