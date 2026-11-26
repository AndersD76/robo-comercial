# -*- coding: utf-8 -*-
"""Jobs do crescimento orgânico (uma passada por hora, trava no Postgres).

Toda hora: sequência de e-mails das iscas; lotes de IA terminados.
Diário: IBGE/CNAE (dados), sementes e mapa de buscas, geração do dia,
distribuição das páginas novas, linha de base, GA4, alertas.
Semanal: expansão do mapa pelo autocomplete (domingo), resumo por e-mail
(segunda 8h), onda de publicação e medição das ondas (segunda 9h),
envio do sitemap ao Search Console.
"""
import base64
import datetime as _dt
import json
import os
import threading
import time
from html import escape

import cnae_paginas as cnae
import conteudo_motor as cm
import crescimento as cfg
import gerador_conteudo as gen
import iscas
import mapa_buscas
import sementes_conteudo as sem
import sequencias as seq

TRAVA = 7700505        # funil 7700501, medição 7700502, IndexNow 7700503, MP 7700504
TRAVA_MAPA = 7700506
ONDA_TAMANHO = int(os.environ.get('ONDA_TAMANHO', '400'))
_estado = {'deploy_anotado': False}


def registrar(m):
    m._crescimento_passada = lambda agora=None, forcar=(): passada(m, agora, forcar)
    m._ga4_compra = lambda *a, **k: ga4_compra(m, *a, **k)
    if m.DATABASE_URL and os.environ.get('RAILWAY_ENVIRONMENT_ID'):
        threading.Thread(target=_loop, args=(m,), daemon=True).start()


def _loop(m):
    time.sleep(240)
    while True:
        try:
            passada(m)
        except Exception:
            m.logger.exception('crescimento: falha na passada')
        time.sleep(3600 - time.time() % 3600 + 120)


def agora_br():
    return _dt.datetime.utcnow() - _dt.timedelta(hours=3)


def _segmentos(m):
    return {s['slug']: s for s in m.CNAE_B2B}


def _alternativas():
    try:
        import conteudo_alternativas
        return {a['slug'].split('-')[0]: a for a in conteudo_alternativas.ALTERNATIVAS}
    except Exception:
        return {}


def _relatorio(c):
    try:
        c.execute('SELECT dados, base_mes FROM relatorio_dados ORDER BY gerado_em DESC LIMIT 1')
        r = c.fetchone()
        if r:
            d = r['dados'] if isinstance(r['dados'], dict) else json.loads(r['dados'])
            return dict(d, base_mes=r['base_mes'])
    except Exception:
        c.connection.rollback()
    return None


