# -*- coding: utf-8 -*-
"""Mapa de buscas (tabela mapa_buscas): consultas do ICP com intenção,
cluster, tipo de página, isca e prioridade.

Fontes: consultas reais do Search Console, combinações que já têm página
(segmento × cidade, CNAE), as sementes de conteúdo e o autocomplete
(Google, com DuckDuckGo de reserva), expandido toda semana com os
modificadores de pergunta. Volume: impressões do Search Console quando há;
sem elas a prioridade é estimada e marcada como estimativa.
"""
import json
import math
import re
import time

import conteudo_motor as cm
import crescimento as cfg

SEMENTES = [
    'prospecção de clientes', 'prospecção b2b', 'como prospectar clientes', 'como conseguir clientes', 'lista de empresas',
    'base de dados de empresas', 'mailing de empresas', 'consulta cnpj', 'cnae', 'código cnae', 'empresas por cnae',
    'empresas abertas', 'gerar leads', 'leads b2b', 'leads qualificados', 'cold call', 'e-mail de prospecção',
    'cold mail', 'mensagem de prospecção', 'mensagem whatsapp vendas', 'whatsapp business vendas', 'script de vendas',
    'follow up vendas', 'cadência de prospecção', 'funil de vendas', 'pipeline de vendas', 'meta de vendas', 'cac',
    'ltv', 'taxa de conversão vendas', 'crm', 'crm para pequenas empresas', 'automação comercial', 'sdr', 'bdr',
    'pré-vendas', 'icp', 'persona b2b', 'decisor', 'sócios de empresa', 'quadro societário', 'lgpd prospecção',
    'lgpd e-mail marketing', 'legítimo interesse', 'representante comercial', 'como vender para empresas',
    'vendas b2b', 'social selling', 'linkedin vendas', 'sales navigator', 'proposta comercial', 'objeções de vendas',
    'ferramenta de prospecção', 'software de prospecção', 'econodata', 'speedio', 'apollo io', 'leads2b',
    'planilha de prospecção', 'indicadores de vendas', 'playbook de vendas', 'qualificação de leads', 'bant',
]
MODIFICADORES = ['', 'como', 'o que é', 'quanto custa', 'qual', 'quando', 'prazo', 'multa', 'obrigatório', 'exemplo',
                 'modelo', 'planilha', 'checklist', 'passo a passo', 'vs', 'melhor', 'grátis', 'pdf']
LETRAS = list('abcdefghijlmnopqrstuvz')

MARCAS = r'econodata|speedio|apollo|leads2b|agendor|rd station|pipedrive|hubspot|ploomes|meetime|turbovenda'
_REGRAS_CLUSTER = [
    ('lgpd', r'\blgpd\b|dados pessoais|\banpd\b|legitimo interesse|consentimento|protecao de dados'),
    ('cnae', r'\bcnae\b|codigo de atividade|atividade economica'),
    ('decisor', r'decisor|\bsocio|quadro societario|\bqsa\b|dono da empresa'),
    ('email', r'\be-?mail|cold mail|\bspf\b|\bdkim\b|\bdmarc\b|entregabilidade|caixa de entrada'),
    ('whatsapp', r'whatsapp|\bzap\b'),
    ('linkedin', r'linkedin|sales navigator|inmail|ligacao|cold call|telefone'),
    ('ferramentas', MARCAS + r'|\bvs\b|alternativa|software|plataforma|ferramenta|sistema de'),
    ('crm', r'\bcrm\b|automacao comercial|automacao de vendas'),
    ('metas', r'\bmeta\b|metas|funil|pipeline|forecast|conversao'),
    ('gestao', r'\bcac\b|\bltv\b|churn|indicador|\bkpi|comissao|ticket medio|\bmrr\b|\bnps\b|gestao comercial'),
    ('listas', r'lista de empresas|empresas de|empresas em|base de dados|mailing|\bcnpj\b|empresas abertas'),
    ('abordagem', r'mensagem|script|abordagem|follow ?up|objec|pitch|proposta'),
]
_ICP = r'prospec|cliente|b2b|venda|vender|empresa|lead|comercial|representante|sdr|negocio'


def normalizar(q):
    q = re.sub(r'\s+', ' ', (q or '').strip().lower())
    return q[:120]


