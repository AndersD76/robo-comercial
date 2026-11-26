# -*- coding: utf-8 -*-
"""O que produzir (alvos 'pendente' em conteudo_paginas) e o contexto de
cada alvo para o gerador: DADOS (da base da Receita, do IBGE, da LGPD, dos
comparativos conferidos), FONTES e LINKS internos permitidos.
"""
import json

import cnae_paginas as cnae
import conteudo_motor as cm
import crescimento as cfg
import iscas
import lgpd_textos

# ---------------------------------------------------------------------------
# Glossário (300 termos) por cluster
# ---------------------------------------------------------------------------
_G = {
    'prospeccao': '''prospecção ativa|prospecção passiva|prospecção outbound|inbound sales|outbound sales|cold call|cold mail|
social selling|SDR|BDR|closer|hunter|farmer|pré-vendas|lead|prospect|suspect|ICP|persona de vendas|conta-alvo|
account-based marketing (ABM)|lista de prospecção|cadência de prospecção|follow-up|toque de prospecção|gatekeeper|decisor|
influenciador de compra|champion|rapport|pitch de vendas|elevator pitch|script de vendas|playbook de vendas|objeção de vendas|
quebra de objeção|qualificação de leads|BANT|GPCTBA/C&I|SPIN Selling|MEDDIC|CHAMP|ANUM|lead scoring|MQL|SQL|SAL|PQL|
nutrição de leads|warm call|lead frio|lead quente|prospecção por indicação|networking comercial|reunião de descoberta|
demonstração de produto|no-show|proposta comercial|fechamento de vendas|venda consultiva|venda transacional|venda complexa|
ciclo de vendas|prospecção multicanal|sales engagement|sequência de vendas|automação de prospecção|enriquecimento de dados|
higienização de base|deduplicação de leads|prospecção digital|prospecção por telefone|visita comercial|comitê de compra''',
    'listas': '''CNPJ|CNPJ básico|matriz e filial|razão social|nome fantasia|natureza jurídica|MEI|microempresa (ME)|
empresa de pequeno porte (EPP)|porte da empresa|capital social|quadro de sócios (QSA)|sócio-administrador|situação cadastral|
empresa ativa|empresa baixada|empresa inapta|empresa suspensa|data de abertura da empresa|inscrição estadual|inscrição municipal|
Simples Nacional|Lucro Presumido|Lucro Real|dados abertos do CNPJ|Redesim|junta comercial|alvará de funcionamento|cartão CNPJ|
consulta CNPJ|mailing de empresas|base de dados de empresas|lista de empresas|segmentação geográfica|segmentação por porte|
dados firmográficos|lookalike de clientes|matriz CNPJ|estabelecimento|código de município''',
    'cnae': '''CNAE|CNAE principal|CNAE secundário|subclasse CNAE|classe CNAE|grupo CNAE|divisão CNAE|seção CNAE|
CONCLA|CNAE 2.3|código de atividade econômica''',
    'email': '''e-mail frio|assunto de e-mail|taxa de abertura|taxa de resposta|taxa de cliques|bounce|hard bounce|soft bounce|
spam trap|blacklist de e-mail|SPF|DKIM|DMARC|reputação de domínio|aquecimento de domínio|domínio de envio|entregabilidade|
caixa de entrada|filtro de spam|opt-in|opt-out|double opt-in|descadastro|personalização de e-mail|campos personalizados|
e-mail de breakup|e-mail marketing B2B|disparo em massa|limite de envio|pixel de abertura''',
    'whatsapp': '''WhatsApp Business|WhatsApp Business Platform|lista de transmissão|mensagem modelo do WhatsApp|
catálogo do WhatsApp|etiquetas do WhatsApp Business|chatbot de vendas|resposta automática|link do WhatsApp (wa.me)|
WhatsApp para vendas B2B''',
    'linkedin': '''LinkedIn Sales Navigator|InMail|Social Selling Index (SSI)|conexão no LinkedIn|perfil de LinkedIn para vendas|
página de empresa no LinkedIn|ligação fria|roteiro de ligação|discador automático|videomensagem de prospecção''',
    'gestao': '''funil de vendas|pipeline de vendas|forecast de vendas|meta de vendas|cota de vendas|taxa de conversão|
ticket médio|CAC|LTV|LTV/CAC|payback|churn|MRR|ARR|receita recorrente|NPS|upsell|cross-sell|downsell|customer success|
onboarding de clientes|health score|retenção de clientes|KPI de vendas|OKR comercial|SLA entre marketing e vendas|smarketing|
RevOps|sales ops|sales enablement|comissão de vendas|OTE|remuneração variável|território de vendas|carteira de clientes|
key account|KAM|representante comercial|distribuidor|revenda|canal indireto|parceiro de canal|CRM|automação comercial|
Kanban de vendas|estágio do funil|oportunidade de venda|negócio ganho|motivo de perda|tempo de resposta ao lead|speed to lead|
produtividade comercial|gestão de leads|distribuição de leads|roleta de leads|dashboard de vendas|relatório de vendas|B2B|B2C|
B2B2C|D2C|marketplace B2B|venda direta|venda por representação|gestão comercial|plano de vendas|previsibilidade de receita''',
    'lgpd': '''LGPD|ANPD|titular de dados|dado pessoal|dado pessoal sensível|dado anonimizado|controlador de dados|
operador de dados|encarregado de dados (DPO)|tratamento de dados|base legal|consentimento|legítimo interesse|
teste de balanceamento|relatório de impacto (RIPD)|registro das operações de tratamento|incidente de segurança|
direito de oposição|direito de acesso aos dados|portabilidade de dados|eliminação de dados|anonimização|pseudonimização|
minimização de dados|princípio da finalidade|princípio da transparência|privacy by design|política de privacidade|
dado de acesso público|agente de tratamento''',
    'metas': '''landing page|isca digital|inbound marketing|marketing de conteúdo|jornada do cliente|topo de funil|
meio de funil|fundo de funil|CTA|UTM|atribuição de marketing|primeiro toque|último toque|remarketing|newsletter|
automação de marketing|segmentação de público|teste A/B|taxa de rejeição|tráfego orgânico|palavra-chave|intenção de busca|
prova social|case de sucesso|proposta de valor|posicionamento de marca|diferencial competitivo|benchmark|SEO|SEM|CTR|CPC|
CPL|CPA|ROAS''',
}
GLOSSARIO = [(t.strip(), cl) for cl, bloco in _G.items() for t in bloco.replace('\n', '').split('|') if t.strip()]