def passada(m, agora=None, forcar=()):
    """forcar: nomes de etapas para rodar fora do horário (ex.: {'dados', 'onda'})."""
    agora = agora or agora_br()
    forcar = set(forcar or ())
    conn = m._conn()
    try:
        c = conn.cursor()
        c.execute('SELECT pg_try_advisory_lock(%s) AS ok', (TRAVA,))
        if not c.fetchone()['ok']:
            return {'trava': False}
        feito = {}
        try:
            cfg.criar_tabelas(c)
            c.execute("""CREATE TABLE IF NOT EXISTS conteudo_execucoes (
                         etapa TEXT PRIMARY KEY, em TIMESTAMPTZ DEFAULT now(), resultado TEXT)""")
            conn.commit()
            _anotar_deploy(c)
            conn.commit()

            def etapa(nome, quando, fn):
                if nome not in forcar and not quando:
                    return
                try:
                    feito[nome] = fn()
                    c.execute("""INSERT INTO conteudo_execucoes (etapa, resultado) VALUES (%s, %s)
                                 ON CONFLICT (etapa) DO UPDATE SET em = now(), resultado = EXCLUDED.resultado""",
                              (nome, json.dumps(feito[nome], default=str, ensure_ascii=False)[:2000]))
                    conn.commit()
                except Exception:
                    conn.rollback()
                    m.logger.exception(f'crescimento: etapa {nome} falhou')

            def ultima(nome):
                c.execute('SELECT em FROM conteudo_execucoes WHERE etapa = %s', (nome,))
                r = c.fetchone()
                return r['em'] if r else None

            def nunca(nome, dias=1):
                u = ultima(nome)
                return u is None or u < _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=dias)

            link_lead = lambda i: f'{m.APP_URL}/descadastrar/{seq.token_lead(i, m.app.secret_key)}'  # noqa: E731
            etapa('sequencias', True, lambda: seq.rodar(conn, m._send_system_email, link_lead, oferta_dias=m.TRIAL_DAYS))
            c.execute("SELECT COUNT(*) AS n FROM cnae_ibge")
            ibge_vazio = c.fetchone()['n'] == 0
            etapa('ibge', nunca('ibge', 30) and (ibge_vazio or agora.hour in (3, 4, 5)), lambda: importar_ibge(c))
            etapa('dados', nunca('dados') and agora.hour >= 4, lambda: preparar_dados(m, c))
            etapa('primeira_onda', _sem_ondas(c), lambda: cm.publicar_onda(c, limite_total=ONDA_TAMANHO))
            cliente = _cliente_ia()
            if cliente:
                ctx = _contexto_fn(m, c)
                etapa('lotes', True, lambda: gen.processar_lotes(conn, cliente, ctx, _avaliador(m)))
                etapa('gerar', nunca('gerar') and agora.hour >= 10, lambda: gen.enviar_lote(conn, cliente, ctx))
                etapa('convidados', nunca('convidados') and agora.hour >= 11, lambda: artigos_convidados(c, cliente))
            etapa('distribuicao', True, lambda: distribuicao(c))
            etapa('linha_base', nunca('linha_base') and agora.hour >= 7,
                  lambda: cfg.gravar_linha_base(c, agora.date(), cfg.linha_base_hoje(c, agora.date()), 'telemetria+gsc'))
            etapa('ga4', nunca('ga4') and agora.hour >= 7, lambda: ga4_ingerir(c))
            etapa('alertas', nunca('alertas') and agora.hour >= 8, lambda: alertas(m, c))
            etapa('resumo', agora.weekday() == 0 and agora.hour >= 8 and nunca('resumo', 6), lambda: resumo_semanal(m, c))
            etapa('onda', agora.weekday() == 0 and agora.hour >= 9 and nunca('onda', 6),
                  lambda: cm.publicar_onda(c, limite_total=ONDA_TAMANHO))
            etapa('medir_ondas', nunca('medir_ondas', 6) and agora.hour >= 9, lambda: medir_ondas(c))
            etapa('sitemap_gsc', nunca('sitemap_gsc', 7) and agora.hour >= 9, lambda: enviar_sitemap_gsc())
        finally:
            conn.rollback()
            c.execute('SELECT pg_advisory_unlock(%s)', (TRAVA,))
            conn.commit()
        if agora.weekday() == 6 and 2 <= agora.hour <= 5 or 'mapa_autocomplete' in forcar:
            threading.Thread(target=expandir_mapa, args=(m,), daemon=True).start()
        return feito
    finally:
        conn.close()


def _sem_ondas(c):
    c.execute('SELECT COUNT(*) AS n FROM conteudo_ondas')
    if c.fetchone()['n']:
        return False
    c.execute("SELECT COUNT(*) AS n FROM conteudo_paginas WHERE status = 'aprovada'")
    return c.fetchone()['n'] > 0


def _anotar_deploy(c):
    if _estado['deploy_anotado']:
        return
    sha = os.environ.get('RAILWAY_GIT_COMMIT_SHA') or os.environ.get('RAILWAY_DEPLOYMENT_ID')
    if sha:
        msg = (os.environ.get('RAILWAY_GIT_COMMIT_MESSAGE') or '').splitlines()[0][:200] if os.environ.get(
            'RAILWAY_GIT_COMMIT_MESSAGE') else ''
        cfg.anotar(c, 'deploy', f'Deploy {sha[:7]}' + (f': {msg}' if msg else ''), ref=f'deploy:{sha}')
    _estado['deploy_anotado'] = True


def _cliente_ia():
    if not os.environ.get('ANTHROPIC_API_KEY'):
        return None
    try:
        import anthropic
        return anthropic.Anthropic(timeout=120.0)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Dados: IBGE, CNAE, sementes, mapa
# ---------------------------------------------------------------------------


def importar_ibge(c):
    import requests
    r = requests.get(cnae.IBGE_URL, timeout=60)
    r.raise_for_status()
    n = cnae.importar_ibge(c, r.json())
    c.connection.commit()
    return n


