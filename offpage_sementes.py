# -*- coding: utf-8 -*-
"""Off-page: alvos de link (tabela alvos_link), textos de diretório e pautas
de artigo de convidado (tabela pecas_offpage). Nada é enviado: o dono
dispara pelo painel. Endereços conferidos por acesso em 26/11/2026.
"""

ATIVOS = {
    'relatorio': ('Relatório de empresas ativas no Brasil, com gráficos para incorporar (link de atribuição)',
                  '/dados/empresas-ativas-no-brasil'),
    'ferramentas': ('Ferramentas grátis de prospecção (lista de empresas, diagnóstico, calculadoras)', '/ferramentas'),
    'cnae': ('Consulta de CNAE com descrição do IBGE e empresas ativas por estado', '/cnae'),
    'glossario': ('Glossário de vendas B2B com exemplo prático em cada termo', '/glossario'),
    'lgpd': ('LGPD na prospecção B2B, artigo por artigo, com o texto oficial', '/lgpd'),
    'perfil': ('Perfil do produto com descrição, preços e capturas de tela', '/'),
}

_T = []


def _a(nome, url, tipo, pagina, ativo):
    _T.append({'nome': nome, 'url': url, 'tipo': tipo, 'pagina': pagina, 'ativo': ativo})


# Diretórios de software e de startups
for nome, url in [('B2B Stack', 'https://www.b2bstack.com.br'), ('Capterra Brasil', 'https://www.capterra.com.br'),
                  ('GetApp Brasil', 'https://www.getapp.com.br'), ('G2', 'https://www.g2.com'),
                  ('SaaSHub', 'https://www.saashub.com'), ('AlternativeTo', 'https://alternativeto.net'),
                  ('Product Hunt', 'https://www.producthunt.com'), ('Crunchbase', 'https://www.crunchbase.com'),
                  ('SourceForge', 'https://sourceforge.net'),
                  ('Reclame Aqui', 'https://www.reclameaqui.com.br'), ('TabNews', 'https://www.tabnews.com.br')]:
    _a(nome, url, 'diretório de software', 'categoria de prospecção / geração de leads / CRM', 'perfil')

# Sebrae: nacional e estaduais (páginas de conteúdo e ferramentas para empreendedores)
_a('Sebrae', 'https://sebrae.com.br', 'apoio a pequenas empresas', 'conteúdo de vendas e ferramentas para empreender', 'ferramentas')
for uf in ['ac', 'al', 'ap', 'am', 'ba', 'ce', 'df', 'es', 'go', 'ma', 'mt', 'ms', 'mg', 'pa', 'pb', 'pr', 'pe', 'pi',
           'rj', 'rn', 'rs', 'ro', 'rr', 'sc', 'sp', 'se', 'to']:
    _a(f'Sebrae {uf.upper()}', f'https://sebrae.com.br/sites/PortalSebrae/ufs/{uf}', 'apoio a pequenas empresas',
       'materiais e ferramentas para pequenas empresas do estado', 'relatorio')

# Indústria: CNI e federações estaduais (dados do setor por estado)
for nome, url in [('CNI / Portal da Indústria', 'https://www.portaldaindustria.com.br'),
                  ('FIERGS', 'https://www.fiergs.org.br'), ('FIESC', 'https://fiesc.com.br'),
                  ('FIEP (Sistema Fiep)', 'https://www.sistemafiep.org.br'), ('FIESP', 'https://www.fiesp.com.br'),
                  ('FIEMG', 'https://www.fiemg.com.br'), ('Firjan', 'https://www.firjan.com.br'),
                  ('FIEB', 'https://www.fieb.org.br'), ('Sistema FIEG', 'https://sistemafieg.org.br'),
                  ('FIEMT', 'https://www.fiemt.ind.br'), ('FIEMS', 'https://www.fiems.com.br'),
                  ('Sistema FIEC', 'https://www.sfiec.org.br'), ('FIEPE', 'https://www.fiepe.org.br'),
                  ('Findes', 'https://findes.com.br'), ('FIEPA', 'https://www.fiepa.org.br'),
                  ('FIEAM', 'https://www.fieam.org.br'), ('FIERN', 'https://www.fiern.org.br'),
                  ('FIEPB', 'https://fiepb.org.br'), ('FIEA (Alagoas)', 'https://www.fiea.org.br'),
                  ('FIES (Sergipe)', 'https://www.fies.org.br'), ('FIEPI', 'https://www.fiepi.com.br'),
                  ('FIEMA', 'https://www.fiema.org.br'), ('FIETO', 'https://www.fieto.com.br'),
                  ('FIERO', 'https://www.fiero.org.br')]:
    _a(nome, url, 'federação das indústrias', 'notícias e dados da indústria do estado', 'relatorio')

