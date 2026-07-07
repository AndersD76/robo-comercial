#!/usr/bin/env python3
"""Replace _gerar_termos function body in app.py"""
import sys

with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find range: from "    SEGMENTOS_BASE = [" to "    return {'termos': lista, 'cargos': CARGOS}"
start = None
end = None
for i, line in enumerate(lines):
    if 'SEGMENTOS_BASE = [' in line and start is None:
        start = i
    if start is not None and "return {'termos': lista," in line:
        end = i
        break

if start is None or end is None:
    # Try alternate marker
    for i, line in enumerate(lines):
        if '# ── 1. Mapear keywords' in line and start is None:
            start = i
        if start is not None and "return {'termos': lista," in line:
            end = i
            break

if start is None or end is None:
    print(f'ERROR: Could not find range. start={start} end={end}')
    sys.exit(1)

print(f'Replacing lines {start+1} to {end+1}')

NEW_BODY = r"""    # ── 1. Mapear keywords da descrição → segmentos-alvo ──
    KEYWORD_SEGMENTS = {
        'agro': ['fazenda', 'cooperativa agrícola', 'agroindústria', 'cerealista',
                 'revendedora agrícola', 'usina açúcar álcool', 'frigorífico'],
        'agrícol': ['cooperativa agrícola', 'agroindústria', 'cerealista', 'fazenda',
                    'revendedora agrícola', 'silo grãos'],
        'rural': ['fazenda', 'cooperativa agrícola', 'agroindústria', 'pecuária'],
        'grão': ['cerealista', 'cooperativa agrícola', 'armazém grãos', 'trading agrícola',
                 'silo grãos', 'beneficiadora grãos'],
        'cereal': ['cerealista', 'cooperativa agrícola', 'armazém grãos', 'trading agrícola'],
        'soja': ['cerealista', 'cooperativa agrícola', 'trading agrícola', 'armazém grãos',
                 'agroindústria soja', 'esmagadora soja'],
        'milho': ['cerealista', 'cooperativa agrícola', 'trading agrícola', 'armazém grãos',
                  'agroindústria milho'],
        'trigo': ['moinho trigo', 'cooperativa agrícola', 'cerealista', 'armazém grãos',
                  'indústria farinha'],
        'arroz': ['beneficiadora arroz', 'cooperativa arroz', 'cerealista', 'armazém grãos'],
        'café': ['cooperativa café', 'exportadora café', 'beneficiadora café', 'torrefadora'],
        'silo': ['cerealista', 'cooperativa agrícola', 'armazém grãos', 'silo grãos'],
        'cooperativ': ['cooperativa agrícola', 'cooperativa crédito', 'cooperativa'],
        'tombador': ['cerealista', 'cooperativa agrícola', 'armazém grãos',
                     'trading agrícola', 'agroindústria'],
        'coletor': ['cerealista', 'cooperativa agrícola', 'armazém grãos'],
        'prensa': ['indústria reciclagem', 'cooperativa reciclagem', 'sucateiro',
                   'indústria papel', 'agroindústria'],
        'hidráulic': ['indústria metalúrgica', 'construtora', 'mineradora',
                      'empresa equipamentos industriais'],
        'saúde': ['hospital', 'clínica médica', 'laboratório análises',
                  'clínica odontológica', 'operadora saúde'],
        'médic': ['hospital', 'clínica médica', 'laboratório análises'],
        'software': ['empresa tecnologia', 'startup', 'software house',
                     'escritório contabilidade', 'empresa logística'],
        'sistema': ['escritório contabilidade', 'empresa logística',
                    'distribuidora', 'comércio varejista'],
        'monitor': ['escritório contabilidade', 'escritório advocacia',
                    'agência marketing digital', 'consultoria empresarial',
                    'empresa logística', 'empresa recursos humanos',
                    'empresa call center', 'empresa tecnologia',
                    'corretora seguros', 'BPO', 'startup'],
        'produtividade': ['escritório contabilidade', 'escritório advocacia',
                          'consultoria empresarial', 'empresa call center',
                          'empresa tecnologia', 'BPO', 'startup'],
        'funcionário': ['escritório contabilidade', 'empresa logística',
                        'empresa recursos humanos', 'empresa call center',
                        'empresa tecnologia', 'distribuidora'],
        'computador': ['escritório contabilidade', 'empresa call center',
                       'empresa tecnologia', 'BPO', 'startup'],
        'gestor': ['escritório contabilidade', 'empresa logística',
                   'empresa call center', 'empresa tecnologia', 'distribuidora'],
        'tecnologia': ['empresa tecnologia', 'startup', 'software house',
                       'provedor internet'],
        'construção': ['construtora', 'incorporadora', 'empresa engenharia',
                       'loja materiais construção'],
        'aliment': ['indústria alimentícia', 'distribuidora alimentos',
                    'frigorífico', 'padaria industrial'],
        'automotiv': ['concessionária veículos', 'oficina mecânica', 'autopeças'],
        'varejo': ['loja roupas', 'supermercado', 'rede lojas', 'franquia'],
        'financ': ['cooperativa crédito', 'corretora investimentos', 'fintech'],
        'jurídic': ['escritório advocacia', 'cartório'],
        'contab': ['escritório contabilidade', 'consultoria tributária'],
        'logística': ['transportadora', 'empresa logística', 'armazém'],
        'indústria': ['indústria metalúrgica', 'indústria química',
                      'indústria têxtil', 'fábrica', 'indústria plásticos'],
        'educaç': ['escola particular', 'faculdade', 'centro treinamento'],
        'seguran': ['empresa segurança', 'portaria remota', 'empresa facilities'],
        'energia': ['empresa energia solar', 'distribuidora energia'],
        'telecom': ['provedor internet', 'empresa telecom'],
        'pet': ['pet shop', 'clínica veterinária'],
        'beleza': ['salão beleza', 'clínica estética'],
        'imóve': ['imobiliária', 'incorporadora', 'construtora'],
        'recicl': ['cooperativa reciclagem', 'empresa reciclagem', 'sucateiro'],
        'mineraç': ['mineradora', 'pedreira', 'empresa mineração'],
        'pecuári': ['fazenda gado', 'frigorífico', 'leilão gado', 'confinamento'],
    }

    segmentos_priorizados = []
    for kw, segs in KEYWORD_SEGMENTS.items():
        if kw in desc_lower:
            segmentos_priorizados.extend(segs)

    seen = set()
    segmentos = []
    for s in segmentos_priorizados:
        if s not in seen:
            seen.add(s)
            segmentos.append(s)

    if not segmentos:
        segmentos = [
            'escritório contabilidade', 'escritório advocacia',
            'consultoria empresarial', 'empresa logística', 'construtora',
            'indústria metalúrgica', 'empresa tecnologia', 'distribuidora',
            'empresa recursos humanos', 'corretora seguros', 'imobiliária',
            'empresa transporte', 'cooperativa', 'empresa engenharia',
        ]

    # ── 2. Detectar regiões/estados mencionados na descrição ──
    REGIOES = {
        'sul': ['Curitiba', 'Porto Alegre', 'Florianópolis', 'Londrina', 'Maringá',
                'Cascavel', 'Ponta Grossa', 'Chapecó', 'Joinville', 'Blumenau',
                'Caxias do Sul', 'Passo Fundo', 'Novo Hamburgo', 'Santa Maria',
                'Pelotas', 'Guarapuava', 'Toledo', 'Francisco Beltrão'],
        'centro-oeste': ['Goiânia', 'Brasília', 'Campo Grande', 'Cuiabá',
                         'Anápolis', 'Aparecida de Goiânia', 'Dourados',
                         'Rondonópolis', 'Rio Verde', 'Sinop', 'Lucas do Rio Verde',
                         'Sorriso', 'Primavera do Leste', 'Itumbiara'],
        'sudeste': ['São Paulo', 'Campinas', 'Ribeirão Preto', 'Sorocaba',
                    'São José dos Campos', 'Piracicaba', 'Belo Horizonte',
                    'Uberlândia', 'Rio de Janeiro', 'Vitória', 'Jundiaí',
                    'Bauru', 'Franca', 'Uberaba'],
        'nordeste': ['Salvador', 'Recife', 'Fortaleza', 'São Luís', 'Natal',
                     'João Pessoa', 'Aracaju', 'Maceió', 'Teresina',
                     'Feira de Santana', 'Petrolina', 'Barreiras',
                     'Luís Eduardo Magalhães'],
        'norte': ['Manaus', 'Belém', 'Porto Velho', 'Palmas', 'Macapá',
                  'Rio Branco', 'Boa Vista'],
    }
    ESTADOS_POR_REGIAO = {
        'sul': ['PR', 'SC', 'RS'],
        'centro-oeste': ['GO', 'MT', 'MS', 'DF'],
        'sudeste': ['SP', 'MG', 'RJ', 'ES'],
        'nordeste': ['BA', 'PE', 'CE', 'MA', 'RN', 'PB', 'SE', 'AL', 'PI'],
        'norte': ['AM', 'PA', 'TO', 'RO', 'AC', 'RR', 'AP'],
    }

    regioes_match = []
    for regiao in REGIOES:
        if regiao in desc_lower:
            regioes_match.append(regiao)

    uf_map = {
        'paraná': 'sul', 'santa catarina': 'sul', 'rio grande do sul': 'sul',
        'goiás': 'centro-oeste', 'mato grosso': 'centro-oeste',
        'mato grosso do sul': 'centro-oeste',
        'são paulo': 'sudeste', 'minas gerais': 'sudeste',
        'rio de janeiro': 'sudeste', 'espírito santo': 'sudeste',
        'bahia': 'nordeste', 'pernambuco': 'nordeste', 'ceará': 'nordeste',
        'maranhão': 'nordeste', 'piauí': 'nordeste', 'tocantins': 'norte',
    }
    for uf_nome, reg in uf_map.items():
        if uf_nome in desc_lower and reg not in regioes_match:
            regioes_match.append(reg)

    if not regioes_match:
        regioes_match = list(REGIOES.keys())

    cidades = []
    estados = []
    for reg in regioes_match:
        cidades.extend(REGIOES.get(reg, []))
        estados.extend(ESTADOS_POR_REGIAO.get(reg, []))
    cidades = list(dict.fromkeys(cidades))
    estados = list(dict.fromkeys(estados))

    # ── 3. Cargos baseados na descrição ──
    CARGO_KW = {
        'Gerente de Operações': ['operaç'],
        'Gerente de Compras': ['compra', 'suprimento'],
        'Gerente de Infraestrutura': ['infraestrutura', 'silo', 'armazém'],
        'Diretor Industrial': ['indústria', 'industrial', 'fábrica'],
        'Gerente Agrícola': ['agrícol', 'agro', 'safra', 'grão'],
        'Diretor de TI': ['software', 'sistema', 'monitor', 'tecnologia'],
        'Gerente de TI': ['software', 'sistema', 'computador'],
        'Gerente Comercial': ['vendas', 'comercial'],
        'Gerente Financeiro': ['financ', 'contab'],
        'Gerente de Logística': ['logística', 'transporte', 'armazém'],
        'Gerente de Produção': ['produção', 'produtividade', 'fábrica'],
    }
    cargos_pri = []
    for cargo, triggers in CARGO_KW.items():
        if any(t in desc_lower for t in triggers):
            cargos_pri.append(cargo)
    cargos_base = [
        'Diretor Geral', 'Diretor Comercial', 'Proprietário',
        'Sócio-diretor', 'CEO', 'Gerente Administrativo',
        'Gerente Comercial', 'Gerente de Operações',
    ]
    cargos = list(dict.fromkeys(cargos_pri + cargos_base))

    # ── 4. Gerar termos de busca (100% focados) ──
    PADROES = [
        '{seg} {loc} contato site:.com.br',
        '{seg} {loc} telefone email',
        '{seg} {loc} quem somos',
        'empresas de {seg} {loc}',
        '{seg} {loc} endereço telefone',
        '{seg} {loc} CNPJ contato',
        'lista {seg} {loc}',
        'diretório {seg} {loc}',
    ]

    termos = set()
    for seg in segmentos:
        n_cids = min(6, len(cidades))
        cids = random.sample(cidades, n_cids)
        for cid in cids:
            pat = random.choice(PADROES)
            termos.add(pat.format(seg=seg, loc=cid))
        ufs = random.sample(estados, min(3, len(estados)))
        for uf in ufs:
            termos.add(f'{seg} {uf} contato site:.com.br')

    while len(termos) < 130:
        seg = random.choice(segmentos)
        loc = random.choice(cidades + estados)
        pat = random.choice(PADROES)
        termos.add(pat.format(seg=seg, loc=loc))

    lista = list(termos)
    random.shuffle(lista)
    return {'termos': lista, 'cargos': cargos}
"""

new_lines = lines[:start] + [NEW_BODY + '\n'] + lines[end+1:]
with open('app.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print(f'OK - replaced lines {start+1}-{end+1}')