def paginas_cnae(c):
    """Uma linha em conteudo_paginas por célula acima do limiar (entra nas
    ondas); lastmod acompanha a atualização das estatísticas."""
    for url, total, atualizado in cnae.celulas(c):
        partes = url.strip('/').split('/')
        codigo = partes[1]
        uf = partes[2].upper() if len(partes) > 2 else None
        consulta = f'cnae {codigo}' + (f' {uf.lower()}' if uf else '')
        c.execute("""INSERT INTO conteudo_paginas (url, tipo, cluster, consulta, titulo, matriz, celula, status, origem,
                         isca, extra, atualizado_em)
                     VALUES (%s, 'programatica', 'cnae', %s, %s, %s, %s, 'aprovada', 'dados', 'consulta-cnae', %s, %s)
                     ON CONFLICT (url) DO UPDATE SET atualizado_em = GREATEST(conteudo_paginas.atualizado_em, EXCLUDED.atualizado_em),
                         extra = conteudo_paginas.extra || EXCLUDED.extra
                     RETURNING (xmax = 0) AS nova""",
                  (url, consulta, f'CNAE {cnae.formatado(codigo)}' + (f' {uf}' if uf else ''),
                   'cnae_uf' if uf else 'cnae', f'{codigo}/{uf}' if uf else codigo,
                   json.dumps({'prioridade': min(99, 30 + int(10 * __import__('math').log10(1 + total))),
                               'empresas': total}), atualizado))
        if c.fetchone()['nova']:
            # portão da página de dados: dado acima do limiar, célula única, título e descrição gerados
            cm.registrar_avaliacao(c, url, {'aprovado': True, 'nota': 100, 'motivo': '',
                                            'checks': {'dados_suficientes': True, 'celula_unica': True,
                                                       'titulo': True, 'descricao': True, 'isca': True}})
    # célula que caiu abaixo do limiar sai do índice
    validas = [u for u, _, _ in cnae.celulas(c)]
    c.execute("""UPDATE conteudo_paginas SET indexavel = FALSE WHERE tipo = 'programatica' AND matriz LIKE 'cnae%%'
                 AND NOT (url = ANY(%s))""", (validas,))
    return len(validas)


def preparar_dados(m, c):
    saida = {}
    c.execute('SELECT COUNT(*) AS n FROM cnae_estatisticas')
    if c.fetchone()['n']:
        saida['cnae'] = paginas_cnae(c)
        c.connection.commit()
    segs = list(m.CNAE_B2B)
    saida['sementes'] = sem.semear(c, segs)
    c.connection.commit()
    try:
        saida['mapa_gsc'] = mapa_buscas.importar_gsc(c)
    except Exception:
        c.connection.rollback()
    c.connection.commit()
    try:
        c.execute('SELECT codigo, descricao FROM cnae_ibge')
        cnaes = [(r['codigo'], r['descricao']) for r in c.fetchall()]
        saida['mapa_combinacoes'] = mapa_buscas.importar_combinacoes(c, m._pseo_sitemap_urls(), _segmentos(m), cnaes)
    except Exception:
        c.connection.rollback()
    saida['mapa_sementes'] = mapa_buscas.importar_sementes(c, sem.alvos(segs))
    c.connection.commit()
    c.execute("SELECT COUNT(*) AS n FROM conteudo_paginas WHERE tipo = 'satelite'")
    if c.fetchone()['n'] < 200:
        alvos = mapa_buscas.alvos_satelites(c, 200)
        saida['satelites'] = sem.semear(c, [], alvos)
    c.connection.commit()
    saida['offpage'] = semear_offpage(c)
    c.connection.commit()
    return saida


def expandir_mapa(m):
    conn = m._conn()
    try:
        c = conn.cursor()
        c.execute('SELECT pg_try_advisory_lock(%s) AS ok', (TRAVA_MAPA,))
        if not c.fetchone()['ok']:
            return
        try:
            import requests
            pedidos, novos = mapa_buscas.expandir(c, requests.Session(), limite=int(os.environ.get('MAPA_PEDIDOS', '900')))
            conn.commit()
            m.logger.info(f'crescimento: autocomplete {pedidos} pedidos, {novos} consultas')
        finally:
            conn.rollback()
            c.execute('SELECT pg_advisory_unlock(%s)', (TRAVA_MAPA,))
            conn.commit()
    except Exception:
        m.logger.exception('crescimento: expansão do mapa falhou')
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Portão (com índice e grafo do que já está no ar)
# ---------------------------------------------------------------------------