# Representantes comerciais e comércio
for nome, url in [('CONFERE (Conselho Federal dos Representantes Comerciais)', 'https://confere.org.br'),
                  ('CORE-RS', 'https://www.core-rs.org.br'), ('CORE-SC', 'https://coresc.org.br'),
                  ('CORE-PR', 'https://www.corepr.org.br'), ('CORE-SP', 'https://core-sp.org.br'),
                  ('CORE-MG', 'https://coremg.org.br'), ('CORE-RJ', 'https://core-rj.org.br'),
                  ('Federasul', 'https://www.federasul.com.br'), ('Associação Comercial de São Paulo', 'https://acsp.com.br'),
                  ('CNDL', 'https://www.cndl.org.br'), ('FACISC', 'https://facisc.org.br'), ('Faciap', 'https://faciap.org.br'),
                  ('CIC Caxias do Sul', 'https://www.cic-caxias.com.br')]:
    _a(nome, url, 'representantes e comércio', 'benefícios e materiais para associados', 'ferramentas')

# Tecnologia e startups
for nome, url in [('ACATE', 'https://www.acate.com.br'), ('Abstartups', 'https://abstartups.com.br'),
                  ('ABES Software', 'https://abes.com.br'), ('Assespro', 'https://assespro.org.br'),
                  ('Softex', 'https://softex.br'), ('Brasscom', 'https://brasscom.org.br'),
                  ('Endeavor Brasil', 'https://endeavor.org.br'), ('UPF Parque', 'https://www.upf.br/upfparque')]:
    _a(nome, url, 'tecnologia e startups', 'conteúdo para empreendedores e associados', 'ferramentas')

# Universidades (bibliotecas de dados e disciplinas de vendas/marketing)
for nome, url in [('UFRGS', 'https://www.ufrgs.br'), ('UPF', 'https://www.upf.br'), ('UFSC', 'https://ufsc.br'),
                  ('UFPR', 'https://www.ufpr.br'), ('FEA-USP', 'https://www.fea.usp.br'), ('FGV', 'https://portal.fgv.br'),
                  ('PUCRS', 'https://www.pucrs.br'), ('Unisinos', 'https://www.unisinos.br'), ('Insper', 'https://www.insper.edu.br'),
                  ('UCS', 'https://www.ucs.br')]:
    _a(nome, url, 'universidade', 'guia de fontes de dados / disciplina de vendas e marketing', 'cnae')

# Dados abertos
for nome, url in [('Base dos Dados', 'https://basedosdados.org'), ('Brasil.IO', 'https://brasil.io'),
                  ('Open Knowledge Brasil', 'https://ok.org.br'), ('Escola de Dados', 'https://escoladedados.org'),
                  ('Kaggle (datasets)', 'https://www.kaggle.com')]:
    _a(nome, url, 'dados abertos', 'catálogo de bases e tutoriais', 'relatorio')

