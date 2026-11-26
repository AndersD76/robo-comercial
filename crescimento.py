# -*- coding: utf-8 -*-
"""Crescimento orgânico: configuração (clusters, tipos de página, eventos,
canais) e tabelas operacionais que alimentam o painel /admin/crescimento.

Tudo o que é dado operacional (mapa de buscas, fila de conteúdo, portão de
qualidade, iscas e leads, alvos de link, distribuição, anotações, linha de
base) mora no banco; nada de planilha ou relatório em arquivo.
"""
import datetime as _dt
import json
import re
from urllib.parse import urlencode, urlparse

SITE = 'https://www.turbovenda.com.br'

# ---------------------------------------------------------------------------
# Clusters de tema (os 6 primeiros são os do blog, em links_internos.py)
# ---------------------------------------------------------------------------
CLUSTERS = {
    'prospeccao': {'nome': 'Prospecção B2B', 'pilar': '/blog/como-prospectar-clientes-b2b',
                   'comercial': '/', 'isca': 'diagnostico-prospeccao'},
    'listas': {'nome': 'Listas e base de empresas', 'pilar': '/blog/base-de-dados-de-empresas-cnpj',
               'comercial': '/empresas', 'isca': 'lista-de-empresas'},
    'abordagem': {'nome': 'Abordagem e mensagens', 'pilar': '/blog/mensagem-de-prospeccao-whatsapp',
                  'comercial': '/', 'isca': 'gerador-de-mensagem'},
    'metas': {'nome': 'Metas e funil de vendas', 'pilar': '/blog/quantos-leads-preciso-para-bater-a-meta',
              'comercial': '/precos', 'isca': 'calculadora-de-meta'},
    'crm': {'nome': 'CRM e automação comercial', 'pilar': '/blog/automacao-comercial-guia-completo',
            'comercial': '/precos', 'isca': 'calculadora-roi'},
    'decisor': {'nome': 'Decisor e sócios', 'pilar': '/blog/como-encontrar-o-decisor-da-empresa',
                'comercial': '/', 'isca': 'gerador-icp'},
    'cnae': {'nome': 'CNAE e CNPJ', 'pilar': '/cnae', 'comercial': '/empresas',
             'isca': 'consulta-cnae'},
    'lgpd': {'nome': 'LGPD na prospecção', 'pilar': '/lgpd', 'comercial': '/',
             'isca': 'checklist-lgpd'},
    'ferramentas': {'nome': 'Ferramentas de prospecção', 'pilar': '/alternativas',
                    'comercial': '/precos', 'isca': 'calculadora-roi'},
    'email': {'nome': 'E-mail de prospecção', 'pilar': '/modelos', 'comercial': '/',
              'isca': 'cadencia-prospeccao'},
    'whatsapp': {'nome': 'WhatsApp para vendas', 'pilar': '/blog/whatsapp-para-vendas-b2b',
                 'comercial': '/', 'isca': 'gerador-de-mensagem'},
    'linkedin': {'nome': 'LinkedIn e social selling', 'pilar': '/glossario', 'comercial': '/',
                 'isca': 'cadencia-prospeccao'},
    'gestao': {'nome': 'Gestão comercial e indicadores', 'pilar': '/glossario', 'comercial': '/precos',
               'isca': 'calculadora-cac'},
    'setores': {'nome': 'Prospecção por setor', 'pilar': '/empresas', 'comercial': '/empresas',
                'isca': 'lista-de-empresas'},
}

# ---------------------------------------------------------------------------
# Tipos de página: prefixo da URL, JSON-LD e limite de palavras (intenção)
# ---------------------------------------------------------------------------
TIPOS_PAGINA = {
    'pilar': {'nome': 'Guia completo', 'hub': '/blog', 'schema': 'Article', 'palavras': (1800, 6000)},
    'satelite': {'nome': 'Pergunta respondida', 'hub': '/blog', 'schema': 'Article', 'palavras': (700, 3500)},
    'modelo': {'nome': 'Modelo pronto', 'hub': '/modelos', 'schema': 'Article', 'palavras': (450, 3000)},
    'glossario': {'nome': 'Glossário', 'hub': '/glossario', 'schema': 'DefinedTerm', 'palavras': (250, 1600)},
    'norma': {'nome': 'Lei explicada', 'hub': '/lgpd', 'schema': 'Article', 'palavras': (600, 3500)},
    'comparativo': {'nome': 'Comparativo', 'hub': '/alternativas', 'schema': 'Article', 'palavras': (600, 3500)},
    'ferramenta': {'nome': 'Ferramenta grátis', 'hub': '/ferramentas', 'schema': 'WebApplication', 'palavras': (150, 2500)},
    'programatica': {'nome': 'Página de dados', 'hub': '/cnae', 'schema': 'Dataset', 'palavras': (150, 4000)},
    'setor': {'nome': 'Prospecção por setor', 'hub': '/empresas', 'schema': 'Article', 'palavras': (500, 3500)},
}
PREFIXOS = {'satelite': '/blog/', 'pilar': '/blog/', 'modelo': '/modelos/', 'glossario': '/glossario/',
            'norma': '/lgpd/', 'comparativo': '/comparar/', 'programatica': '/cnae/',
            'setor': '/setores/', 'ferramenta': '/ferramentas/'}