def _contexto_fn(m, c):
    segs = _segmentos(m)
    alts = _alternativas()
    rel = _relatorio(c)
    return lambda cur, alvo: sem.contexto(cur, alvo, segs, alts, rel)


def _avaliador(m):
    def avaliar(cur, pg, ctx):
        g = m._crescimento_grafo() if getattr(m, '_crescimento_grafo', None) else {}
        indice = g.get('indice')
        cur.execute("""SELECT COUNT(*) AS n FROM conteudo_paginas WHERE cluster = %s AND url <> %s
                       AND status IN ('publicada', 'aprovada') AND tipo <> 'programatica'""", (pg.get('cluster'), pg['url']))
        vizinhas = cur.fetchone()['n']
        # hub do tipo (sempre lista) + vizinhas do cluster (grafo garante 3 entradas)
        entrada = 1 + min(3, vizinhas) + (1 if pg['tipo'] in ('satelite', 'pilar') else 0)
        return cm.avaliar(pg, indice=indice, links_entrada=entrada, numeros_permitidos=sem.numeros_permitidos(ctx, pg),
                          iscas_validas=set(iscas.ISCAS), links_saida_auto=min(5, vizinhas))
    return avaliar


# ---------------------------------------------------------------------------
# Distribuição e off-page
# ---------------------------------------------------------------------------


def distribuicao(c, limite=40):
    """Cada página publicada ganha 1 post de LinkedIn e 1 roteiro de vídeo
    curto (rascunhos com UTM), para aprovação no painel."""
    c.execute("""SELECT p.url, p.h1, p.titulo, p.resposta, p.corpo, p.tipo FROM conteudo_paginas p
                 WHERE p.status = 'publicada' AND p.tipo <> 'programatica'
                   AND NOT EXISTS (SELECT 1 FROM fila_distribuicao f WHERE f.url = p.url)
                 ORDER BY p.publicado_em DESC LIMIT %s""", (limite,))
    n = 0
    for p in c.fetchall():
        import re
        topicos = [cm.texto_puro(t) for t in re.findall(r'<h2[^>]*>(.*?)</h2>', p['corpo'] or '')][:3]
        slug = cm.slugify(p['url'], 50)
        link_li = cfg.com_utm(cfg.SITE + p['url'], 'linkedin', 'social', slug)
        link_vid = cfg.com_utm(cfg.SITE + p['url'], 'video', 'social', slug)
        post = (f"{p['h1']}?\n\n{p['resposta']}\n\n" + ''.join(f'→ {t}\n' for t in topicos)
                + f'\nO passo a passo completo, com modelo e dados da Receita: {link_li}\n\n#vendasb2b #prospeccao')
        roteiro = (f"[0-3s] Gancho: \"{p['h1']}? Em 45 segundos.\"\n"
                   f"[3-15s] Resposta direta: {p['resposta']}\n"
                   + ''.join(f'[{15 + i * 8}-{23 + i * 8}s] {t}\n' for i, t in enumerate(topicos))
                   + f'[40-45s] Chamada: "O link com o modelo está na descrição."\nDescrição: {link_vid}')
        for canal, texto, link in (('linkedin', post, link_li), ('video', roteiro, link_vid)):
            c.execute("""INSERT INTO fila_distribuicao (url, canal, texto, link_utm) VALUES (%s, %s, %s, %s)
                         ON CONFLICT (url, canal) DO NOTHING""", (p['url'], canal, texto, link))
            n += c.rowcount
    return n