# ---------------------------------------------------------------------------
# Modelos prontos
# ---------------------------------------------------------------------------
MODELOS = [
    ('modelo de e-mail de prospecção', 'email'), ('modelo de e-mail de apresentação de empresa', 'email'),
    ('modelo de e-mail de follow-up', 'email'), ('modelo de follow-up após proposta', 'email'),
    ('modelo de e-mail de follow-up após reunião', 'email'), ('modelo de e-mail para reativar cliente', 'email'),
    ('modelo de e-mail pedindo indicação', 'email'), ('modelo de e-mail para agendar reunião', 'email'),
    ('modelo de e-mail de agradecimento ao cliente', 'email'), ('modelo de e-mail de último contato', 'email'),
    ('modelo de e-mail de boas-vindas ao cliente', 'email'), ('modelo de e-mail pós-feira de negócios', 'email'),
    ('modelo de mensagem de prospecção no whatsapp', 'whatsapp'), ('modelo de follow-up no whatsapp', 'whatsapp'),
    ('modelo de mensagem de apresentação no whatsapp', 'whatsapp'), ('mensagem de whatsapp para cliente sumido', 'whatsapp'),
    ('mensagem de whatsapp para agendar visita', 'whatsapp'), ('script de ligação fria', 'linkedin'),
    ('script para passar pela secretária', 'linkedin'), ('script de ligação de follow-up', 'linkedin'),
    ('roteiro de reunião de descoberta', 'prospeccao'), ('roteiro de demonstração de produto', 'prospeccao'),
    ('modelo de proposta comercial', 'gestao'), ('modelo de proposta comercial simples', 'gestao'),
    ('modelo de carta de apresentação comercial', 'abordagem'), ('mensagem de conexão no linkedin para vendas', 'linkedin'),
    ('modelo de inmail no linkedin', 'linkedin'), ('modelo de cadência de prospecção de 14 dias', 'prospeccao'),
    ('planilha de controle de vendas', 'gestao'), ('planilha de funil de vendas', 'metas'),
    ('planilha de metas de vendas', 'metas'), ('checklist de qualificação de leads', 'prospeccao'),
    ('checklist de perfil de cliente ideal', 'decisor'), ('modelo de playbook de vendas', 'gestao'),
    ('script de quebra de objeções', 'abordagem'), ('como responder cliente que diz que está caro', 'abordagem'),
    ('como responder me manda por e-mail', 'abordagem'), ('modelo de pesquisa de satisfação B2B', 'gestao'),
    ('modelo de pitch de vendas', 'abordagem'), ('modelo de elevator pitch', 'abordagem'),
    ('modelo de relatório semanal de vendas', 'gestao'), ('modelo de plano de ação comercial', 'gestao'),
    ('mensagem de prospecção para representante comercial', 'prospeccao'), ('modelo de e-mail para fornecedor B2B', 'email'),
    ('modelo de apresentação de representante comercial', 'prospeccao'),
    ('modelo de mensagem de aniversário para cliente B2B', 'whatsapp'),
    ('modelo de e-mail de retomada de negociação', 'email'),
]

