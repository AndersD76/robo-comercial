# -*- coding: utf-8 -*-
"""
Sistema de Mensagens com IA — Robô Pili
Tombadores e Coletores de Grãos para Cerealistas e Cooperativas
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
    """Gera mensagens personalizadas sobre tombadores e coletores de grãos"""

    def __init__(self):
        self.ai_client = None
        if HAS_ANTHROPIC and ANTHROPIC_API_KEY:
            self.ai_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            print("  [OK] Claude AI conectado")
        else:
            print("  [!] Sem IA - usando templates fixos")

    # =========================================================================
    # MENSAGEM INICIAL
    # =========================================================================

    def gerar_inicial(self, lead):
        """Gera mensagem inicial com links de catálogo e agendamento"""
        segmento = self._detectar_segmento(lead)

        if self.ai_client:
            msg = self._gerar_inicial_ia(lead, segmento)
            if msg:
                return msg

        template = random.choice(MENSAGENS['inicial'])
        return template.format(segmento=segmento, cal_link=DEMO_CAL_LINK)

    def _gerar_inicial_ia(self, lead, segmento):
        """Gera mensagem inicial com Claude"""
        try:
            info = (
                f"Empresa: {lead.get('nome_fantasia', 'N/A')}\n"
                f"Segmento: {lead.get('segmento', segmento)}\n"
                f"Cidade: {lead.get('cidade', 'N/A')}, {lead.get('estado', 'N/A')}\n"
            )

            response = self.ai_client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=400,
                system=f"""Você é vendedor da Pili Equipamentos, que fabrica tombadores e coletores de grãos.

SOBRE A PILI:
- Tombadores de grãos para caminhonetes e carretas
- Coletores de grãos (varredura — zero desperdício)
- Redução de perdas no recebimento
- ROI em menos de 1 safra
- Entrega para todo o Brasil
- Atende cerealistas, cooperativas, silos, fazendas
- Agendamento: {DEMO_CAL_LINK}

REGRAS:
1. Máximo 6 linhas (WhatsApp é rápido)
2. Comece com "Olá!" ou "Oi!"
3. Mencione o segmento/atividade da empresa
4. OBRIGATÓRIO: inclua o link de agendamento ({DEMO_CAL_LINK})
5. Foque em benefícios: redução de perda, produtividade, ROI
6. Use 1-2 emojis no máximo (🌾 ou 🚜 são bons)
7. Termine com pergunta ou convite para demo/visita técnica
8. Tom profissional mas amigável — público rural/agro
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
    # RESPOSTA INTELIGENTE
    # =========================================================================

    def gerar_resposta(self, lead, mensagem_recebida, historico=None,
                       estagio='inicial'):
        """Gera resposta baseada na mensagem e estágio da conversa"""
        intencao = self.detectar_intencao(mensagem_recebida, estagio)

        if self.ai_client:
            resposta = self._gerar_resposta_ia(
                lead, mensagem_recebida, historico, intencao, estagio
            )
            if resposta:
                return resposta, intencao

        return self._resposta_fallback(intencao, estagio), intencao

    def _gerar_resposta_ia(self, lead, mensagem_recebida, historico,
                            intencao, estagio):
        """Gera resposta com Claude — consciente do estágio e produto"""
        try:
            contexto = ""
            if historico:
                for msg in historico[-5:]:
                    quem = "Lead" if msg.get('tipo') == 'recebida' else "Você"
                    contexto += f"{quem}: {msg.get('texto', '')}\n"

            instrucao = {
                'inicial': (
                    "Se tiver interesse: envie link de agendamento "
                    f"({DEMO_CAL_LINK}) e proponha visita técnica ou demo online."
                ),
                'demo_proposta': "Lead já recebeu link. Confirme agendamento ou tire dúvidas.",
                'demo_confirmada': "Demo confirmada. Seja caloroso e confirme detalhes.",
            }.get(estagio, '')

            response = self.ai_client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=400,
                system=f"""Você é vendedor da Pili Equipamentos (tombadores e coletores de grãos).

PRODUTO:
- Tombadores de grãos para caminhonetes e carretas
- Coletores de varredura — zero desperdício
- ROI em menos de 1 safra
- Entrega nacional, assistência técnica
- Agendamento: {DEMO_CAL_LINK}

REGRAS:
1. Natural, como WhatsApp real — máximo 5 linhas
2. NUNCA diga que é robô ou IA
3. Tom próximo, vocabulário do agro
4. Nível de intenção: {intencao['nivel']} ({intencao.get('sinal', '-')})
5. {instrucao}
6. Use 1-2 emojis (🌾 🚜 🤝)
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
                "Nossos tombadores e coletores de grãos são usados por "
                "cerealistas e cooperativas em todo o Brasil. 🌾\n\n"
                "Principais benefícios:\n"
                "- Redução de perda no recebimento\n"
                "- Maior produtividade no descarregamento\n"
                "- Durabilidade e manutenção simples\n\n"
                f"Quer agendar uma demonstração? {DEMO_CAL_LINK}"
            )

        if nivel == 'baixa':
            return (
                "Entendo! Sem problemas. 🙂\n\n"
                "Se precisar de equipamentos para recebimento de grãos "
                "no futuro, é só chamar. Obrigado! 🌾"
            )

        return (
            "Posso te mandar mais informações sobre nossos tombadores e coletores?\n\n"
            f"Ou prefere agendar uma demonstração rápida? {DEMO_CAL_LINK} 🤝"
        )

    # =========================================================================
    # PROPOSTA DE DEMO / VISITA TÉCNICA
    # =========================================================================

    def gerar_proposta_demo(self, lead):
        """Propõe visita técnica ou demo online"""
        if self.ai_client:
            try:
                nome = lead.get('nome_fantasia', 'vocês')
                response = self.ai_client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=250,
                    system=f"""Você é vendedor da Pili Equipamentos.