def classificar(consulta):
    q = cm.sem_acento(normalizar(consulta))
    cluster = next((c for c, rx in _REGRAS_CLUSTER if re.search(rx, q)), 'prospeccao')
    if re.search(MARCAS, q) and not re.search(r'\bvs\b|alternativa|preco|vale a pena|ou\b', q):
        intencao = 'navegacional'
    elif re.search(r'\bvs\b|alternativa|comparativo|melhor|vale a pena|review|opiniao|preco|planos', q):
        intencao = 'comercial'
    elif re.search(r'gratis|baixar|download|comprar|contratar|teste|software|ferramenta|app\b|sistema', q):
        intencao = 'transacional'
    else:
        intencao = 'informacional'
    if re.search(r'^o que (e|sao|significa)|significado|definicao|o que quer dizer', q):
        tipo = 'glossario'
    elif re.search(r'\bcnae\b\s*\d{4}', q):
        tipo = 'programatica'
    elif re.search(r'^empresas de .+ em |^lista de empresas de .+ em ', q):
        tipo = 'programatica'
    elif re.search(r'calculadora|calcular|calculo|gerador|simulador', q):
        tipo = 'ferramenta'
    elif re.search(r'modelo|template|exemplo de|script|planilha|checklist|roteiro', q):
        tipo = 'modelo'
    elif re.search(r'\bvs\b|alternativa|melhor (ferramenta|software|crm|plataforma)|preco|vale a pena', q):
        tipo = 'comparativo'
    elif re.search(r'lgpd.*\bart', q):
        tipo = 'norma'
    else:
        tipo = 'satelite'
    return {'intencao': intencao, 'cluster': cluster, 'tipo_pagina': tipo,
            'isca': cfg.CLUSTERS.get(cluster, {}).get('isca', 'diagnostico-prospeccao')}


def prioridade(consulta, intencao, impressoes=None):
    q = cm.sem_acento(consulta.lower())
    p = 35
    p += {'transacional': 25, 'comercial': 22, 'informacional': 8, 'navegacional': -10}.get(intencao, 0)
    if re.search(_ICP, q):
        p += 15
    if impressoes:
        p += min(25, int(5 * math.log10(1 + impressoes)))
    return max(0, min(100, p))


def gravar(cur, consulta, fonte, impressoes=None, cliques=None, posicao=None, pagina=None, volume=None):
    consulta = normalizar(consulta)
    if len(consulta) < 3 or len(consulta.split()) > 12:
        return 0
    c = classificar(consulta)
    pr = prioridade(consulta, c['intencao'], impressoes)
    cur.execute("""INSERT INTO mapa_buscas (consulta, intencao, cluster, tipo_pagina, isca, volume, volume_estimado,
                       prioridade, fonte, pagina, impressoes_28d, cliques_28d, posicao_28d)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (consulta) DO UPDATE SET
                       impressoes_28d = COALESCE(EXCLUDED.impressoes_28d, mapa_buscas.impressoes_28d),
                       cliques_28d = COALESCE(EXCLUDED.cliques_28d, mapa_buscas.cliques_28d),
                       posicao_28d = COALESCE(EXCLUDED.posicao_28d, mapa_buscas.posicao_28d),
                       pagina = COALESCE(mapa_buscas.pagina, EXCLUDED.pagina),
                       prioridade = GREATEST(mapa_buscas.prioridade, EXCLUDED.prioridade),
                       atualizado_em = now()""",
                (consulta, c['intencao'], c['cluster'], c['tipo_pagina'], c['isca'], volume, volume is None, pr, fonte,
                 pagina, impressoes, cliques, posicao))
    return 1


def importar_gsc(cur, dias=90):
    """Consultas reais do Search Console (consulta × página)."""
    cur.execute("""SELECT consulta, SUM(impressoes) AS imp, SUM(cliques) AS cli,
                          SUM(posicao * impressoes) / NULLIF(SUM(impressoes), 0) AS pos,
                          (ARRAY_AGG(pagina ORDER BY impressoes DESC))[1] AS pagina
                   FROM busca_consultas WHERE fonte = 'google' AND consulta <> '*' AND data > current_date - %s
                   GROUP BY consulta""", (dias,))
    linhas = cur.fetchall()
    n = 0
    for r in linhas:
        pagina = (r['pagina'] or '').replace(cfg.SITE, '') or None
        n += gravar(cur, r['consulta'], 'gsc', int(r['imp'] or 0), int(r['cli'] or 0),
                    round(float(r['pos']), 1) if r['pos'] else None, pagina)
    return n


def importar_combinacoes(cur, pseo_urls, segmentos_por_slug, cnaes):
    """Consultas das páginas de dados que já existem (com a página ligada)."""
    n = 0
    for u in pseo_urls:
        p = u.replace(cfg.SITE, '')
        partes = p.strip('/').split('/')
        if len(partes) == 3 and partes[0] == 'empresas' and partes[1] in segmentos_por_slug:
            seg = segmentos_por_slug[partes[1]]['label'].lower()
            m = re.match(r'(.+)-([a-z]{2})$', partes[2])
            if m:
                n += gravar(cur, f'empresas de {seg} em {m.group(1).replace("-", " ")}', 'combinacao', pagina=p)
        elif len(partes) == 2 and partes[0] == 'empresas' and partes[1] in segmentos_por_slug:
            n += gravar(cur, f'lista de empresas de {segmentos_por_slug[partes[1]]["label"].lower()}', 'combinacao', pagina=p)
    for codigo, descricao in cnaes:
        n += gravar(cur, f'cnae {codigo}', 'combinacao', pagina=f'/cnae/{codigo}')
        n += gravar(cur, f'cnae {codigo[:4]}-{codigo[4]}/{codigo[5:]}', 'combinacao', pagina=f'/cnae/{codigo}')
    return n


