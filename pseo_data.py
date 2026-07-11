# -*- coding: utf-8 -*-
"""
Dados compartilhados do motor de SEO programático (pSEO) — TurboVenda.

Usado por:
  - app.py (rotas /empresas/*)
  - scripts/cnpj_ingest.py (ingestão dos dados abertos CNPJ da Receita)

CNAE_B2B: ~50 CNAEs principais (7 dígitos, formato dos dados abertos CNPJ)
de segmentos B2B relevantes para prospecção. Cada entrada:
  codigo  -> 7 dígitos como aparece no CSV da Receita (sem pontuação)
  slug    -> usado na URL /empresas/{slug}/{municipio-uf}
  nome    -> completa a frase "Empresas de {nome} em {Cidade}"
  label   -> nome plural para listas e anchors ("Transportadoras", "Gráficas")
"""

import re
import unicodedata


def slugify(texto):
    """passo fundo -> passo-fundo (remove acentos, minúsculas, hífens)."""
    if not texto:
        return ''
    t = unicodedata.normalize('NFKD', str(texto))
    t = t.encode('ascii', 'ignore').decode('ascii').lower()
    t = re.sub(r'[^a-z0-9]+', '-', t).strip('-')
    return t


def cnae_formatado(codigo):
    """6201501 -> 6201-5/01 (formato oficial de exibição)."""
    c = str(codigo)
    if len(c) != 7:
        return c
    return f'{c[:4]}-{c[4]}/{c[5:]}'


PORTE_LABELS = {
    '00': 'Não informado',
    '01': 'Microempresa',
    '03': 'Pequena (EPP)',
    '05': 'Média/Grande',
}


UF_NOMES = {
    'RS': 'Rio Grande do Sul',
    'SC': 'Santa Catarina',
    'PR': 'Paraná',
}


# UFs cobertas na primeira fase da ingestão
UFS_INGEST = ('RS', 'SC', 'PR')


