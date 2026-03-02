# -*- coding: utf-8 -*-
"""
Robô Comercial Pili — Equipamentos para Grãos
Tombadores e Coletores de Grãos para Cerealistas e Cooperativas
"""

import os

# =============================================================================
# CREDENCIAIS
# =============================================================================
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

DEMO_CAL_LINK = os.environ.get(
    'DEMO_CAL_LINK',
    'https://calendar.app.google/SEU_LINK_AQUI'
)

# =============================================================================
# LIMITES DIÁRIOS
# =============================================================================
MAX_BUSCAS_DIA = 80
MAX_WHATSAPP_DIA = 60
MAX_ENRIQUECIMENTOS_DIA = 150

WARMUP = {1: 15, 2: 25, 3: 35, 4: 45, 5: 50, 6: 55, 7: 60}

FOLLOWUP1_DIAS = 4
FOLLOWUP2_DIAS = 10

# =============================================================================
# INTERVALOS (anti-ban)
# =============================================================================
INTERVALO_MSG_MIN = 35
INTERVALO_MSG_MAX = 100
PAUSA_LONGA_A_CADA = 12
PAUSA_LONGA_MIN = 150
PAUSA_LONGA_MAX = 360

INTERVALO_BUSCA_MIN = 4
INTERVALO_BUSCA_MAX = 10
INTERVALO_SITE_MIN = 2
INTERVALO_SITE_MAX = 6

HORARIO_INICIO = 7
HORARIO_FIM = 18
DIAS_ATIVOS = [0, 1, 2, 3, 4]

# =============================================================================
# TERMOS DE BUSCA — Cerealistas, cooperativas e silos de grãos
# =============================================================================
TERMOS_BUSCA = [
    # Cerealistas e compra de grãos
    'cerealista site:.com.br whatsapp contato',
    'cerealista compra graos site:.com.br telefone',
    'compra venda graos site:.com.br whatsapp',
    'recebimento graos soja milho site:.com.br contato',

    # Cooperativas agrícolas
    'cooperativa agricola site:.com.br whatsapp',
    'cooperativa graos soja site:.com.br contato',
    'cooperativa armazenagem site:.com.br telefone',

    # Silos e armazéns
    'silo armazenagem graos site:.com.br contato',
    'armazem agricola site:.com.br whatsapp',
    'unidade recebimento graos site:.com.br',

    # Por estado — cinturão de grãos
    'cerealista Mato Grosso MT telefone whatsapp',
    'cerealista Parana PR site:.com.br contato',
    'cerealista Rio Grande do Sul RS telefone',
    'cooperativa agricola Goias GO whatsapp',
    'cerealista Mato Grosso do Sul MS contato',
    'cooperativa graos Minas Gerais MG telefone',

    # Equipamentos para grãos
    'tombador graos caminhonete comprar',
    'coletor graos equipamento site:.com.br',
    'equipamento descarga graos site:.com.br',
    'descarregamento graos soja milho equipamento',

    # Transportadoras e fazendas
    'transportadora graos site:.com.br whatsapp',
    'fazenda producao soja milho MT PR GO site:.com.br',
    'produtor rural graos site:.com.br contato',

    # Diretórios
    'lista cerealistas MT MS GO PR RS telefone',
    'diretorio cooperativas agricolas Brasil',
    'cerealista "fale conosco" OR "whatsapp" soja milho',
]

# =============================================================================
# CNAEs ALVO — Agronegócio e Comércio de Grãos
# =============================================================================
CNAES_ALVO = {
    '01': 'Agricultura e Pecuária',
    '011': 'Cultivo de Cereais',
    '462': 'Comércio de Cereais',
    '463': 'Comércio de Matérias-primas Agrícolas',
    '521': 'Armazéns Gerais',
    '522': 'Depósito de Mercadorias',
    '281': 'Fabricação de Máquinas Agrícolas',
    '493': 'Transporte de Cargas',
}

ESTADOS_PRIORIDADE = ['MT', 'MS', 'GO', 'PR', 'RS', 'MG', 'SP', 'BA']

