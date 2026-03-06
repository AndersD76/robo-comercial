# -*- coding: utf-8 -*-
"""
Robô Comercial Prima — PrismaBiz
Configurações do agente de prospecção WhatsApp
"""

import os

# =============================================================================
# CREDENCIAIS
# =============================================================================
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

# LinkedIn — variáveis de ambiente ou arquivo linkedin_creds.json (dashboard)
LINKEDIN_EMAIL    = os.environ.get('LINKEDIN_EMAIL', '')
LINKEDIN_PASSWORD = os.environ.get('LINKEDIN_PASSWORD', '')

# Lê credenciais do arquivo local se existir (salvo pelo dashboard)
_creds_file = os.path.join(os.path.dirname(__file__), 'linkedin_creds.json')
if os.path.exists(_creds_file):
    try:
        import json as _json
        _creds = _json.load(open(_creds_file, encoding='utf-8'))
        LINKEDIN_EMAIL    = _creds.get('email', LINKEDIN_EMAIL)
        LINKEDIN_PASSWORD = _creds.get('password', LINKEDIN_PASSWORD)
    except Exception:
        pass

# Limites diários LinkedIn (anti-ban)
LINKEDIN_MAX_CONEXOES_DIA  = int(os.environ.get('LINKEDIN_MAX_CONEXOES', '20'))
LINKEDIN_MAX_MENSAGENS_DIA = int(os.environ.get('LINKEDIN_MAX_MSGS', '15'))

# Cargos-alvo para prospecção LinkedIn — gestão da qualidade
LINKEDIN_CARGOS_ALVO = [
    # Qualidade (foco principal)
    'qualidade', 'quality', 'SGQ', 'gestão da qualidade',
    'gerente de qualidade', 'coordenador de qualidade',
    'responsável pela qualidade', 'supervisor de qualidade',
    'analista de qualidade', 'engenheiro de qualidade',
    'head of quality', 'quality manager', 'quality engineer',
    # Normas / melhoria contínua
    'auditor interno', 'auditor de qualidade', 'melhoria contínua',
    'lean manufacturing', 'six sigma', 'gestão de processos',
    # Produção / operações (termos compostos para evitar falsos positivos)
    'diretor industrial', 'gerente industrial', 'gerente de produção',
    'gerente de operações', 'coordenador de produção',
    'supervisor de produção', 'diretor de operações',
    'engenheiro de processos', 'gerente de fábrica',
    'diretor de fábrica', 'gerente de processos industriais',
]

# Termos de busca LinkedIn — empresas industriais / ISO 9001
LINKEDIN_TERMOS_BUSCA = [
    # Qualidade + setores
    'gerente qualidade metalurgica',
    'coordenador SGQ industria',
    'responsavel qualidade fabrica',
    'gerente qualidade ISO 9001',
    'quality manager manufacturing Brazil',
    'gerente qualidade usinagem',
    'coordenador qualidade industria alimentos',
    'analista qualidade industria',
    'gestor qualidade fabrica',
    'gerente producao industria ISO',
    # Setores específicos
    'gerente qualidade autopeças',
    'coordenador qualidade farmaceutica',
    'gerente qualidade embalagens',
    'supervisor qualidade quimica',
    'gerente qualidade plasticos',
    'coordenador qualidade cosmeticos',
    'gerente qualidade textil',
    # Produção / operações
    'diretor industrial São Paulo',
    'gerente producao fabrica',
    'gerente operações industria',
    'coordenador producao metalurgica',
    'diretor industrial Minas Gerais',
    'gerente fabrica Parana',
    'diretor operações industria',
    # Regiões
    'gerente qualidade Rio Grande do Sul',
    'coordenador qualidade Santa Catarina',
    'gerente qualidade Campinas',
    'diretor industrial Curitiba',
    'gerente qualidade Joinville',
    'gerente qualidade Caxias do Sul',
    # Inglês (multinacionais)
    'quality director Brazil',
    'plant manager Brazil',
    'operations manager manufacturing Brazil',
    'continuous improvement manager Brazil',
]