# ---------------------------------------------------------------------------
# Taxonomia de eventos (objeto_ação). Propriedades obrigatórias de página:
# page_type, cluster, consulta_alvo, isca_id. Compra só vem do servidor.
# ---------------------------------------------------------------------------
PROPS_PAGINA = ('page_type', 'cluster', 'consulta_alvo', 'isca_id')
TAXONOMIA_EVENTOS = {
    'isca_vista': {'origem': 'navegador', 'props': PROPS_PAGINA, 'ga4_conversao': False},
    'isca_iniciada': {'origem': 'navegador', 'props': PROPS_PAGINA, 'ga4_conversao': False},
    'isca_concluida': {'origem': 'navegador', 'props': PROPS_PAGINA, 'ga4_conversao': True},
    'lead_capturado': {'origem': 'servidor', 'props': PROPS_PAGINA, 'ga4_conversao': True},
    'cta_produto_clicado': {'origem': 'navegador', 'props': PROPS_PAGINA + ('cta',), 'ga4_conversao': False},
    'paywall_viewed': {'origem': 'navegador', 'props': ('origem', 'plano'), 'ga4_conversao': False},
    'signup_completed': {'origem': 'servidor', 'props': ('plano',), 'ga4_conversao': True},
    'checkout_started': {'origem': 'servidor', 'props': ('plano', 'metodo'), 'ga4_conversao': False},
    'payment_succeeded': {'origem': 'servidor', 'props': ('plano', 'valor'), 'ga4_conversao': True},
}
EVENTOS_NAVEGADOR_CRESCIMENTO = {k for k, v in TAXONOMIA_EVENTOS.items()
                                 if v['origem'] == 'navegador' and k != 'paywall_viewed'}

# ---------------------------------------------------------------------------
# Canais: orgânico inclui buscadores e respostas de IA. Ordem importa.
# ---------------------------------------------------------------------------
CANAIS = [
    ('ia', r'(^|\.)(chatgpt\.com|chat\.openai\.com|openai\.com|perplexity\.ai|gemini\.google\.com|'
           r'bard\.google\.com|copilot\.microsoft\.com|claude\.ai|you\.com|phind\.com)$',
     r'^(chatgpt|openai|perplexity|gemini|copilot|claude)'),
    ('busca', r'(^|\.)(google\.[a-z.]+|bing\.com|duckduckgo\.com|search\.yahoo\.com|ecosia\.org|'
              r'search\.brave\.com|yandex\.[a-z]+)$', r'^(google|bing)$'),
    ('social', r'(^|\.)(linkedin\.com|lnkd\.in|facebook\.com|instagram\.com|t\.co|x\.com|twitter\.com|'
               r'youtube\.com|whatsapp\.com|wa\.me|reddit\.com)$', r'^(linkedin|facebook|instagram|youtube|whatsapp)'),
    ('email', r'(^|\.)(mail\.google\.com|outlook\.live\.com|outlook\.office\.com)$', r'^(email|newsletter|resend)'),
]
UTM_PADRAO = {'utm_source': 'origem (google, linkedin, newsletter, parceiro)',
              'utm_medium': 'organic | social | email | referral | pseo | isca',
              'utm_campaign': 'peça ou campanha (slug da página ou da isca)'}