def semear_offpage(c):
    import offpage_sementes as off
    n = 0
    for a in off.ALVOS:
        c.execute("""INSERT INTO alvos_link (nome, url, tipo, pagina_alvo, ativo, mensagem) VALUES (%s, %s, %s, %s, %s, %s)
                     ON CONFLICT (url) DO NOTHING""",
                  (a['nome'], a['url'], a['tipo'], a['pagina'], a['ativo'], off.mensagem(a)))
        n += c.rowcount
    for p in off.DIRETORIOS:
        c.execute("""INSERT INTO pecas_offpage (tipo, titulo, destino, texto) VALUES ('diretorio', %s, %s, %s)
                     ON CONFLICT (tipo, titulo) DO NOTHING""", (p['nome'], p['url'], off.texto_diretorio(p)))
        n += c.rowcount
    return n


def artigos_convidados(c, cliente, por_vez=2):
    """10 artigos de convidado (com link de atribuição), prontos no painel."""
    import offpage_sementes as off
    c.execute("SELECT titulo FROM pecas_offpage WHERE tipo = 'artigo_convidado'")
    feitos = {r['titulo'] for r in c.fetchall()}
    faltam = [a for a in off.ARTIGOS_CONVIDADO if a['titulo'] not in feitos][:por_vez]
    n = 0
    for a in faltam:
        r = cliente.beta.messages.create(
            model=gen.MODELO, max_tokens=8000, output_config={'effort': 'medium'},
            betas=['server-side-fallback-2026-07-01'], extra_body={'fallbacks': 'default'},
            system=gen.SISTEMA.split('Regras que não podem ser quebradas:')[0]
            + 'Escreva um artigo de convidado para o veículo indicado: útil por si só, sem propaganda, com no máximo '
              'uma menção ao TurboVenda e um link de atribuição para a página indicada. Nenhum número que não esteja '
              'nos DADOS. Formato: título na primeira linha, depois o texto em parágrafos curtos. 800 a 1.100 palavras.',
            messages=[{'role': 'user', 'content': json.dumps(a, ensure_ascii=False)}])
        if r.stop_reason != 'end_turn':
            continue
        texto = ''.join(b.text for b in r.content if getattr(b, 'type', '') == 'text').strip()
        c.execute("""INSERT INTO pecas_offpage (tipo, titulo, destino, texto) VALUES ('artigo_convidado', %s, %s, %s)
                     ON CONFLICT (tipo, titulo) DO NOTHING""", (a['titulo'], a['veiculo'], texto))
        c.connection.commit()
        n += 1
    return n


# ---------------------------------------------------------------------------
# Medição: GA4, ondas, sitemap no Search Console
# ---------------------------------------------------------------------------


def _credenciais(escopos):
    from google.oauth2 import service_account
    bruto = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON_BASE64', '')
    if bruto:
        info = json.loads(base64.b64decode(bruto).decode('utf-8'))
    elif os.environ.get('GSC_CREDENCIAIS_JSON'):
        info = json.loads(os.environ['GSC_CREDENCIAIS_JSON'])
    else:
        return None
    return service_account.Credentials.from_service_account_info(info, scopes=escopos)


def ga4_ingerir(c, dias=7):
    prop = os.environ.get('GA4_PROPERTY_ID', '').strip()
    cred = _credenciais(['https://www.googleapis.com/auth/analytics.readonly']) if prop else None
    if not cred:
        return 'sem credencial'
    from googleapiclient.discovery import build
    api = build('analyticsdata', 'v1beta', credentials=cred, cache_discovery=False)
    hoje = _dt.date.today()
    corpo = {'dateRanges': [{'startDate': (hoje - _dt.timedelta(days=dias)).isoformat(), 'endDate': 'yesterday'}],
             'dimensions': [{'name': 'date'}, {'name': 'sessionDefaultChannelGroup'}, {'name': 'landingPage'}],
             'metrics': [{'name': 'sessions'}, {'name': 'totalUsers'}, {'name': 'keyEvents'}], 'limit': 100000}
    r = api.properties().runReport(property=f'properties/{prop}', body=corpo).execute()
    n = 0
    for linha in r.get('rows', []):
        d, canal, pagina = [x['value'] for x in linha['dimensionValues']]
        s, u, k = [float(x['value']) for x in linha['metricValues']]
        c.execute("""INSERT INTO ga4_diario (data, canal, pagina, sessoes, usuarios, conversoes) VALUES (%s, %s, %s, %s, %s, %s)
                     ON CONFLICT (data, canal, pagina) DO UPDATE SET sessoes = EXCLUDED.sessoes, usuarios = EXCLUDED.usuarios,
                     conversoes = EXCLUDED.conversoes""",
                  (_dt.datetime.strptime(d, '%Y%m%d').date(), canal[:60], pagina[:300], int(s), int(u), int(k)))
        n += 1
    return n