# ---------------------------------------------------------------------------
# LGPD artigo por artigo (sempre revisado pelo dono antes de publicar)
# ---------------------------------------------------------------------------
NORMAS = [
    ('art-5-definicoes', 'lgpd art 5 definições', ['5']), ('art-6-principios', 'lgpd art 6 princípios', ['6']),
    ('art-7-bases-legais', 'bases legais da lgpd art 7', ['7']),
    ('legitimo-interesse-art-10', 'legítimo interesse lgpd art 10', ['7', '10']),
    ('dados-publicos-art-7', 'lgpd dados públicos', ['7']), ('consentimento-art-8', 'consentimento lgpd art 8', ['8']),
    ('direitos-do-titular-art-18', 'direitos do titular lgpd art 18', ['18']),
    ('prazo-de-resposta-art-19', 'prazo para responder titular lgpd', ['19']),
    ('registro-de-operacoes-art-37', 'registro de operações lgpd art 37', ['37']),
    ('relatorio-de-impacto-art-38', 'relatório de impacto lgpd art 38', ['38']),
    ('encarregado-art-41', 'encarregado de dados lgpd art 41', ['41']),
    ('seguranca-art-46', 'segurança dos dados lgpd art 46', ['46']),
    ('incidente-de-seguranca-art-48', 'incidente de segurança lgpd art 48', ['48']),
    ('sancoes-art-52', 'multa lgpd art 52', ['52']), ('aplicacao-art-3-e-4', 'a quem se aplica a lgpd', ['3', '4']),
    ('fim-do-tratamento-art-15-e-16', 'término do tratamento de dados lgpd', ['15', '16']),
]