# =============================================================================
# SALES NAVIGATOR (requer assinatura Sales Navigator)
# =============================================================================
SALES_NAV_HABILITADO = os.environ.get('SALES_NAV_HABILITADO', 'false').lower() == 'true'

# Filtros avançados Sales Navigator
SALES_NAV_FILTROS = {
    # Cargos para busca (títulos) — usados no filtro "Title"
    'titulos': [
        'Gerente de Qualidade', 'Coordenador de Qualidade',
        'Diretor Industrial', 'Gerente de Produção',
        'Engenheiro de Qualidade', 'Supervisor de Qualidade',
        'Gerente de Operações', 'Head of Quality',
        'Quality Manager', 'Responsável SGQ',
        'Gerente de Fábrica', 'Coordenador SGQ',
    ],
    # Indústrias — IDs do LinkedIn Sales Navigator
    # 56=Metalurgia, 53=Máquinas, 48=Alimentos, 46=Plásticos/Borracha
    # 50=Química, 42=Papel/Celulose, 57=Automotivo, 51=Embalagens
    'industrias': [
        'Metalurgia', 'Máquinas e Equipamentos', 'Alimentos',
        'Plásticos e Borracha', 'Química', 'Automotivo',
        'Embalagens', 'Fabricação', 'Manufacturing',
    ],
    # Porte da empresa (Sales Nav headcount ranges)
    # B=1-10, C=11-50, D=51-200, E=201-500, F=501-1000, G=1001-5000
    'portes': ['C', 'D', 'E', 'F'],  # 11 a 1000 funcionários
    # Geografia — IDs de regiões do LinkedIn
    'regioes': [
        'São Paulo', 'Minas Gerais', 'Paraná',
        'Santa Catarina', 'Rio Grande do Sul', 'Rio de Janeiro',
    ],
    # Nível de senioridade
    # 3=Manager, 4=Director, 5=VP, 8=CXO, 9=Owner
    'senioridade': ['3', '4', '5', '8', '9'],
}

# Termos de busca específicos para Sales Navigator (keywords)
SALES_NAV_TERMOS = [
    'qualidade ISO 9001',
    'gestão qualidade indústria',
    'SGQ metalurgia',
    'quality management manufacturing',
    'gerente qualidade fábrica',
    'coordenador SGQ',
    'melhoria contínua produção',
    'auditoria qualidade',
    'engenheiro qualidade produção',
    'diretor industrial qualidade',
]

# =============================================================================
# APOLLO.IO (API para enriquecimento e busca de leads)
# =============================================================================
APOLLO_API_KEY = os.environ.get('APOLLO_API_KEY', '')
APOLLO_HABILITADO = bool(APOLLO_API_KEY)
APOLLO_MAX_BUSCAS_DIA = int(os.environ.get('APOLLO_MAX_BUSCAS', '50'))

# Filtros Apollo.io
APOLLO_FILTROS = {
    'titulos': [
        'Gerente de Qualidade', 'Coordenador de Qualidade',
        'Diretor Industrial', 'Gerente de Produção',
        'Quality Manager', 'Engenheiro de Qualidade',
        'Supervisor de Qualidade', 'Gerente de Operações',
        'Gerente SGQ', 'Head of Quality',
    ],
    'localizacao': ['Brazil'],
    'industrias': [
        'manufacturing', 'industrial machinery',
        'automotive', 'food production', 'chemicals',
        'metals & mining', 'plastics',
    ],
    # Porte: 11-50, 51-200, 201-500, 501-1000
    'porte_min': 11,
    'porte_max': 1000,
    'palavras_chave': [
        'ISO 9001', 'qualidade', 'SGQ', 'quality management',
        'industrial', 'metalurgia', 'manufacturing',
    ],
}