# Veículos de negócios, marketing e regionais
for nome, url, ativo in [('Pequenas Empresas & Grandes Negócios', 'https://revistapegn.globo.com', 'relatorio'),
                         ('Exame', 'https://exame.com', 'relatorio'), ('GZH', 'https://gauchazh.clicrbs.com.br', 'relatorio'),
                         ('NSC Total', 'https://www.nsctotal.com.br', 'relatorio'),
                         ('Gazeta do Povo', 'https://www.gazetadopovo.com.br', 'relatorio'),
                         ('Contábeis', 'https://www.contabeis.com.br', 'cnae'),
                         ('Startups.com.br', 'https://startups.com.br', 'ferramentas'),
                         ('Mundo do Marketing', 'https://www.mundodomarketing.com.br', 'glossario'),
                         ('Meio & Mensagem', 'https://www.meioemensagem.com.br', 'relatorio'),
                         ('Administradores.com', 'https://administradores.com.br', 'glossario'),
                         ('Revista Amanhã', 'https://amanha.com.br', 'relatorio'),
                         ('Jornal do Comércio (RS)', 'https://www.jornaldocomercio.com', 'relatorio'),
                         ('O Nacional (Passo Fundo)', 'https://www.onacional.com.br', 'relatorio'),
                         ('Consumidor Moderno', 'https://consumidormoderno.com.br', 'glossario'),
                         ('E-Commerce Brasil', 'https://www.ecommercebrasil.com.br', 'lgpd')]:
    _a(nome, url, 'veículo', 'pauta de dados de empresas por estado e setor', ativo)

ALVOS = _T


def mensagem(a):
    texto, link = ATIVOS[a['ativo']]
    url = f'https://www.turbovenda.com.br{link}?utm_source=parceiro&utm_medium=referral&utm_campaign=link-{a["nome"][:30].lower().replace(" ", "-")}'
    if a['tipo'] == 'diretório de software':
        return (f'Cadastrar o TurboVenda no {a["nome"]} (categoria: prospecção B2B / geração de leads / CRM).\n'
                f'Site no cadastro: {url}\nTexto: use a descrição do painel (peça "diretório").')
    return (f'Olá, equipe {a["nome"]}.\n\n'
            f'Sou do TurboVenda, software de prospecção B2B de Passo Fundo/RS. Publicamos {texto.lower()}, '
            'com dados abertos da Receita Federal e do IBGE, gratuito e sem cadastro.\n\n'
            f'Achei que pode ser útil para o público de vocês ({a["pagina"]}). O material está em {url} '
            'e pode ser citado ou incorporado com o link de atribuição.\n\n'
            'Se fizer sentido, posso preparar um recorte só do estado ou do setor de vocês.\n\nObrigado!')


DIRETORIOS = [
    {'nome': 'LinkedIn: página da empresa', 'url': 'https://www.linkedin.com/company/setup/new/'},
    {'nome': 'B2B Stack', 'url': 'https://www.b2bstack.com.br'}, {'nome': 'G2', 'url': 'https://www.g2.com'},
    {'nome': 'Capterra Brasil', 'url': 'https://www.capterra.com.br'}, {'nome': 'GetApp Brasil', 'url': 'https://www.getapp.com.br'},
    {'nome': 'Portal da Indústria Gaúcha (FIERGS)', 'url': 'https://www.fiergs.org.br'},
    {'nome': 'CORE-RS', 'url': 'https://www.core-rs.org.br'}, {'nome': 'Sebrae Startups', 'url': 'https://sebrae.com.br'},
    {'nome': 'UPF Parque', 'url': 'https://www.upf.br/upfparque'}, {'nome': 'Product Hunt', 'url': 'https://www.producthunt.com'},
    {'nome': 'Abstartups', 'url': 'https://abstartups.com.br'}, {'nome': 'ACATE', 'url': 'https://www.acate.com.br'},
    {'nome': 'AlternativeTo', 'url': 'https://alternativeto.net'}, {'nome': 'SaaSHub', 'url': 'https://www.saashub.com'},
    {'nome': 'Crunchbase', 'url': 'https://www.crunchbase.com'}, {'nome': 'Bing Places', 'url': 'https://www.bingplaces.com'},
    {'nome': 'TabNews', 'url': 'https://www.tabnews.com.br'}, {'nome': 'Reclame Aqui', 'url': 'https://www.reclameaqui.com.br'},
]

CURTA = ('Prospecção B2B com IA: encontre empresas na base pública da Receita, com telefone, e-mail e sócio, e faça o '
         'primeiro contato. Teste grátis com 50 leads.')