# ---------------------------------------------------------------------------
# Comparativos (só com os fatos conferidos de conteudo_alternativas.py)
# ---------------------------------------------------------------------------
_CONC = ['econodata', 'speedio', 'leads2b', 'apollo']
COMPARATIVOS = [(f'{a} vs {b}', f'{a}-vs-{b}', [a, b]) for i, a in enumerate(_CONC) for b in _CONC[i + 1:]] + [
    ('melhor ferramenta de prospecção b2b', 'melhor-ferramenta-de-prospeccao-b2b', _CONC),
    ('ferramenta de prospecção para pequenas empresas', 'ferramenta-de-prospeccao-para-pequenas-empresas', _CONC),
    ('ferramenta de prospecção para representante comercial', 'ferramenta-de-prospeccao-para-representante-comercial', _CONC),
    ('ferramenta de prospecção para indústria', 'ferramenta-de-prospeccao-para-industria', _CONC),
    ('ferramenta de prospecção para distribuidora', 'ferramenta-de-prospeccao-para-distribuidora', _CONC),
    ('ferramenta de prospecção por whatsapp', 'ferramenta-de-prospeccao-por-whatsapp', _CONC),
    ('ferramenta para lista de empresas por cnae', 'ferramenta-para-lista-de-empresas-por-cnae', _CONC),
    ('ferramenta para encontrar decisor de empresa', 'ferramenta-para-encontrar-decisor', _CONC),
    ('ferramenta de prospecção gratuita', 'ferramenta-de-prospeccao-gratuita', _CONC),
    ('econodata preço', 'econodata-preco', ['econodata']), ('speedio preço', 'speedio-preco', ['speedio']),
    ('leads2b preço', 'leads2b-preco', ['leads2b']), ('apollo.io preço', 'apollo-preco', ['apollo']),
    ('econodata vale a pena', 'econodata-vale-a-pena', ['econodata']), ('speedio vale a pena', 'speedio-vale-a-pena', ['speedio']),
    ('leads2b vale a pena', 'leads2b-vale-a-pena', ['leads2b']), ('apollo.io vale a pena', 'apollo-vale-a-pena', ['apollo']),
    ('planilha ou ferramenta de prospecção', 'planilha-ou-ferramenta-de-prospeccao', []),
    ('crm ou ferramenta de prospecção', 'crm-ou-ferramenta-de-prospeccao', []),
    ('prospecção manual ou automatizada', 'prospeccao-manual-ou-automatizada', []),
    ('comprar lista de empresas ou montar a própria', 'comprar-lista-ou-montar-a-propria', []),
    ('whatsapp business ou api do whatsapp para vendas', 'whatsapp-business-ou-api', []),
    ('e-mail frio ou ligação fria', 'email-frio-ou-ligacao-fria', []),
    ('sdr interno ou terceirizado', 'sdr-interno-ou-terceirizado', []),
]

# Pilares dos clusters que ainda não têm guia completo
PILARES = [
    ('prospecção por e-mail', 'prospeccao-por-email-guia-completo', 'email'),
    ('linkedin para vendas b2b', 'linkedin-para-vendas-b2b-guia-completo', 'linkedin'),
    ('indicadores de vendas', 'indicadores-de-vendas-guia-completo', 'gestao'),
    ('lgpd na prospecção b2b', 'lgpd-na-prospeccao-b2b-guia-completo', 'lgpd'),
    ('cnae para prospecção', 'cnae-para-prospeccao-guia-completo', 'cnae'),
    ('ferramentas de prospecção b2b', 'ferramentas-de-prospeccao-b2b-guia-completo', 'ferramentas'),
    ('prospecção por setor', 'prospeccao-por-setor-guia-completo', 'setores'),
]
# Segmentos que já têm guia no blog (não duplicar em /setores)
SETORES_NO_BLOG = {'contabilidade', 'clinicas', 'metalurgicas', 'metalurgia', 'tecnologia', 'cooperativas'}


def _alvo(url, tipo, cluster, consulta, prioridade=50, **extra):
    isca = cfg.CLUSTERS.get(cluster, {}).get('isca') or 'diagnostico-prospeccao'
    return {'url': url, 'tipo': tipo, 'cluster': cluster, 'consulta': consulta, 'isca': isca,
            'extra': dict(extra, prioridade=prioridade)}