def ga4_compra(m, uid, valor, plano, transacao):
    """Compra no GA4 pelo servidor (Measurement Protocol), nunca pelo navegador."""
    segredo = os.environ.get('GA4_API_SECRET', '').strip()
    if not segredo or not m.GA_MEASUREMENT_ID:
        return False
    import requests
    try:
        r = requests.post('https://www.google-analytics.com/mp/collect',
                          params={'measurement_id': m.GA_MEASUREMENT_ID, 'api_secret': segredo}, timeout=10,
                          json={'client_id': f'{int(uid)}.servidor', 'user_id': str(int(uid)),
                                'events': [{'name': 'purchase', 'params': {
                                    'currency': 'BRL', 'value': float(valor or 0), 'transaction_id': str(transacao),
                                    'items': [{'item_id': plano, 'item_name': f'TurboVenda {plano}', 'price': float(valor or 0)}]}}]})
        return r.status_code < 300
    except Exception:
        return False


def _inspecionar():
    prop = os.environ.get('GSC_PROPRIEDADE', '').strip()
    cred = _credenciais(['https://www.googleapis.com/auth/webmasters.readonly']) if prop else None
    if not cred:
        return None
    from googleapiclient.discovery import build
    api = build('searchconsole', 'v1', credentials=cred, cache_discovery=False)

    def inspecionar(url):
        try:
            r = api.urlInspection().index().inspect(body={'inspectionUrl': cfg.SITE + url, 'siteUrl': prop}).execute()
            veredito = r['inspectionResult']['indexStatusResult'].get('verdict')
            return veredito == 'PASS'
        except Exception:
            return None
    return inspecionar


def medir_ondas(c):
    insp = _inspecionar()
    if not insp:
        return 'sem credencial'
    return cm.avaliar_ondas(c, insp)


def enviar_sitemap_gsc():
    prop = os.environ.get('GSC_PROPRIEDADE', '').strip()
    cred = _credenciais(['https://www.googleapis.com/auth/webmasters']) if prop else None
    if not cred:
        return 'sem credencial'
    from googleapiclient.discovery import build
    api = build('searchconsole', 'v1', credentials=cred, cache_discovery=False)
    api.sitemaps().submit(siteUrl=prop, feedpath=cfg.SITE + '/sitemap.xml').execute()
    return 'enviado'


# ---------------------------------------------------------------------------
# Alertas e resumo semanal
# ---------------------------------------------------------------------------


def _enviar_dono(m, c, chave, assunto, html):
    para = os.environ.get('ALERTAS_EMAIL', '').strip()
    if not para:
        return False
    c.execute('INSERT INTO alertas_enviados (chave) VALUES (%s) ON CONFLICT (chave) DO NOTHING', (chave,))
    if not c.rowcount:
        return False
    c.connection.commit()
    return m._send_system_email(para, assunto, seq._layout(assunto, html, None))