CNAE_B2B = [
    # --- Fabricação de máquinas e equipamentos ---
    {'codigo': '2833000', 'slug': 'maquinas-agricolas', 'nome': 'fabricação de máquinas agrícolas', 'label': 'Fabricantes de máquinas agrícolas'},
    {'codigo': '2869100', 'slug': 'maquinas-industriais', 'nome': 'fabricação de máquinas para uso industrial', 'label': 'Fabricantes de máquinas industriais'},
    {'codigo': '2829199', 'slug': 'maquinas-uso-geral', 'nome': 'fabricação de máquinas de uso geral', 'label': 'Fabricantes de máquinas de uso geral'},
    {'codigo': '3321000', 'slug': 'instalacao-de-maquinas', 'nome': 'instalação de máquinas e equipamentos industriais', 'label': 'Instaladoras de máquinas industriais'},
    {'codigo': '3314710', 'slug': 'manutencao-de-maquinas', 'nome': 'manutenção de máquinas e equipamentos', 'label': 'Manutenção de máquinas'},
    # --- Metalurgia / produtos de metal ---
    {'codigo': '2511000', 'slug': 'estruturas-metalicas', 'nome': 'fabricação de estruturas metálicas', 'label': 'Fabricantes de estruturas metálicas'},
    {'codigo': '2512800', 'slug': 'esquadrias-de-metal', 'nome': 'fabricação de esquadrias de metal', 'label': 'Fabricantes de esquadrias de metal'},
    {'codigo': '2539001', 'slug': 'usinagem', 'nome': 'usinagem, tornearia e solda', 'label': 'Usinagens'},
    {'codigo': '2542000', 'slug': 'serralheria', 'nome': 'serralheria', 'label': 'Serralherias'},
    {'codigo': '2451200', 'slug': 'fundicao', 'nome': 'fundição de ferro e aço', 'label': 'Fundições'},
    # --- Indústria de alimentos ---
    {'codigo': '1011201', 'slug': 'frigorificos', 'nome': 'frigorífico e abate de bovinos', 'label': 'Frigoríficos (bovinos)'},
    {'codigo': '1012101', 'slug': 'abate-de-aves', 'nome': 'abate de aves', 'label': 'Abatedouros de aves'},
    {'codigo': '1052000', 'slug': 'laticinios', 'nome': 'fabricação de laticínios', 'label': 'Laticínios'},
    {'codigo': '1061901', 'slug': 'beneficiamento-de-arroz', 'nome': 'beneficiamento de arroz', 'label': 'Beneficiadoras de arroz'},
    {'codigo': '1066000', 'slug': 'alimentos-para-animais', 'nome': 'fabricação de alimentos para animais', 'label': 'Fábricas de ração'},
    {'codigo': '1091101', 'slug': 'panificacao-industrial', 'nome': 'panificação industrial', 'label': 'Panificação industrial'},
    {'codigo': '1041400', 'slug': 'oleos-vegetais', 'nome': 'fabricação de óleos vegetais', 'label': 'Indústrias de óleos vegetais'},
    # --- Embalagens, plástico, papel, móveis, química, têxtil ---
    {'codigo': '2222600', 'slug': 'embalagens-plasticas', 'nome': 'fabricação de embalagens plásticas', 'label': 'Fabricantes de embalagens plásticas'},
    {'codigo': '1731100', 'slug': 'embalagens-de-papel', 'nome': 'fabricação de embalagens de papel', 'label': 'Fabricantes de embalagens de papel'},
    {'codigo': '3101200', 'slug': 'moveis-de-madeira', 'nome': 'fabricação de móveis de madeira', 'label': 'Fabricantes de móveis'},
    {'codigo': '2029100', 'slug': 'produtos-quimicos', 'nome': 'fabricação de produtos químicos', 'label': 'Indústrias químicas'},
    {'codigo': '1412601', 'slug': 'confeccao-de-vestuario', 'nome': 'confecção de vestuário', 'label': 'Confecções'},
    # --- Gráficas ---
    {'codigo': '1813001', 'slug': 'graficas', 'nome': 'impressão gráfica de material publicitário', 'label': 'Gráficas'},
    # --- Atacado / distribuição ---
    {'codigo': '4632001', 'slug': 'atacado-de-cereais', 'nome': 'comércio atacadista de cereais', 'label': 'Atacadistas de cereais'},
    {'codigo': '4639701', 'slug': 'atacado-de-alimentos', 'nome': 'comércio atacadista de alimentos', 'label': 'Atacadistas de alimentos'},
    {'codigo': '4644301', 'slug': 'atacado-de-medicamentos', 'nome': 'comércio atacadista de medicamentos', 'label': 'Distribuidoras de medicamentos'},
    {'codigo': '4661300', 'slug': 'comercio-de-maquinas-agropecuarias', 'nome': 'comércio de máquinas e equipamentos agropecuários', 'label': 'Revendas de máquinas agropecuárias'},
    {'codigo': '4663000', 'slug': 'comercio-de-maquinas-industriais', 'nome': 'comércio de máquinas e equipamentos industriais', 'label': 'Revendas de máquinas industriais'},
    {'codigo': '4683400', 'slug': 'defensivos-e-fertilizantes', 'nome': 'comércio de defensivos agrícolas e fertilizantes', 'label': 'Distribuidoras de defensivos e fertilizantes'},
    {'codigo': '4692300', 'slug': 'insumos-agropecuarios', 'nome': 'comércio atacadista de insumos agropecuários', 'label': 'Atacadistas de insumos agropecuários'},
    {'codigo': '4672900', 'slug': 'atacado-de-ferragens', 'nome': 'comércio atacadista de ferragens e ferramentas', 'label': 'Atacadistas de ferragens'},
    {'codigo': '4679699', 'slug': 'atacado-de-materiais-de-construcao', 'nome': 'comércio atacadista de materiais de construção', 'label': 'Atacadistas de materiais de construção'},
    {'codigo': '4530701', 'slug': 'atacado-de-autopecas', 'nome': 'comércio atacadista de autopeças', 'label': 'Distribuidoras de autopeças'},
    {'codigo': '4635499', 'slug': 'atacado-de-bebidas', 'nome': 'comércio atacadista de bebidas', 'label': 'Distribuidoras de bebidas'},
    {'codigo': '4646002', 'slug': 'atacado-de-higiene-e-cosmeticos', 'nome': 'comércio atacadista de higiene e cosméticos', 'label': 'Atacadistas de higiene e cosméticos'},
    {'codigo': '4649408', 'slug': 'atacado-de-produtos-de-limpeza', 'nome': 'comércio atacadista de produtos de limpeza', 'label': 'Atacadistas de produtos de limpeza'},
    # --- Transporte / logística ---
    {'codigo': '4930201', 'slug': 'transporte-de-cargas-municipal', 'nome': 'transporte rodoviário de cargas (municipal)', 'label': 'Transportadoras (municipal)'},
    {'codigo': '4930202', 'slug': 'transportadoras', 'nome': 'transporte rodoviário de cargas', 'label': 'Transportadoras'},
    {'codigo': '5211701', 'slug': 'armazens-gerais', 'nome': 'armazéns gerais', 'label': 'Armazéns gerais'},
    # --- TI / software ---
    {'codigo': '6201501', 'slug': 'desenvolvimento-de-software', 'nome': 'desenvolvimento de software sob encomenda', 'label': 'Software houses'},
    {'codigo': '6202300', 'slug': 'software-customizavel', 'nome': 'desenvolvimento de software customizável', 'label': 'Desenvolvedoras de software customizável'},
    {'codigo': '6204000', 'slug': 'consultoria-em-ti', 'nome': 'consultoria em tecnologia da informação', 'label': 'Consultorias de TI'},
    {'codigo': '6209100', 'slug': 'suporte-tecnico-ti', 'nome': 'suporte técnico em TI', 'label': 'Suporte técnico de TI'},
    # --- Saúde privada ---
    {'codigo': '8630501', 'slug': 'clinicas-medicas', 'nome': 'atividade médica ambulatorial (clínicas)', 'label': 'Clínicas médicas'},
    {'codigo': '8630503', 'slug': 'consultorios-medicos', 'nome': 'consultórios médicos', 'label': 'Consultórios médicos'},
    {'codigo': '8630504', 'slug': 'clinicas-odontologicas', 'nome': 'odontologia', 'label': 'Clínicas odontológicas'},
    {'codigo': '8640202', 'slug': 'laboratorios-clinicos', 'nome': 'laboratórios de análises clínicas', 'label': 'Laboratórios clínicos'},
    # --- Engenharia, construção e serviços profissionais ---
    {'codigo': '7112000', 'slug': 'engenharia', 'nome': 'serviços de engenharia', 'label': 'Empresas de engenharia'},
    {'codigo': '4120400', 'slug': 'construtoras', 'nome': 'construção de edifícios', 'label': 'Construtoras'},
    {'codigo': '4321500', 'slug': 'instalacoes-eletricas', 'nome': 'instalações elétricas', 'label': 'Empresas de instalações elétricas'},
    {'codigo': '6920601', 'slug': 'contabilidade', 'nome': 'contabilidade', 'label': 'Escritórios de contabilidade'},
    {'codigo': '7020400', 'slug': 'consultoria-empresarial', 'nome': 'consultoria em gestão empresarial', 'label': 'Consultorias empresariais'},
    {'codigo': '7311400', 'slug': 'agencias-de-publicidade', 'nome': 'publicidade', 'label': 'Agências de publicidade'},
    # --- Agro / serviços agrícolas ---
    {'codigo': '0161003', 'slug': 'servicos-agricolas', 'nome': 'serviços de preparação de terreno, cultivo e colheita', 'label': 'Prestadoras de serviços agrícolas'},
]

CNAE_POR_CODIGO = {c['codigo']: c for c in CNAE_B2B}
CNAE_POR_SLUG = {c['slug']: c for c in CNAE_B2B}
CNAE_CODIGOS = frozenset(CNAE_POR_CODIGO.keys())
