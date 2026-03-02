# -*- coding: utf-8 -*-
"""
Sistema de Mensagens com IA - PrismaBiz
Funil: inicial (com links) → resposta → proposta de demo → agendamento
"""

import re
import random

from config import MENSAGENS, ANTHROPIC_API_KEY, DEMO_CAL_LINK

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False


class GeradorMensagens:
    """Gera mensagens personalizadas com IA — funil completo"""

    def __init__(self):
        self.ai_client = None
        if HAS_ANTHROPIC and ANTHROPIC_API_KEY:
            self.ai_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            print("  [OK] Claude AI conectado para personalização")
        else:
            print("  [!] Sem IA - usando templates fixos")
            if not ANTHROPIC_API_KEY:
                print("      Configure ANTHROPIC_API_KEY no ambiente")

    # =========================================================================
    # MENSAGEM INICIAL (sempre com ambos os links)
    # =========================================================================

    def gerar_inicial(self, lead):
        """Gera mensagem inicial com link de cadastro + link de agendamento"""
        segmento = self._detectar_segmento(lead)

        if self.ai_client:
            msg = self._gerar_inicial_ia(lead, segmento)
            if msg:
                return msg

        # Fallback: template com ambos os links
        template = random.choice(MENSAGENS['inicial'])
        return template.format(segmento=segmento, cal_link=DEMO_CAL_LINK)

    def _gerar_inicial_ia(self, lead, segmento):
        """Gera mensagem inicial usando Claude — sempre inclui ambos os links"""
        try:
            info = (
                f"Empresa: {lead.get('nome_fantasia', 'N/A')}\n"
                f"Segmento: {lead.get('segmento', segmento)}\n"
                f"Porte: {lead.get('porte', 'N/A')}\n"
                f"Cidade: {lead.get('cidade', 'N/A')}, "
                f"{lead.get('estado', 'N/A')}\n"
            )

            response = self.ai_client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=400,
                system=f"""Você é a Ana, vendedora do PrismaBiz (gestão da qualidade).

SOBRE O PRISMABIZ:
- 11 ferramentas GRÁTIS: Plano de Ação 5W2H, Auditoria Interna, SWOT, PDCA, Canvas, etc
- Plano PRO: R$59,90/mês com Indicadores KPI, Documentos, RH
- Cadastro: prismabiz.com.br/cadastro
- Demo: {DEMO_CAL_LINK}

REGRAS DA MENSAGEM:
1. Máximo 6 linhas (WhatsApp é rápido)
2. Comece com "Olá!" ou "Oi!"
3. Mencione o segmento da empresa
4. OBRIGATÓRIO: inclua o link de cadastro (prismabiz.com.br/cadastro)
5. OBRIGATÓRIO: inclua o link de agendamento ({DEMO_CAL_LINK})
6. Termine com pergunta ou convite para demo
7. Use 1-2 emojis no máximo
8. Seja simpática mas profissional
9. Retorne APENAS a mensagem, sem aspas""",
                messages=[{
                    "role": "user",
                    "content": f"Crie mensagem inicial de WhatsApp:\n{info}"
                }]
            )

            msg = response.content[0].text.strip()
            if msg.startswith('"') and msg.endswith('"'):
                msg = msg[1:-1]
            return msg

        except Exception as e:
            print(f"    [IA] Erro inicial: {e}")
            return None

    # =========================================================================
    # RESPOSTA INTELIGENTE (detecta estágio e age adequadamente)
    # =========================================================================

    def gerar_resposta(self, lead, mensagem_recebida, historico=None,
                       estagio='inicial'):
        """
        Gera resposta baseada na mensagem e no estágio da conversa.
        estagio: 'inicial' | 'demo_proposta' | 'demo_confirmada'
        """
        intencao = self.detectar_intencao(mensagem_recebida, estagio)

        if self.ai_client:
            resposta = self._gerar_resposta_ia(
                lead, mensagem_recebida, historico, intencao, estagio
            )
            if resposta:
                return resposta, intencao

        # Fallback por intenção
        return self._resposta_fallback(intencao, estagio), intencao

    def _gerar_resposta_ia(self, lead, mensagem_recebida, historico,
                            intencao, estagio):
        """Gera resposta usando Claude — consciente do estágio do funil"""
        try:
            contexto = ""
            if historico:
                for msg in historico[-5:]:
                    quem = "Lead" if msg.get('tipo') == 'recebida' else "Você"
                    contexto += f"{quem}: {msg.get('texto', '')}\n"

            instrucao_estagio = {
                'inicial': (
                    "Se tiver interesse: envie links de cadastro "
                    "(prismabiz.com.br/cadastro) E de agendamento "
                    f"({DEMO_CAL_LINK}). Proponha demo de 20 min."
                ),
                'demo_proposta': (
                    "O lead já recebeu o link da demo. "
                    "Confirme o agendamento ou tire dúvidas sobre a demo."
                ),
                'demo_confirmada': (
                    "Demo confirmada. Seja calorosa, confirme data/hora "
                    "e diga que mandará o link do Meet."
                ),
            }.get(estagio, '')

            response = self.ai_client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=400,
                system=f"""Você é a Ana, vendedora do PrismaBiz.

SOBRE O PRISMABIZ:
- 11 ferramentas GRÁTIS + PRO R$59,90/mês
- Cadastro: prismabiz.com.br/cadastro
- Demo (20 min): {DEMO_CAL_LINK}

REGRAS:
1. Seja natural, como WhatsApp real — máximo 5 linhas
2. NUNCA diga que é robô ou IA
3. Se perguntarem nome: "Sou a Ana, do comercial"
4. Nível de intenção detectado: {intencao['nivel']} ({intencao.get('sinal', '-')})
5. {instrucao_estagio}
6. Use 1-2 emojis máximo
7. Retorne APENAS a mensagem""",
                messages=[{
                    "role": "user",
                    "content": (
                        f"Histórico:\n{contexto}\n"
                        f"Lead respondeu: \"{mensagem_recebida}\"\n\n"
                        "Responda:"
                    )
                }]
            )

            msg = response.content[0].text.strip()
            if msg.startswith('"') and msg.endswith('"'):
                msg = msg[1:-1]
            return msg

        except Exception as e:
            print(f"    [IA] Erro resposta: {e}")
            return None

    def _resposta_fallback(self, intencao, estagio):
        """Templates de fallback por intenção"""
        nivel = intencao['nivel']

        if nivel in ('alta', 'demo'):
            return MENSAGENS['interesse'].format(cal_link=DEMO_CAL_LINK)

        if nivel == 'agendamento':
            return MENSAGENS['demo_proposta'].format(cal_link=DEMO_CAL_LINK)

        if nivel == 'confirmacao':
            return MENSAGENS['demo_confirmada']

        if nivel == 'media':
            return (
                "O PrismaBiz é um sistema de gestão da qualidade online.\n\n"
                "Você pode usar 11 ferramentas de graça:\n"
                "- Plano de Ação 5W2H\n"
                "- Auditoria Interna\n"
                "- Análise SWOT e PDCA\n\n"
                f"Crie sua conta: prismabiz.com.br/cadastro\n"
                f"Ou veja ao vivo (20 min): {DEMO_CAL_LINK} 😊"
            )

        if nivel == 'baixa':
            return (
                "Entendo! Sem problemas. 🙂\n\n"
                "Se precisar de algo no futuro, estarei aqui.\n"
                "O PrismaBiz sempre terá opção gratuita. Obrigada! 🙏"
            )

        # neutra
        return (
            "Posso te ajudar com mais alguma dúvida?\n\n"
            f"Conta grátis: prismabiz.com.br/cadastro\n"
            f"Demo de 20 min: {DEMO_CAL_LINK} 😊"
        )

    # =========================================================================
    # PROPOSTA DE DEMO
    # =========================================================================

    def gerar_proposta_demo(self, lead):
        """Mensagem específica para propor agendamento de demonstração"""
        if self.ai_client:
            try:
                nome = lead.get('nome_fantasia', 'vocês')
                response = self.ai_client.messages.create(
                    model="claude-3-haiku-20240307",
                    max_tokens=300,
                    system=f"""Você é a Ana, do PrismaBiz.
O lead demonstrou interesse. Sua missão agora é convencer a agendar
uma demonstração de 20 minutos.

Link de agendamento: {DEMO_CAL_LINK}

REGRAS:
- Máximo 4 linhas
- Mencione que é rápido (20 minutos)
- Inclua o link {DEMO_CAL_LINK}
- 1 emoji máximo
- Retorne APENAS a mensagem""",
                    messages=[{
                        "role": "user",
                        "content": (
                            f"Empresa: {nome}\n"
                            "Proponha agendamento de demo:"
                        )
                    }]
                )
                msg = response.content[0].text.strip()
                if msg.startswith('"') and msg.endswith('"'):
                    msg = msg[1:-1]
                return msg
            except Exception as e:
                print(f"    [IA] Erro demo: {e}")

        return MENSAGENS['demo_proposta'].format(cal_link=DEMO_CAL_LINK)

    # =========================================================================
    # FOLLOW-UP
    # =========================================================================

    def gerar_followup(self, lead, numero=1):
        """Gera mensagem de follow-up com link de agendamento"""
        key = f'followup{numero}'
        template = MENSAGENS.get(key, '')
        if template:
            return template.format(cal_link=DEMO_CAL_LINK)
        return None

    # =========================================================================
    # DETECÇÃO DE INTENÇÃO
    # =========================================================================

    def detectar_intencao(self, mensagem, estagio='inicial'):
        """
        Detecta intenção do lead. Retorna dict com:
        - nivel: 'alta' | 'demo' | 'agendamento' | 'confirmacao' | 'media' | 'baixa' | 'neutra'
        - sinal: palavra que disparou
        - acao: próxima ação recomendada
        """
        msg = mensagem.lower().strip()

        # CONFIRMAÇÃO DE AGENDAMENTO (quando demo já foi proposta)
        if estagio == 'demo_proposta':
            sinais_confirmacao = [
                'confirmado', 'agendei', 'marquei', 'ok', 'sim', 'pode ser',
                'beleza', 'combinado', 'perfeito', 'ótimo', 'claro', 'bora',
                r'\d{1,2}[/\-]\d{1,2}',   # data ex: 15/03
                r'\d{1,2}h\d{0,2}',        # hora ex: 10h ou 10h30
            ]
            for sinal in sinais_confirmacao:
                if re.search(sinal, msg):
                    return {
                        'nivel': 'confirmacao',
                        'sinal': sinal,
                        'acao': 'confirmar_demo',
                    }

        # QUER AGENDAR DEMO
        sinais_agendamento = [
            'quero demo', 'quero agendar', 'agendar', 'demonstracao',
            'demonstração', 'ver o sistema', 'reuniao', 'reunião',
            'call', 'video', 'vídeo', 'apresentacao', 'apresentação',
            'quero ver', 'pode apresentar',
        ]
        for sinal in sinais_agendamento:
            if sinal in msg:
                return {
                    'nivel': 'demo',
                    'sinal': sinal,
                    'acao': 'propor_agendamento',
                }

        # ALTA INTENÇÃO DE COMPRA
        sinais_quentes = [
            'quero', 'me manda', 'manda o link', 'pode mandar', 'envia',
            'interessado', 'tenho interesse', 'gostei', 'quanto custa',
            'qual o preco', 'qual o preço', 'valor', 'preco', 'preço',
            'vamos conversar', 'pode ligar', 'me liga',
            'sim', 'claro', 'pode ser', 'beleza', 'bora',
            'como funciona', 'quero saber mais', 'me explica',
            'tem como', 'quero testar', 'quero conhecer',
        ]
        for sinal in sinais_quentes:
            if sinal in msg:
                return {
                    'nivel': 'alta',
                    'sinal': sinal,
                    'acao': 'enviar_links',
                }

        # INTENÇÃO MÉDIA (curioso)
        sinais_medios = [
            'o que e', 'o que é', 'como assim', 'explica',
            'nao entendi', 'não entendi', 'o que faz',
            'bom dia', 'boa tarde', 'boa noite', 'oi', 'ola', 'olá',
            'quem é', 'de onde', 'por que', 'porque',
        ]
        for sinal in sinais_medios:
            if sinal in msg:
                return {
                    'nivel': 'media',
                    'sinal': sinal,
                    'acao': 'explicar',
                }

        # DESINTERESSE
        sinais_frios = [
            'nao', 'não', 'sem interesse', 'nao quero', 'não quero',
            'para', 'parar', 'remove', 'cancela', 'bloquear',
            'spam', 'chato', 'para de', 'ja tenho', 'já tenho',
            'nao preciso', 'não preciso', 'obrigado mas',
        ]
        for sinal in sinais_frios:
            if sinal in msg:
                return {
                    'nivel': 'baixa',
                    'sinal': sinal,
                    'acao': 'encerrar',
                }

        return {'nivel': 'neutra', 'sinal': None, 'acao': 'continuar'}

    # =========================================================================
    # UTILIDADES
    # =========================================================================

    def _detectar_segmento(self, lead):
        """Detecta segmento do lead para personalizar mensagem"""
        texto = (
            f"{lead.get('nome_fantasia', '')} "
            f"{lead.get('segmento', '')} "
            f"{lead.get('razao_social', '')}"
        ).lower()

        segmentos = {
            'metalúrgica': [
                'metalurgica', 'metalurgia', 'usinagem', 'ferramentaria',
                'caldeiraria', 'fundicao', 'fundição',
            ],
            'indústria de plásticos': [
                'plastico', 'plástico', 'injecao', 'injeção',
                'extrusao', 'extrusão',
            ],
            'indústria alimentícia': [
                'alimento', 'alimenticia', 'frigorifico', 'frigorífico',
                'laticinios', 'laticínios', 'bebida',
            ],
            'autopeças': ['autopecas', 'autopeças', 'automotivo', 'sistemista'],
            'indústria química': ['quimica', 'química', 'tinta', 'cosmetico', 'cosmético'],
            'indústria': [
                'industria', 'indústria', 'fabrica', 'fábrica',
                'manufatura', 'producao', 'produção',
            ],
        }

        for nome_seg, palavras in segmentos.items():
            for palavra in palavras:
                if palavra in texto:
                    return nome_seg

        if lead.get('segmento'):
            return lead['segmento'][:50]

        return 'seu segmento'
