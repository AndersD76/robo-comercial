"""Links internos do blog: pilar + satélites por cluster e similaridade.

Antes, cada post listava os outros 29 como "relacionados": link demais, sem
contexto, e o pilar de cada tema não se destacava. Aqui cada post recebe:
  - o pilar do seu cluster (o guia principal do tema);
  - os satélites mais parecidos (TF-IDF sobre o texto do post);
  - um post de outro cluster, para o leitor não ficar preso num tema;
  - as ferramentas e páginas de dados ligadas ao tema.
O pilar lista todos os seus satélites. Calculado uma vez na importação.

Clusters vêm de growth/mapa-intencao.csv.
"""
import math
import re
from collections import Counter

CLUSTERS = {
    'listas': {
        'nome': 'Listas e base de empresas',
        'pilar': 'base-de-dados-de-empresas-cnpj',
        'satelites': ['lista-de-empresas-por-cidade', 'mailing-de-empresas',
                      'o-que-e-cnae-prospeccao'],
        'paginas': [('Lista de empresas por cidade e segmento (grátis)', '/ferramentas/lista-de-empresas'),
                    ('Empresas por segmento e cidade, com dados da Receita', '/empresas')],
    },
    'prospeccao': {
        'nome': 'Prospecção B2B',
        'pilar': 'como-prospectar-clientes-b2b',
        'satelites': ['como-encontrar-clientes-pela-internet', 'como-fazer-prospeccao-ativa',
                      'como-montar-lista-de-prospeccao', 'como-conseguir-clientes-representante-comercial',
                      'como-vender-para-industrias', 'prospecao-outbound-guia',
                      'como-gerar-leads-qualificados', 'prospectar-empresas-de-tecnologia',
                      'como-prospectar-clinicas-e-consultorios', 'como-prospectar-contabilidades',
                      'como-prospectar-metalurgicas', 'como-vender-para-cooperativas-agricolas',
                      'automacao-comercial-para-industria'],
        'paginas': [('Lista de empresas por cidade e segmento (grátis)', '/ferramentas/lista-de-empresas'),
                    ('Prospecção para indústria', '/para/industria')],
    },
    'abordagem': {
        'nome': 'Abordagem e mensagens',
        'pilar': 'mensagem-de-prospeccao-whatsapp',
        'satelites': ['email-marketing-b2b-templates', 'follow-up-de-vendas',
                      'whatsapp-para-vendas-b2b'],
        'paginas': [('Gerador de mensagem de prospecção com IA (grátis)',
                     '/ferramentas/gerador-de-mensagem-de-prospeccao')],
    },
    'metas': {
        'nome': 'Metas e funil de vendas',
        'pilar': 'quantos-leads-preciso-para-bater-a-meta',
        'satelites': ['pipeline-de-vendas-como-montar'],
        'paginas': [('Calculadora de leads: quantos preciso para a meta',
                     '/ferramentas/calculadora-de-leads')],
    },
    'crm': {
        'nome': 'CRM e automação comercial',
        'pilar': 'automacao-comercial-guia-completo',
        'satelites': ['crm-para-pequenas-empresas', 'o-que-e-crm-para-que-serve',
                      'crm-para-distribuidora', 'turbovenda-vs-rdstation'],
        'paginas': [('Comparativos com Econodata, Speedio, Leads2b e Apollo', '/alternativas')],
    },
    'decisor': {
        'nome': 'Decisor e sócios',
        'pilar': 'como-encontrar-o-decisor-da-empresa',
        'satelites': [],
        'paginas': [('Empresas por segmento e cidade, com dados da Receita', '/empresas')],
    },
}

_PALAVRAS_VAZIAS = set('''a o as os um uma uns umas de da do das dos em no na nos nas
por para pelo pela pelos pelas com sem sobre entre e ou que se seu sua seus suas
ao aos à às é são ser foi como mais menos muito muita já não sim isso esse essa este
esta isto ele ela eles elas você vocês nós lhe lhes mas também quando onde qual quais
cada até porque pois então só ainda há tem têm ter vai vão pode podem deve devem
the and turbovenda'''.split())


def _tokens(html):
    texto = re.sub(r'<[^>]+>', ' ', html or '').lower()
    return [t for t in re.findall(r'[a-zà-ú0-9]{3,}', texto) if t not in _PALAVRAS_VAZIAS]


def _vetores(docs):
    n = len(docs)
    df = Counter(t for d in docs.values() for t in set(d))
    vet = {}
    for slug, toks in docs.items():
        tf = Counter(toks)
        v = {t: (c / len(toks)) * math.log((1 + n) / (1 + df[t])) for t, c in tf.items()} if toks else {}
        norma = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vet[slug] = {t: x / norma for t, x in v.items()}
    return vet


def _similaridade(a, b):
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(t, 0.0) for t, x in a.items())


def montar(posts):
    """{slug: {'cluster', 'pilar', 'relacionados': [post], 'paginas': [(titulo, url)]}}"""
    por_slug = {p['slug']: p for p in posts}
    cluster_de = {}
    for chave, c in CLUSTERS.items():
        for slug in [c['pilar']] + c['satelites']:
            cluster_de[slug] = chave
    vet = _vetores({s: _tokens(p.get('titulo', '') + ' ' + p.get('conteudo', ''))
                    for s, p in por_slug.items()})
    resultado = {}
    for slug, post in por_slug.items():
        chave = cluster_de.get(slug)
        c = CLUSTERS.get(chave) or {'nome': '', 'pilar': None, 'satelites': [], 'paginas': []}
        parecidos = sorted((s for s in por_slug if s != slug),
                           key=lambda s: -_similaridade(vet[slug], vet[s]))
        hub = slug == c['pilar'] and any(s in por_slug for s in c['satelites'])
        if hub:
            # O pilar é o hub do tema: lista todos os satélites, e só eles
            rel = [s for s in c['satelites'] if s in por_slug]
        elif slug == c['pilar']:
            rel = parecidos[:4]   # pilar sem satélites: os mais próximos
        else:
            # O pilar vai em destaque à parte (chave 'pilar'), fora da lista
            rel = [s for s in parecidos if cluster_de.get(s) == chave and s != c['pilar']][:3]
            fora = next((s for s in parecidos if cluster_de.get(s) != chave and s not in rel), None)
            if fora:
                rel.append(fora)
        resultado[slug] = {
            'hub': hub,
            'cluster': c['nome'],
            'pilar': por_slug.get(c['pilar']) if c['pilar'] != slug else None,
            'relacionados': [por_slug[s] for s in rel if s in por_slug and s != slug],
            'paginas': c['paginas'],
        }
    return resultado


def orfaos(mapa):
    """Posts que nenhum outro post linka (o índice do blog não conta)."""
    linkados = {r['slug'] for m in mapa.values() for r in m['relacionados']}
    linkados |= {m['pilar']['slug'] for m in mapa.values() if m['pilar']}
    return sorted(set(mapa) - linkados)