LONGA = ('O TurboVenda é um software brasileiro de prospecção B2B para quem vende para outras empresas: donos de PME, '
         'gerentes comerciais e representantes comerciais. Ele encontra empresas do seu perfil na base de dados abertos '
         'do CNPJ da Receita Federal e em buscadores, completa telefone, e-mail, CNPJ e o sócio que decide a compra, e faz '
         'o primeiro contato por e-mail e WhatsApp com mensagens escritas por IA. Os leads ficam num CRM em Kanban. '
         'Teste grátis com 50 leads, sem cartão; Starter a R$ 97/mês e Pro a R$ 297/mês. No site há ferramentas grátis, '
         'sem login: lista de empresas, consulta de CNAE, diagnóstico de prospecção e calculadoras. Desenvolvido pela '
         'AndersTech, de Passo Fundo/RS.')


def texto_diretorio(p):
    slug = p['nome'].split(':')[0].strip().lower().replace(' ', '-').replace('(', '').replace(')', '')
    site = ('https://www.turbovenda.com.br/ferramentas/lista-de-empresas?utm_source=diretorio&utm_medium=diretorio'
            f'&utm_campaign={slug}')
    return (f'Onde: {p["url"]}\nNome: TurboVenda\nEmpresa: AndersTech (Passo Fundo/RS)\n'
            'Categorias: Prospecção B2B, Geração de leads, CRM de vendas, Base de dados de empresas\n'
            f'Site: {site}\nTeste grátis: https://www.turbovenda.com.br/cadastro?utm_source=diretorio&utm_medium=diretorio'
            f'&utm_campaign={slug}\nPreço: teste grátis com 50 leads; Starter R$ 97/mês; Pro R$ 297/mês\n\n'
            f'Descrição curta:\n{CURTA}\n\nDescrição longa:\n{LONGA}')


ARTIGOS_CONVIDADO = [
    {'titulo': 'Quantas empresas ativas existem em cada estado, e o que isso muda para quem vende B2B',
     'veiculo': 'Pequenas Empresas & Grandes Negócios', 'link': 'https://www.turbovenda.com.br/dados/empresas-ativas-no-brasil'},
    {'titulo': 'Como montar uma lista de clientes B2B com os dados abertos da Receita',
     'veiculo': 'Contábeis', 'link': 'https://www.turbovenda.com.br/ferramentas/lista-de-empresas'},
    {'titulo': 'Representante comercial: como prospectar sem comprar lista',
     'veiculo': 'CORE-RS (boletim)', 'link': 'https://www.turbovenda.com.br/ferramentas/gerador-de-icp'},
    {'titulo': 'O que o CNAE de uma empresa revela para o seu time de vendas',
     'veiculo': 'Startups.com.br', 'link': 'https://www.turbovenda.com.br/cnae'},
    {'titulo': 'Onde estão as indústrias do Rio Grande do Sul, e como falar com quem decide',
     'veiculo': 'Revista Amanhã', 'link': 'https://www.turbovenda.com.br/empresas'},
    {'titulo': 'Cinco contas que todo gerente comercial deveria fazer antes de contratar mais vendedores',
     'veiculo': 'Endeavor Brasil', 'link': 'https://www.turbovenda.com.br/ferramentas/calculadora-de-cac'},
    {'titulo': 'Primeira mensagem para outra empresa: como escrever sem parecer spam',
     'veiculo': 'Mundo do Marketing', 'link': 'https://www.turbovenda.com.br/modelos'},
    {'titulo': 'Dados abertos do CNPJ na prática: um guia para pequenas empresas',
     'veiculo': 'Base dos Dados (blog)', 'link': 'https://www.turbovenda.com.br/dados/empresas-ativas-no-brasil'},
    {'titulo': 'Prospecção no agro: como distribuidoras e cooperativas podem usar dados públicos',
     'veiculo': 'GZH (Campo e Lavoura)', 'link': 'https://www.turbovenda.com.br/empresas'},
    {'titulo': 'LGPD na prospecção B2B: o básico que toda pequena empresa precisa saber',
     'veiculo': 'Administradores.com', 'link': 'https://www.turbovenda.com.br/ferramentas/checklist-lgpd-prospeccao'},
]