def alertas(m, c):
    hoje = _dt.date.today()
    achados = []
    import painel_crescimento as painel
    # queda de cliques > 30% por cluster, semana contra semana
    try:
        c.execute('SELECT url, cluster FROM conteudo_paginas')
        mp = {r['url']: r['cluster'] for r in c.fetchall()}
        c.execute("""SELECT pagina, SUM(CASE WHEN data > current_date - 9 THEN cliques ELSE 0 END) AS atual,
                            SUM(CASE WHEN data <= current_date - 9 THEN cliques ELSE 0 END) AS anterior
                     FROM busca_consultas WHERE fonte = 'gsc' AND consulta = '*' AND data > current_date - 16
                     GROUP BY pagina""")
        por = {}
        for r in c.fetchall():
            cl = painel.cluster_da_url(r['pagina'], mp)
            x = por.setdefault(cl, [0, 0])
            x[0] += r['atual'] or 0
            x[1] += r['anterior'] or 0
        for cl, (atual, anterior) in por.items():
            if anterior >= 20 and atual < anterior * 0.7:
                achados.append(f'Cliques do cluster {cfg.CLUSTERS.get(cl, {}).get("nome", cl)} caíram de {anterior} para {atual} '
                               '(semana contra semana).')
    except Exception:
        c.connection.rollback()
    # página prioritária desindexada (inspeção diária do Search Console)
    try:
        c.execute("""SELECT url FROM busca_inspecao WHERE coletado_em = (SELECT MAX(coletado_em) FROM busca_inspecao)
                     AND COALESCE(veredito, '') <> 'PASS'
                     AND url IN (SELECT url FROM busca_inspecao WHERE veredito = 'PASS')""")
        for r in c.fetchall():
            achados.append(f'Página prioritária fora do índice do Google: {r["url"]}')
    except Exception:
        c.connection.rollback()
    # 5xx ou noindex indevido numa amostra das publicadas
    try:
        c.execute("""SELECT url FROM conteudo_paginas WHERE status = 'publicada' AND indexavel
                     ORDER BY random() LIMIT 15""")
        cli = m.app.test_client()
        for r in c.fetchall():
            resp = cli.get(r['url'])
            corpo = resp.get_data(as_text=True)
            if resp.status_code >= 500:
                achados.append(f'Erro {resp.status_code} em {r["url"]}')
            elif resp.status_code == 200 and 'content="noindex' in corpo:
                achados.append(f'noindex indevido em {r["url"]}')
    except Exception:
        c.connection.rollback()
    # isca vista e nenhum lead em 7 dias
    try:
        c.execute("""SELECT props->>'isca_id' AS isca, SUM(CASE WHEN nome = 'isca_vista' THEN 1 ELSE 0 END) AS vistas,
                            SUM(CASE WHEN nome = 'lead_capturado' THEN 1 ELSE 0 END) AS leads
                     FROM eventos WHERE criado_em > now() - interval '7 days' AND nome IN ('isca_vista', 'lead_capturado')
                     GROUP BY 1""")
        for r in c.fetchall():
            if r['isca'] and (r['vistas'] or 0) >= 30 and not r['leads']:
                achados.append(f'Isca {iscas.ISCAS.get(r["isca"], {}).get("nome", r["isca"])}: {r["vistas"]} visualizações e '
                               'nenhum lead em 7 dias.')
    except Exception:
        c.connection.rollback()
    if achados:
        html = '<ul>' + ''.join(f'<li>{escape(a)}</li>' for a in achados) + '</ul>' \
               '<p><a href="https://www.turbovenda.com.br/admin/crescimento">Abrir o painel</a></p>'
        _enviar_dono(m, c, f'alerta:{hoje}', f'Alerta do crescimento orgânico: {len(achados)} ponto(s)', html)
    return achados