# Link do Google Calendar Appointment Scheduling
DEMO_CAL_LINK = os.environ.get(
    'DEMO_CAL_LINK',
    'https://prismabiz.com.br/cadastro'
)
if 'SEU_LINK_AQUI' in DEMO_CAL_LINK:
    DEMO_CAL_LINK = 'https://prismabiz.com.br/cadastro'
    print("[CONFIG] AVISO: DEMO_CAL_LINK nao configurado — usando link de cadastro como fallback")

# =============================================================================
# LIMITES DIÁRIOS
# =============================================================================
MAX_BUSCAS_DIA = 100
MAX_WHATSAPP_DIA = 80
MAX_ENRIQUECIMENTOS_DIA = 200

WARMUP = {1: 20, 2: 30, 3: 40, 4: 50, 5: 60, 6: 70, 7: 80}

FOLLOWUP1_DIAS = 3
FOLLOWUP2_DIAS = 7

# =============================================================================
# INTERVALOS (anti-ban)
# =============================================================================
INTERVALO_MSG_MIN = 15
INTERVALO_MSG_MAX = 40
PAUSA_LONGA_A_CADA = 15
PAUSA_LONGA_MIN = 60
PAUSA_LONGA_MAX = 120

INTERVALO_BUSCA_MIN = 3
INTERVALO_BUSCA_MAX = 8
INTERVALO_SITE_MIN = 2
INTERVALO_SITE_MAX = 5

HORARIO_INICIO = 8
HORARIO_FIM = 18
DIAS_ATIVOS = [0, 1, 2, 3, 4]

# =============================================================================
# TERMOS DE BUSCA — Empresas industriais que precisam de gestão da qualidade
# =============================================================================
TERMOS_BUSCA = [
    # Metalúrgica / usinagem
    'metalurgica SP contato site:.com.br',
    'metalurgica MG contato site:.com.br',
    'metalurgica PR contato site:.com.br',
    'metalurgica RS site:.com.br telefone',
    'usinagem CNC SP site:.com.br contato',
    'usinagem CNC MG site:.com.br',
    'ferramentaria SP contato site:.com.br',
    'caldeiraria soldagem SP site:.com.br',
    # Outros segmentos industriais
    'injecao plastica SP site:.com.br contato',
    'fabrica pecas metal SP site:.com.br',
    'fabrica embalagens SP site:.com.br contato',
    'industria alimentos SP site:.com.br contato',
    'frigorifico abatedouro SP site:.com.br',
    'autopecas SP site:.com.br contato',
    'industria quimica SP site:.com.br',
    'borracha industrial SP site:.com.br',
    'tratamento superficial SP site:.com.br',
    # ISO 9001 / gestão da qualidade
    'industria ISO 9001 SP site:.com.br',
    'fabricante gestao qualidade SP site:.com.br',
    'empresa certificada ISO 9001 SP site:.com.br',
]

# =============================================================================
# CNAEs ALVO
# =============================================================================
CNAES_ALVO = {
    '10': 'Alimentos', '11': 'Bebidas', '20': 'Químicos',
    '22': 'Borracha e Plástico', '24': 'Metalurgia',
    '25': 'Produtos de Metal', '27': 'Equipamentos Elétricos',
    '28': 'Máquinas e Equipamentos', '29': 'Veículos Automotores',
}

ESTADOS_PRIORIDADE = ['SP', 'MG', 'PR', 'SC', 'RS', 'RJ']

# =============================================================================
# QUALIFICAÇÃO
# =============================================================================
SCORE_TEM_WHATSAPP = 30
SCORE_TEM_EMAIL = 10
SCORE_TEM_SITE = 10
SCORE_CNAE_INDUSTRIAL = 20
SCORE_PORTE_MEDIO_GRANDE = 20
SCORE_MINIMO = 30