def alvos(segmentos):
    """Todos os alvos das sementes (sem o mapa de buscas)."""
    saida = []
    for termo, cl in GLOSSARIO:
        saida.append(_alvo('/glossario/' + cm.slugify(termo), 'glossario', cl, f'o que é {termo.lower()}', 55, termo=termo))
    for consulta, cl in MODELOS:
        saida.append(_alvo('/modelos/' + cm.slugify(consulta), 'modelo', cl, consulta, 70))
    for s in segmentos:
        consulta = f'modelo de e-mail de prospecção para {s["label"].lower()}'
        saida.append(_alvo('/modelos/' + cm.slugify(consulta), 'modelo', 'setores', consulta, 60, segmento=s['slug']))
        if not any(x in s['slug'] for x in SETORES_NO_BLOG):
            saida.append(_alvo('/setores/' + s['slug'], 'setor', 'setores', f'como prospectar {s["label"].lower()}', 65,
                               segmento=s['slug']))
    for slug, consulta, artigos in NORMAS:
        saida.append(_alvo('/lgpd/' + slug, 'norma', 'lgpd', consulta, 60, artigos=artigos))
    for consulta, slug, conc in COMPARATIVOS:
        saida.append(_alvo('/comparar/' + slug, 'comparativo', 'ferramentas', consulta, 75, concorrentes=conc))
    for consulta, slug, cl in PILARES:
        saida.append(_alvo('/blog/' + slug, 'pilar', cl, consulta, 90))
    return saida


def semear(cur, segmentos, extras=()):
    """Grava os alvos que ainda não existem como 'pendente'. Devolve quantos."""
    n = 0
    for a in list(alvos(segmentos)) + list(extras):
        cur.execute("""INSERT INTO conteudo_paginas (url, tipo, cluster, consulta, isca, extra, status, origem)
                       VALUES (%s, %s, %s, %s, %s, %s, 'pendente', 'llm') ON CONFLICT (url) DO NOTHING""",
                    (a['url'], a['tipo'], a['cluster'], a['consulta'], a['isca'], json.dumps(a['extra'], ensure_ascii=False)))
        n += cur.rowcount
    return n


# ---------------------------------------------------------------------------
# Contexto do gerador
# ---------------------------------------------------------------------------


def _estat(cur, codigo):
    cur.execute('SELECT dados, base_mes FROM cnae_estatisticas WHERE codigo = %s', (codigo,))
    r = cur.fetchone()
    if not r:
        return None, None
    d = r['dados'] if isinstance(r['dados'], dict) else json.loads(r['dados'])
    return d, r['base_mes']


def _resumo_segmento(cur, seg):
    d, mes = _estat(cur, seg['codigo'])
    if not d:
        return None, mes
    return {'segmento': seg['label'], 'cnae': cnae.formatado(seg['codigo']),
            'empresas_ativas_com_contato_no_brasil': d['total'], 'com_email_publico': d.get('com_email'),
            'com_socio_identificado': d.get('com_socio'),
            'estados_com_mais_empresas': [{'uf': x['uf'], 'empresas': x['n']} for x in d.get('por_uf', [])[:8]],
            'cidades_com_mais_empresas': [{'cidade': f"{x['municipio']}/{x['uf']}", 'empresas': x['n']}
                                          for x in d.get('cidades', [])[:8]],
            'por_porte': [{'porte': cnae.PORTES.get(x['porte'], 'Não informado'), 'empresas': x['n']}
                          for x in d.get('por_porte', [])],
            'pagina_da_lista': f"/empresas/{seg['slug']}"}, mes


def _links(cur, alvo, segmentos):
    cl = alvo.get('cluster')
    info = cfg.CLUSTERS.get(cl, {})
    links = [{'url': info.get('pilar', '/blog'), 'titulo': f"Guia: {info.get('nome', 'prospecção B2B')}"},
             {'url': '/empresas', 'titulo': 'Empresas por segmento e cidade (base da Receita)'},
             {'url': '/cnae', 'titulo': 'Consulta de CNAE com empresas ativas'},
             {'url': '/glossario', 'titulo': 'Glossário de vendas B2B'},
             {'url': '/modelos', 'titulo': 'Modelos prontos de prospecção'}]
    for k in iscas.ISCAS:
        links.append({'url': iscas.url_de(k), 'titulo': f'Ferramenta grátis: {iscas.ISCAS[k]["nome"]}'})
    try:
        import links_internos
        for k, v in links_internos.CLUSTERS.items():
            if k == cl or (cl in ('email', 'whatsapp', 'linkedin') and k == 'abordagem') or \
                    (cl in ('gestao', 'ferramentas') and k in ('metas', 'crm')):
                for slug in [v['pilar']] + v['satelites']:
                    links.append({'url': f'/blog/{slug}', 'titulo': slug.replace('-', ' ')})
    except Exception:
        pass
    cur.execute("""SELECT url, titulo FROM conteudo_paginas WHERE status = 'publicada' AND cluster = %s
                   AND url <> %s ORDER BY random() LIMIT 12""", (cl, alvo['url']))
    links += [{'url': r['url'], 'titulo': r['titulo']} for r in cur.fetchall()]
    seg = (alvo.get('extra') or {}).get('segmento')
    if seg:
        links.append({'url': f'/empresas/{seg}', 'titulo': 'Lista de empresas do segmento'})
        links.append({'url': f'/setores/{seg}', 'titulo': 'Como prospectar este segmento'})
    vistos, saida = set(), []
    for l in links:
        if l['url'] not in vistos and l['url'] != alvo['url']:
            vistos.add(l['url'])
            saida.append(l)
    return saida[:40]