O lead demonstrou interesse em tombadores/coletores de grãos.
Proponha uma demonstração (20 min online ou visita técnica).

Link de agendamento: {DEMO_CAL_LINK}

REGRAS: máximo 4 linhas, inclua o link, 1 emoji, só a mensagem.""",
                    messages=[{
                        "role": "user",
                        "content": f"Empresa: {nome}\nProponha demo/visita técnica:"
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
        """Follow-up com link de agendamento"""
        key = f'followup{numero}'
        template = MENSAGENS.get(key, '')
        return template.format(cal_link=DEMO_CAL_LINK) if template else None

    # =========================================================================
    # DETECÇÃO DE INTENÇÃO
    # =========================================================================

    def detectar_intencao(self, mensagem, estagio='inicial'):
        """Detecta intenção do lead no contexto de equipamentos agrícolas"""
        msg = mensagem.lower().strip()

        # CONFIRMAÇÃO DE AGENDAMENTO
        if estagio == 'demo_proposta':
            sinais_confirmacao = [
                'confirmado', 'agendei', 'marquei', 'ok', 'sim', 'pode ser',
                'beleza', 'combinado', 'perfeito', 'bora', 'claro',
                r'\d{1,2}[/\-]\d{1,2}', r'\d{1,2}h\d{0,2}',
            ]
            for sinal in sinais_confirmacao:
                if re.search(sinal, msg):
                    return {'nivel': 'confirmacao', 'sinal': sinal, 'acao': 'confirmar_demo'}

        # QUER AGENDAR VISITA / DEMO
        sinais_agendamento = [
            'visita', 'visitar', 'demonstracao', 'demonstração',
            'quero ver', 'pode vir', 'agendar', 'demo',
            'tecnico', 'técnico', 'reuniao', 'reunião', 'call',
        ]
        for sinal in sinais_agendamento:
            if sinal in msg:
                return {'nivel': 'demo', 'sinal': sinal, 'acao': 'propor_agendamento'}

        # ALTA INTENÇÃO (interesse em comprar / saber mais)
        sinais_quentes = [
            'quero', 'interesse', 'interessado', 'quanto custa', 'preco',
            'preço', 'valor', 'orcamento', 'orçamento', 'comprar',
            'adquirir', 'catalogo', 'catálogo', 'especificacao',
            'manda informacao', 'me manda', 'sim', 'beleza', 'pode ser',
            'gostei', 'me interessa', 'precisamos', 'precisamos disso',
        ]
        for sinal in sinais_quentes:
            if sinal in msg:
                return {'nivel': 'alta', 'sinal': sinal, 'acao': 'enviar_info'}

        # MÉDIA INTENÇÃO (curioso)
        sinais_medios = [
            'o que e', 'o que é', 'como funciona', 'explica', 'me conta',
            'o que faz', 'bom dia', 'boa tarde', 'boa noite', 'oi', 'ola', 'olá',
            'tombador', 'coletor', 'qual a capacidade', 'qual modelo',
        ]
        for sinal in sinais_medios:
            if sinal in msg:
                return {'nivel': 'media', 'sinal': sinal, 'acao': 'explicar'}

        # BAIXA INTENÇÃO
        sinais_frios = [
            'nao', 'não', 'sem interesse', 'nao quero', 'não quero',
            'para', 'parar', 'remove', 'spam', 'ja tenho', 'já tenho',
            'nao preciso', 'não preciso',
        ]
        for sinal in sinais_frios:
            if sinal in msg:
                return {'nivel': 'baixa', 'sinal': sinal, 'acao': 'encerrar'}

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
            'cerealista': ['cerealista', 'cereais', 'compra graos', 'compra soja'],
            'cooperativa agrícola': [
                'cooperativa', 'coop', 'coagro', 'coamo', 'corol'
            ],
            'armazém/silo': ['silo', 'armazem', 'armazém', 'deposito', 'depósito'],
            'fazenda/produtor rural': [
                'fazenda', 'rural', 'agropecuaria', 'agropecuária', 'produtor'
            ],
            'transportadora agrícola': ['transportadora', 'logistica', 'logística'],
            'agronegócio': [
                'agro', 'graos', 'grãos', 'soja', 'milho', 'trigo',
                'agricola', 'agrícola',
            ],
        }

        for nome_seg, palavras in segmentos.items():
            for palavra in palavras:
                if palavra in texto:
                    return nome_seg

        if lead.get('segmento'):
            return lead['segmento'][:50]

        return 'agronegócio'