PALAVRAS_POSITIVAS = [
    'iso', 'qualidade', 'certificação', 'sgq', 'auditoria',
    'indústria', 'metalúrgica', 'fabricante', 'manufatura',
    'produção', 'fábrica', 'industrial', 'usinagem',
]

PALAVRAS_NEGATIVAS = ['encerrada', 'baixada', 'inativa', 'falência']

# =============================================================================
# MENSAGENS WHATSAPP
# =============================================================================
MENSAGENS = {
    'inicial': [
        """Olá! Sou a Ana, da equipe do PrismaBiz. 👋

Vi que vocês trabalham com {segmento} e queria apresentar nosso sistema de gestão da qualidade.

✅ 11 ferramentas GRÁTIS (Plano de Ação, Auditoria, PDCA, SWOT e mais)
💡 Crie sua conta em 2 minutos: prismabiz.com.br/cadastro

Quer uma demonstração ao vivo? Só agendar aqui: {cal_link}

O que acha? 😊""",

        """Oi! Tudo bem? Sou a Ana, do PrismaBiz. 😊

Trabalho com gestão da qualidade para {segmento} e acredito que nossa plataforma pode ajudar muito vocês.

🆓 11 ferramentas gratuitas: Auditoria Interna, Plano de Ação, SWOT, Canvas e mais
👉 Acesse grátis: prismabiz.com.br/cadastro

Prefere ver ao vivo? Agende uma demo rápida: {cal_link}""",

        """Olá! 👋 Aqui é a Ana, da equipe PrismaBiz.

Vi que vocês atuam em {segmento}. Temos um sistema completo de gestão da qualidade com 11 ferramentas grátis!

🔗 Crie sua conta: prismabiz.com.br/cadastro
📅 Ou agende uma demonstração: {cal_link}

Vale 15 minutos — o que acha? 🚀""",
    ],

    'interesse': """Ótimo! 🎉

Aqui estão os links:
👉 Criar conta grátis: prismabiz.com.br/cadastro
📅 Agendar demonstração: {cal_link}

Na demo mostramos tudo em 20 minutos: Plano de Ação, Auditoria, Indicadores KPI e muito mais.

Qualquer dúvida, pode me chamar! 😊""",

    'demo_proposta': """Que ótimo que topou! 😊

📅 Agende aqui sua demonstração gratuita de 20 minutos:
{cal_link}

É só escolher o melhor horário pra você. Assim que confirmar, mando o link do Google Meet.

Nos vemos em breve! 🚀""",

    'demo_confirmada': """Perfeito! Demonstração confirmada. 🎉

Vou te mandar o link do Google Meet no dia agendado.

Qualquer dúvida antes disso, é só chamar aqui. Até lá! 😊""",

    'followup1': """Oi! Passando para saber se conseguiu ver o PrismaBiz. 😊

Se quiser uma demonstração ao vivo (só 20 min!), é só agendar:
📅 {cal_link}

Posso ajudar com alguma dúvida?""",

    'followup2': """Olá! Última mensagem, prometo! 😅

Se quiser conhecer o PrismaBiz com calma, deixei um horário reservado:
📅 {cal_link}

Obrigado pela atenção! 🙏""",
}

# =============================================================================
# BANCO DE DADOS (PostgreSQL — Neon)
# =============================================================================
_raw_db = os.environ.get('DATABASE_URL', '')
if _raw_db.startswith('psql://'):
    DATABASE_URL = 'postgresql://' + _raw_db[7:]
elif _raw_db.startswith('postgres://'):
    DATABASE_URL = 'postgresql://' + _raw_db[11:]
else:
    DATABASE_URL = _raw_db
DB_SCHEMA = 'prisma'  # schema exclusivo deste bot no Neon

# =============================================================================
# API CNPJ
# =============================================================================
CNPJ_API_URL = 'https://receitaws.com.br/v1/cnpj/{cnpj}'
CNPJ_API_DELAY = 5