def contexto(cur, alvo, segmentos_por_slug, alternativas_por_slug, relatorio=None):
    """DADOS, FONTES, LINKS e ISCA de um alvo."""
    extra = alvo.get('extra') or {}
    dados, fontes = {}, []
    receita = dict(cnae.RECEITA_FONTE, id='receita')
    seg = segmentos_por_slug.get(extra.get('segmento') or '')
    if seg:
        resumo, mes = _resumo_segmento(cur, seg)
        if resumo:
            dados['base_da_receita'] = resumo
            fontes.append(dict(receita, consultado_em=mes or ''))
    if alvo['tipo'] == 'norma':
        dados['texto_oficial'] = {f'art_{a}': lgpd_textos.ARTIGOS.get(a, []) for a in extra.get('artigos') or []}
        fontes.append(dict(lgpd_textos.FONTE, id='planalto'))
    if alvo['tipo'] == 'comparativo':
        fatos = []
        for slug in extra.get('concorrentes') or []:
            alt = alternativas_por_slug.get(slug)
            if not alt:
                continue
            fatos.append({'ferramenta': alt['nome'], 'consultado_em': alt.get('consultado_em'), 'resumo': alt.get('resumo'),
                          'tabela': [list(r) for r in alt.get('tabela', [])], 'pagina_comparativa': f'/alternativas/{slug}'})
            for i, url in enumerate(alt.get('fontes', [])[:4]):
                fontes.append({'id': f'{slug}-{i + 1}', 'nome': f'Site oficial {alt["nome"]}', 'url': url,
                               'consultado_em': alt.get('consultado_em')})
        dados['fatos_conferidos'] = fatos
        dados['nota'] = 'Fatos de cada ferramenta conferidos no site oficial na data indicada; o que não está aqui não deve ser afirmado.'
    if relatorio and alvo['tipo'] in ('pilar', 'satelite', 'glossario') and not dados:
        dados['base_da_receita_brasil'] = {
            'empresas_ativas_com_contato': relatorio.get('total'), 'com_email': relatorio.get('com_email'),
            'com_socio': relatorio.get('com_socio'),
            'estados_com_mais_empresas': [{'uf': x['uf'], 'empresas': x['n']} for x in relatorio.get('por_uf', [])[:5]],
            'pagina_do_relatorio': '/dados/empresas-ativas-no-brasil'}
        fontes.append(dict(receita, consultado_em=relatorio.get('base_mes') or ''))
    if extra.get('termo'):
        dados['termo'] = extra['termo']
    isca_id = alvo.get('isca') or 'diagnostico-prospeccao'
    isca = iscas.ISCAS.get(isca_id, {})
    return {'dados': dados, 'fontes': fontes, 'links': _links(cur, alvo, segmentos_por_slug),
            'isca': {'nome': isca.get('nome'), 'url': iscas.url_de(isca_id) if isca else None}}


def numeros_permitidos(ctx, alvo):
    import gerador_conteudo
    base = [ctx.get('dados'), ctx.get('fontes'), alvo.get('consulta'), gerador_conteudo.PRODUTO]
    s = set()
    for x in base:
        s |= cm.numeros_de(x)
    return s