def importar_sementes(cur, alvos):
    n = 0
    for a in alvos:
        n += gravar(cur, a['consulta'], 'semente', pagina=a['url'])
    return n


# ---------------------------------------------------------------------------
# Autocomplete (job semanal, retomável)
# ---------------------------------------------------------------------------


def _google(q, http):
    r = http.get('https://suggestqueries.google.com/complete/search',
                 params={'client': 'firefox', 'hl': 'pt-BR', 'gl': 'br', 'q': q}, timeout=10,
                 headers={'User-Agent': 'Mozilla/5.0 (compatible; TurboVendaBot/1.0; +https://www.turbovenda.com.br/sobre)'})
    if r.status_code != 200:
        raise RuntimeError(f'google {r.status_code}')
    d = json.loads(r.content.decode(r.encoding or 'latin-1', errors='replace'))
    return [s for s in d[1] if isinstance(s, str)]


def _ddg(q, http):
    r = http.get('https://duckduckgo.com/ac/', params={'q': q, 'kl': 'br-pt'}, timeout=10,
                 headers={'User-Agent': 'Mozilla/5.0 (compatible; TurboVendaBot/1.0; +https://www.turbovenda.com.br/sobre)'})
    if r.status_code != 200:
        raise RuntimeError(f'ddg {r.status_code}')
    return [x.get('phrase', '') for x in r.json() if isinstance(x, dict)]


def consultas_para_expandir():
    for s in SEMENTES:
        for mod in MODIFICADORES:
            yield (f'{mod} {s}'.strip() if mod in ('como', 'o que é', 'qual', 'quando', 'melhor', 'quanto custa')
                   else f'{s} {mod}'.strip())
        for letra in LETRAS:
            yield f'{s} {letra}'


def expandir(cur, http, limite=600, pausa=1.2, agora=None):
    """Faz até `limite` consultas ao autocomplete que não foram feitas nos
    últimos 30 dias. Devolve (pedidos, consultas novas)."""
    cur.execute('SET search_path TO public')
    cur.execute("""CREATE TABLE IF NOT EXISTS mapa_expansao (
        pedido TEXT PRIMARY KEY, feito_em TIMESTAMPTZ DEFAULT now(), sugestoes INTEGER)""")
    cur.execute("SELECT pedido FROM mapa_expansao WHERE feito_em > now() - interval '30 days'")
    feitos = {r['pedido'] for r in cur.fetchall()}
    pedidos = novos = 0
    fonte_ok = [_google, _ddg]
    for q in consultas_para_expandir():
        if q in feitos:
            continue
        if pedidos >= limite or not fonte_ok:
            break
        sugestoes = None
        while fonte_ok and sugestoes is None:
            try:
                sugestoes = fonte_ok[0](q, http)
            except Exception:
                fonte_ok.pop(0)   # bloqueou ou caiu: tenta a próxima fonte
        if sugestoes is None:
            break
        pedidos += 1
        for s in sugestoes:
            novos += gravar(cur, s, 'autocomplete')
        cur.execute("""INSERT INTO mapa_expansao (pedido, sugestoes) VALUES (%s, %s)
                       ON CONFLICT (pedido) DO UPDATE SET feito_em = now(), sugestoes = EXCLUDED.sugestoes""",
                    (q, len(sugestoes)))
        cur.connection.commit()
        time.sleep(pausa)
    return pedidos, novos


# ---------------------------------------------------------------------------
# Satélites: perguntas sem página viram alvos de conteúdo
# ---------------------------------------------------------------------------


def _parecida(a, b):
    ta, tb = set(cm.termos_da_consulta(a)), set(cm.termos_da_consulta(b))
    return bool(ta and tb) and len(ta & tb) / len(ta | tb) >= 0.6


def alvos_satelites(cur, n=200):
    """Consultas informacionais sem página, das de maior prioridade, sem
    quase-duplicatas (uma página por intenção)."""
    cur.execute("""SELECT consulta, cluster, isca, prioridade FROM mapa_buscas
                   WHERE pagina IS NULL AND tipo_pagina = 'satelite' AND intencao IN ('informacional', 'transacional')
                     AND length(consulta) >= 12
                   ORDER BY prioridade DESC, impressoes_28d DESC NULLS LAST LIMIT %s""", (n * 6,))
    escolhidas = []
    for r in cur.fetchall():
        if not re.search(_ICP, cm.sem_acento(r['consulta'])):
            continue
        if any(_parecida(r['consulta'], e['consulta']) for e in escolhidas):
            continue
        escolhidas.append(dict(r))
        if len(escolhidas) >= n:
            break
    saida = []
    for e in escolhidas:
        url = '/blog/' + cm.slugify(e['consulta'], 70)
        saida.append({'url': url, 'tipo': 'satelite', 'cluster': e['cluster'], 'consulta': e['consulta'],
                      'isca': e['isca'], 'extra': {'prioridade': int(e['prioridade'])}})
        cur.execute('UPDATE mapa_buscas SET pagina = %s WHERE consulta = %s', (url, e['consulta']))
    return saida