def resumo_semanal(m, c):
    hoje = _dt.date.today()
    linhas = []

    def um(sql, params=()):
        try:
            c.execute(sql, params)
            r = c.fetchone()
            return list(r.values())[0] if r else None
        except Exception:
            c.connection.rollback()
            return None
    publicadas = um("SELECT COUNT(*) AS n FROM conteudo_paginas WHERE publicado_em > now() - interval '7 days'")
    cliques = um("""SELECT COALESCE(SUM(cliques), 0) FROM busca_consultas WHERE fonte = 'gsc' AND consulta = '*'
                    AND data > current_date - 9""")
    cliques_ant = um("""SELECT COALESCE(SUM(cliques), 0) FROM busca_consultas WHERE fonte = 'gsc' AND consulta = '*'
                        AND data BETWEEN current_date - 16 AND current_date - 9""")
    leads = um("SELECT COUNT(*) FROM leads_isca WHERE criado_em > now() - interval '7 days'")
    cadastros = um("SELECT COUNT(*) FROM users WHERE criado_em > now() - interval '7 days'")
    revisao = um("SELECT COUNT(*) FROM conteudo_paginas WHERE status = 'revisao'")
    alvos_novos = um("SELECT COUNT(*) FROM alvos_link WHERE status = 'novo'")
    distrib = um("SELECT COUNT(*) FROM fila_distribuicao WHERE status = 'rascunho'")
    linhas.append(f'<p><b>Publicado na semana:</b> {publicadas or 0} páginas. <b>Cliques do Google:</b> {cliques or 0} '
                  f'(semana anterior: {cliques_ant or 0}). <b>Leads das iscas:</b> {leads or 0}. <b>Cadastros:</b> {cadastros or 0}.</p>')
    try:
        c.execute("""SELECT props->>'isca_id' AS isca, SUM(CASE WHEN nome = 'isca_vista' THEN 1 ELSE 0 END) AS vistas,
                            SUM(CASE WHEN nome = 'lead_capturado' THEN 1 ELSE 0 END) AS leads
                     FROM eventos WHERE criado_em > now() - interval '7 days' AND nome IN ('isca_vista', 'lead_capturado')
                     GROUP BY 1 HAVING SUM(CASE WHEN nome = 'isca_vista' THEN 1 ELSE 0 END) > 0 ORDER BY 3 DESC""")
        iscas_sem = c.fetchall()
        if iscas_sem:
            melhor, pior = iscas_sem[0], iscas_sem[-1]
            linhas.append(f'<p><b>Melhor isca:</b> {escape(iscas.ISCAS.get(melhor["isca"], {}).get("nome", str(melhor["isca"])))} '
                          f'({melhor["leads"]} leads em {melhor["vistas"]} visualizações). <b>Pior:</b> '
                          f'{escape(iscas.ISCAS.get(pior["isca"], {}).get("nome", str(pior["isca"])))} ({pior["leads"]} em {pior["vistas"]}).</p>')
    except Exception:
        c.connection.rollback()
    try:
        c.execute("""SELECT pagina, SUM(CASE WHEN data > current_date - 9 THEN cliques ELSE 0 END)
                          - SUM(CASE WHEN data <= current_date - 9 THEN cliques ELSE 0 END) AS dif
                     FROM busca_consultas WHERE fonte = 'gsc' AND consulta = '*' AND data > current_date - 16
                     GROUP BY 1 ORDER BY 2 DESC""")
        difs = c.fetchall()
        if difs:
            sobe = [f'{d["pagina"].replace(cfg.SITE, "")} (+{d["dif"]})' for d in difs[:3] if d['dif'] > 0]
            cai = [f'{d["pagina"].replace(cfg.SITE, "")} ({d["dif"]})' for d in difs[-3:] if d['dif'] < 0]
            if sobe:
                linhas.append('<p><b>Subiu:</b> ' + escape(', '.join(sobe)) + '</p>')
            if cai:
                linhas.append('<p><b>Caiu:</b> ' + escape(', '.join(cai)) + '</p>')
    except Exception:
        c.connection.rollback()
    acoes = []
    if revisao:
        acoes.append(f'Revisar {revisao} página(s) na fila de revisão (lei explicada e números sem fonte).')
    if alvos_novos:
        acoes.append(f'Disparar os primeiros contatos de link: {alvos_novos} alvos com mensagem pronta.')
    if distrib:
        acoes.append(f'Aprovar e publicar {distrib} post(s) de LinkedIn e roteiros de vídeo.')
    try:
        c.execute("""SELECT consulta, pagina FROM busca_consultas WHERE fonte = 'gsc' AND consulta <> '*' AND data > current_date - 28
                     GROUP BY 1, 2 HAVING SUM(impressoes) >= 50
                        AND SUM(posicao * impressoes) / NULLIF(SUM(impressoes), 0) BETWEEN 4 AND 15
                     ORDER BY SUM(impressoes) DESC LIMIT 2""")
        for r in c.fetchall():
            acoes.append(f'Reforçar {r["pagina"].replace(cfg.SITE, "")} para "{r["consulta"]}" (posição 4 a 15).')
    except Exception:
        c.connection.rollback()
    acoes.append('Conferir os leads da semana no painel e responder os que pediram contato.')
    linhas.append('<p><b>5 próximas ações</b></p><ol>' + ''.join(f'<li>{escape(a)}</li>' for a in acoes[:5]) + '</ol>')
    linhas.append('<p><a href="https://www.turbovenda.com.br/admin/crescimento">Abrir o painel</a></p>')
    html = ''.join(linhas)
    _enviar_dono(m, c, f'resumo:{hoje.isocalendar()[0]}-{hoje.isocalendar()[1]}',
                 f'Resumo semanal do crescimento orgânico ({hoje.strftime("%d/%m")})', html)
    return {'publicadas': publicadas, 'leads': leads}