def canal_de(referrer='', utm_source='', utm_medium=''):
    """Canal de uma visita: ia, busca, social, email, referencia ou direto."""
    us = (utm_source or '').lower()
    host = urlparse(referrer or '').netloc.lower().split(':')[0]
    if host.startswith('www.'):
        host = host[4:]
    for canal, re_host, re_utm in CANAIS:
        if (us and re.search(re_utm, us)) or (host and re.search(re_host, host)):
            return canal
    if (utm_medium or '').lower() in ('email', 'newsletter'):
        return 'email'
    if host and 'turbovenda.com.br' not in host:
        return 'referencia'
    return 'direto'


def com_utm(url, source, medium, campaign):
    sep = '&' if '?' in url else '?'
    return url + sep + urlencode({'utm_source': source, 'utm_medium': medium, 'utm_campaign': campaign})


# ---------------------------------------------------------------------------
# Tabelas
# ---------------------------------------------------------------------------
DDL = [
    """CREATE TABLE IF NOT EXISTS mapa_buscas (
        consulta TEXT PRIMARY KEY, intencao TEXT, cluster TEXT, tipo_pagina TEXT, isca TEXT,
        volume INTEGER, volume_estimado BOOLEAN DEFAULT TRUE, dificuldade SMALLINT,
        prioridade SMALLINT DEFAULT 50, fonte TEXT, pagina TEXT,
        impressoes_28d INTEGER, cliques_28d INTEGER, posicao_28d REAL,
        criado_em TIMESTAMPTZ DEFAULT now(), atualizado_em TIMESTAMPTZ DEFAULT now())""",
    "CREATE INDEX IF NOT EXISTS idx_mapa_cluster ON mapa_buscas (cluster, prioridade DESC)",
    "CREATE INDEX IF NOT EXISTS idx_mapa_pagina ON mapa_buscas (pagina)",
    """CREATE TABLE IF NOT EXISTS conteudo_paginas (
        url TEXT PRIMARY KEY, tipo TEXT NOT NULL, cluster TEXT, consulta TEXT,
        titulo TEXT, descricao TEXT, h1 TEXT, resposta TEXT, corpo TEXT,
        faq JSONB DEFAULT '[]', fontes JSONB DEFAULT '[]', extra JSONB DEFAULT '{}',
        isca TEXT, matriz TEXT, celula TEXT,
        status TEXT NOT NULL DEFAULT 'rascunho', indexavel BOOLEAN DEFAULT TRUE,
        onda BIGINT, publicado_em TIMESTAMPTZ, atualizado_em TIMESTAMPTZ DEFAULT now(),
        revisar_em DATE, origem TEXT, modelo TEXT, tokens_entrada INTEGER, tokens_saida INTEGER,
        custo_usd NUMERIC(10,4), criado_em TIMESTAMPTZ DEFAULT now())""",
    "CREATE INDEX IF NOT EXISTS idx_conteudo_tipo ON conteudo_paginas (tipo, status)",
    "CREATE INDEX IF NOT EXISTS idx_conteudo_cluster ON conteudo_paginas (cluster, status)",
    """CREATE TABLE IF NOT EXISTS conteudo_qualidade (
        id BIGSERIAL PRIMARY KEY, url TEXT NOT NULL, verificado_em TIMESTAMPTZ DEFAULT now(),
        aprovado BOOLEAN, nota SMALLINT, checks JSONB, motivo TEXT)""",
    "CREATE INDEX IF NOT EXISTS idx_qualidade_url ON conteudo_qualidade (url, verificado_em DESC)",
    """CREATE TABLE IF NOT EXISTS conteudo_ondas (
        id BIGSERIAL PRIMARY KEY, tipo TEXT NOT NULL, publicada_em TIMESTAMPTZ DEFAULT now(),
        paginas INTEGER, inspecionadas INTEGER DEFAULT 0, indexadas INTEGER DEFAULT 0,
        medida_em TIMESTAMPTZ)""",
    """CREATE TABLE IF NOT EXISTS conteudo_pausas (
        tipo TEXT PRIMARY KEY, pausado_em TIMESTAMPTZ DEFAULT now(), motivo TEXT)""",
    """CREATE TABLE IF NOT EXISTS conteudo_lotes (
        id TEXT PRIMARY KEY, criado_em TIMESTAMPTZ DEFAULT now(), status TEXT,
        pedidos INTEGER, concluidos INTEGER DEFAULT 0, falhas INTEGER DEFAULT 0,
        tokens_entrada BIGINT DEFAULT 0, tokens_saida BIGINT DEFAULT 0,
        custo_usd NUMERIC(10,4) DEFAULT 0, processado_em TIMESTAMPTZ)""",
    """CREATE TABLE IF NOT EXISTS leads_isca (
        id BIGSERIAL PRIMARY KEY, email TEXT NOT NULL, nome TEXT, empresa TEXT,
        isca TEXT NOT NULL, cluster TEXT, pagina TEXT, consulta TEXT, utm JSONB,
        first_touch JSONB, last_touch JSONB, resultado JSONB,
        opt_in_marketing BOOLEAN DEFAULT FALSE, passo_sequencia SMALLINT DEFAULT 0,
        proximo_email_em TIMESTAMPTZ, descadastrado_em TIMESTAMPTZ, user_id BIGINT,
        criado_em TIMESTAMPTZ DEFAULT now())""",
    "CREATE INDEX IF NOT EXISTS idx_leads_isca_email ON leads_isca (LOWER(email))",
    "CREATE INDEX IF NOT EXISTS idx_leads_isca_proximo ON leads_isca (proximo_email_em) WHERE descadastrado_em IS NULL",
    """CREATE TABLE IF NOT EXISTS alvos_link (
        id BIGSERIAL PRIMARY KEY, nome TEXT NOT NULL, url TEXT UNIQUE NOT NULL, tipo TEXT,
        pagina_alvo TEXT, ativo TEXT, mensagem TEXT, status TEXT DEFAULT 'novo', notas TEXT,
        atualizado_em TIMESTAMPTZ DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS pecas_offpage (
        id BIGSERIAL PRIMARY KEY, tipo TEXT NOT NULL, titulo TEXT NOT NULL, destino TEXT,
        texto TEXT NOT NULL, status TEXT DEFAULT 'pronto', criado_em TIMESTAMPTZ DEFAULT now(),
        UNIQUE (tipo, titulo))""",
    """CREATE TABLE IF NOT EXISTS fila_distribuicao (
        id BIGSERIAL PRIMARY KEY, url TEXT NOT NULL, canal TEXT NOT NULL, texto TEXT NOT NULL,
        link_utm TEXT, status TEXT DEFAULT 'rascunho', criado_em TIMESTAMPTZ DEFAULT now(),
        UNIQUE (url, canal))""",
    """CREATE TABLE IF NOT EXISTS serp_semanal (
        data DATE NOT NULL, consulta TEXT NOT NULL, resultado JSONB, ai_overview BOOLEAN,
        citados JSONB, nossa_posicao SMALLINT, PRIMARY KEY (data, consulta))""",
    """CREATE TABLE IF NOT EXISTS anotacoes (
        id BIGSERIAL PRIMARY KEY, em TIMESTAMPTZ DEFAULT now(), tipo TEXT NOT NULL,
        texto TEXT NOT NULL, ref TEXT UNIQUE)""",
    """CREATE TABLE IF NOT EXISTS linha_base (
        data DATE NOT NULL, metrica TEXT NOT NULL, valor NUMERIC, fonte TEXT,
        PRIMARY KEY (data, metrica))""",
    """CREATE TABLE IF NOT EXISTS alertas_enviados (
        chave TEXT PRIMARY KEY, enviado_em TIMESTAMPTZ DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS ga4_diario (
        data DATE NOT NULL, canal TEXT NOT NULL, pagina TEXT NOT NULL, sessoes INTEGER,
        usuarios INTEGER, conversoes INTEGER, PRIMARY KEY (data, canal, pagina))""",
    """CREATE TABLE IF NOT EXISTS cnae_ibge (
        codigo TEXT PRIMARY KEY, descricao TEXT NOT NULL, hierarquia JSONB,
        observacoes JSONB, atividades JSONB, atualizado_em TIMESTAMPTZ DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS cnae_estatisticas (
        codigo TEXT PRIMARY KEY, base_mes TEXT, dados JSONB NOT NULL,
        atualizado_em TIMESTAMPTZ DEFAULT now())""",
]