# =============================================================================
# QUALIFICAÇÃO
# =============================================================================
SCORE_TEM_WHATSAPP = 30
SCORE_TEM_EMAIL = 10
SCORE_TEM_SITE = 10
SCORE_CNAE_INDUSTRIAL = 25
SCORE_PORTE_MEDIO_GRANDE = 15
SCORE_MINIMO = 30

PALAVRAS_POSITIVAS = [
    'graos', 'grãos', 'soja', 'milho', 'trigo', 'cerealista',
    'cooperativa', 'armazem', 'armazém', 'silo', 'recebimento',
    'tombador', 'coletor', 'descarga', 'producao', 'produção',
    'fazenda', 'rural', 'agricola', 'agrícola', 'agro',
]

PALAVRAS_NEGATIVAS = ['encerrada', 'baixada', 'inativa', 'falência']

# =============================================================================
# MENSAGENS WHATSAPP — Tombadores e Coletores de Grãos
# =============================================================================
MENSAGENS = {
    'inicial': [
        """Olá! Sou da equipe Pili Equipamentos. 👋

Vi que vocês atuam com {segmento} e gostaria de apresentar nossos tombadores e coletores de grãos.

✅ Reduz perda de grãos no recebimento
✅ Aumenta produtividade no descarregamento
✅ ROI em menos de 1 safra

Posso enviar mais detalhes ou agendar uma visita técnica?
📅 {cal_link} 😊""",

        """Oi! Tudo bem? Sou da Pili Equipamentos. 😊

Trabalhamos com tombadores e coletores de grãos para {segmento} e queria apresentar nossa solução.

🌾 Tombadores para caminhonetes e carretas
🌾 Coletores de varredura — zero desperdício
🌾 Manutenção simples, durabilidade comprovada

Posso te mandar mais informações? Ou agendar uma demonstração:
📅 {cal_link}""",

        """Olá! 👋 Aqui é da Pili Equipamentos.

Vocês trabalham com {segmento}? Temos tombadores e coletores de grãos que podem reduzir suas perdas e agilizar o recebimento.

📦 Entrega para todo o Brasil
🔧 Assistência técnica especializada
💰 Condições especiais para cooperativas e cerealistas

Teria interesse em conhecer? 📅 {cal_link}""",
    ],

    'interesse': """Ótimo! Fico feliz com seu interesse. 🌾

Aqui estão mais informações sobre nossos equipamentos:

🔹 **Tombador de Grãos**: Para caminhonetes e carretas, capacidade de até X toneladas
🔹 **Coletor de Grãos**: Varredura completa, mínimo desperdício

📅 Agende uma visita técnica ou demo online: {cal_link}

Prefere que eu mande o catálogo completo? É só me dizer! 😊""",

    'demo_proposta': """Que ótimo que topou uma demonstração! 😊

📅 Agende aqui sua visita técnica ou demo online:
{cal_link}

Na demonstração mostramos:
✅ Funcionamento do tombador na prática
✅ Cálculo de ROI para sua operação
✅ Condições comerciais e prazo de entrega

Nos vemos em breve! 🚜""",

    'demo_confirmada': """Perfeito! Demonstração confirmada. 🎉

Vou te mandar o link do Google Meet (ou confirmar a visita técnica) no dia agendado.

Qualquer dúvida antes disso, é só chamar aqui. Até lá! 😊""",

    'followup1': """Oi! Passando para saber se conseguiu ver as informações sobre nossos tombadores e coletores. 😊

Se quiser uma demonstração rápida (20 min online!), é só agendar:
📅 {cal_link}

Posso te ajudar com mais informações?""",

    'followup2': """Olá! Última mensagem, prometo! 😅

Trabalhamos com muitas cerealistas e cooperativas que reduziram perdas em mais de 30% com nossos equipamentos.

Se quiser conhecer melhor, agende aqui:
📅 {cal_link}

Obrigado pela atenção! 🙏""",
}

# =============================================================================
# BANCO DE DADOS (PostgreSQL — Neon)
# =============================================================================
DATABASE_URL = os.environ.get('DATABASE_URL', '')
DB_SCHEMA = 'pili'  # schema exclusivo deste bot no Neon

# =============================================================================
# API CNPJ
# =============================================================================
CNPJ_API_URL = 'https://receitaws.com.br/v1/cnpj/{cnpj}'
CNPJ_API_DELAY = 21