def criar_tabelas(cur):
    for sql in DDL:
        cur.execute(sql)


def anotar(cur, tipo, texto, ref=None):
    """Marca na linha do tempo do painel (deploy, onda, publicação). Com ref,
    grava uma vez só (ex.: o mesmo commit não vira duas anotações)."""
    cur.execute('INSERT INTO anotacoes (tipo, texto, ref) VALUES (%s, %s, %s) '
                'ON CONFLICT (ref) DO NOTHING', (tipo, texto[:500], ref))


def gravar_linha_base(cur, data, metricas, fonte):
    for metrica, valor in metricas.items():
        if valor is None:
            continue
        cur.execute('INSERT INTO linha_base (data, metrica, valor, fonte) VALUES (%s, %s, %s, %s) '
                    'ON CONFLICT (data, metrica) DO UPDATE SET valor = EXCLUDED.valor, fonte = EXCLUDED.fonte',
                    (data, metrica, valor, fonte))


def linha_base_hoje(cur, hoje=None):
    """Retrato do dia a partir das tabelas próprias e do Search Console."""
    hoje = hoje or _dt.date.today()
    m = {}

    def um(sql, params=()):
        try:
            cur.execute(sql, params)
            r = cur.fetchone()
            return list(r.values())[0] if isinstance(r, dict) else (r[0] if r else None)
        except Exception:
            cur.connection.rollback()
            return None

    m['gsc_cliques_28d'] = um("""SELECT COALESCE(SUM(cliques), 0) FROM busca_consultas
                                WHERE fonte = 'google' AND consulta = '*' AND data > %s""",
                             (hoje - _dt.timedelta(days=28),))
    m['gsc_impressoes_28d'] = um("""SELECT COALESCE(SUM(impressoes), 0) FROM busca_consultas
                                   WHERE fonte = 'google' AND consulta = '*' AND data > %s""",
                                (hoje - _dt.timedelta(days=28),))
    m['gsc_posicao_media_28d'] = um("""SELECT ROUND((SUM(posicao * impressoes) / NULLIF(SUM(impressoes), 0))::numeric, 2)
                                      FROM busca_consultas WHERE fonte = 'google' AND consulta = '*' AND data > %s""",
                                   (hoje - _dt.timedelta(days=28),))
    if m['gsc_cliques_28d'] is not None and m['gsc_impressoes_28d']:
        m['gsc_ctr_28d'] = round(float(m['gsc_cliques_28d']) / float(m['gsc_impressoes_28d']) * 100, 3)
    m['paginas_indexadas_gsc'] = um("""SELECT SUM(indexadas) FROM busca_sitemaps WHERE fonte = 'google'
                                      AND coletado_em = (SELECT MAX(coletado_em) FROM busca_sitemaps WHERE fonte = 'google')""")
    m['paginas_enviadas_sitemap'] = um("""SELECT SUM(enviadas) FROM busca_sitemaps WHERE fonte = 'google'
                                         AND coletado_em = (SELECT MAX(coletado_em) FROM busca_sitemaps WHERE fonte = 'google')""")
    m['visitas_organicas_28d'] = um("""SELECT COUNT(*) FROM pageviews WHERE entrada AND NOT is_bot
                                      AND created_at > now() - interval '28 days'
                                      AND referrer ~* '(^|\\.)(google|bing|duckduckgo)\\.'""")
    m['visitas_ia_28d'] = um("""SELECT COUNT(*) FROM pageviews WHERE entrada AND NOT is_bot
                               AND created_at > now() - interval '28 days'
                               AND referrer ~* 'chatgpt|openai|perplexity|copilot|gemini|claude\\.ai'""")
    m['leads_isca_28d'] = um("SELECT COUNT(*) FROM leads_isca WHERE criado_em > now() - interval '28 days'")
    m['cadastros_organicos_28d'] = um("""SELECT COUNT(*) FROM users WHERE criado_em > now() - interval '28 days'
                                        AND COALESCE(first_touch->>'ref', '') ~* '(google|bing|duckduckgo|chatgpt|perplexity|copilot|gemini)'""")
    m['vendas_organicas_28d'] = um("""SELECT COUNT(*) FROM eventos e JOIN users u ON u.id = e.user_id
                                     WHERE e.nome = 'payment_succeeded' AND e.criado_em > now() - interval '28 days'
                                     AND COALESCE(u.first_touch->>'ref', '') ~* '(google|bing|duckduckgo|chatgpt|perplexity|copilot|gemini)'""")
    m['paginas_conteudo_publicadas'] = um("SELECT COUNT(*) FROM conteudo_paginas WHERE status = 'publicada'")
    m['consultas_no_mapa'] = um('SELECT COUNT(*) FROM mapa_buscas')
    return {k: (float(v) if v is not None else None) for k, v in m.items()}


def json_ld(obj):
    """JSON-LD seguro para <script>: sem '</' que fecharia a tag."""
    return json.dumps(obj, ensure_ascii=False).replace('</', '<\\/')
