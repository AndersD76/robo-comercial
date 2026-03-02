# -*- coding: utf-8 -*-
"""
Integração Google Calendar - PrismaBiz
Cria eventos de demonstração quando lead confirma agendamento.

SETUP (uma vez só):
1. Acesse console.cloud.google.com → crie projeto → ative "Google Calendar API"
2. Crie credenciais OAuth 2.0 (tipo: aplicativo desktop) → baixe credentials.json
3. Coloque credentials.json nesta pasta (agente_prospeccao/)
4. Na primeira execução, abrirá janela para autorizar → gera token.json (salvo automaticamente)
5. Configure no .env ou ambiente:
   GOOGLE_CALENDAR_ID=seu_email@gmail.com  (ou ID do calendário específico)
"""

import os
import re
from datetime import datetime, timedelta

CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), 'credentials.json')
TOKEN_FILE = os.path.join(os.path.dirname(__file__), 'token.json')
CALENDAR_ID = os.environ.get('GOOGLE_CALENDAR_ID', 'primary')

# Duração padrão da demo em minutos
DEMO_DURACAO_MIN = 30


def _get_service():
    """Retorna serviço autenticado do Google Calendar"""
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        raise RuntimeError(
            "Instale: pip install google-api-python-client "
            "google-auth-oauthlib google-auth-httplib2"
        )

    SCOPES = ['https://www.googleapis.com/auth/calendar']
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"credentials.json não encontrado em {CREDENTIALS_FILE}\n"
                    "Veja as instruções no topo deste arquivo."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE, SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())

    return build('calendar', 'v3', credentials=creds)


def _extrair_data_hora(texto):
    """
    Tenta extrair data e hora de uma mensagem de confirmação.
    Retorna datetime ou None se não encontrar.
    Exemplos suportados: "15/03", "amanhã às 10h", "segunda 14h30"
    """
    agora = datetime.now()
    texto = texto.lower()

    # Padrão: DD/MM às HHh ou HH:MM
    m = re.search(
        r'(\d{1,2})[/\-](\d{1,2}).*?(\d{1,2})h(\d{0,2})',
        texto
    )
    if m:
        dia, mes = int(m.group(1)), int(m.group(2))
        hora = int(m.group(3))
        minuto = int(m.group(4)) if m.group(4) else 0
        ano = agora.year if mes >= agora.month else agora.year + 1
        try:
            return datetime(ano, mes, dia, hora, minuto)
        except ValueError:
            pass

    # Padrão: só hora "às 10h" ou "10:30"
    m = re.search(r'(\d{1,2})h(\d{0,2})', texto)
    if m:
        hora = int(m.group(1))
        minuto = int(m.group(2)) if m.group(2) else 0
        # Usa próximo dia útil
        candidato = agora.replace(hour=hora, minute=minuto, second=0)
        if candidato <= agora:
            candidato += timedelta(days=1)
        return candidato

    # Palavras-chave de dia relativo
    dias_relativos = {
        'hoje': 0, 'amanhã': 1, 'amanha': 1,
        'segunda': None, 'terça': None, 'terca': None,
        'quarta': None, 'quinta': None, 'sexta': None,
    }
    for palavra, delta in dias_relativos.items():
        if palavra in texto and delta is not None:
            m = re.search(r'(\d{1,2})h(\d{0,2})', texto)
            if m:
                hora = int(m.group(1))
                minuto = int(m.group(2)) if m.group(2) else 0
                data = agora + timedelta(days=delta)
                return data.replace(hour=hora, minute=minuto, second=0)

    return None


def criar_evento_demo(nome_empresa, whatsapp, mensagem_confirmacao):
    """
    Cria evento de demonstração no Google Calendar.

    Args:
        nome_empresa: Nome da empresa/lead
        whatsapp: Número WhatsApp do lead
        mensagem_confirmacao: Texto da mensagem de confirmação (para extrair data/hora)

    Returns:
        dict com link do evento ou None em caso de erro
    """
    try:
        service = _get_service()
    except (RuntimeError, FileNotFoundError) as e:
        print(f"    [CALENDAR] {e}")
        return None

    # Tenta extrair data/hora da mensagem
    inicio = _extrair_data_hora(mensagem_confirmacao)
    if not inicio:
        # Fallback: próximo dia útil às 10h
        inicio = datetime.now() + timedelta(days=1)
        inicio = inicio.replace(hour=10, minute=0, second=0, microsecond=0)
        # Pula fim de semana
        while inicio.weekday() >= 5:
            inicio += timedelta(days=1)

    fim = inicio + timedelta(minutes=DEMO_DURACAO_MIN)

    evento = {
        'summary': f'Demo PrismaBiz — {nome_empresa}',
        'description': (
            f'Demonstração do PrismaBiz para {nome_empresa}\n'
            f'WhatsApp: {whatsapp}\n'
            f'Agendado via bot de prospecção.'
        ),
        'start': {
            'dateTime': inicio.strftime('%Y-%m-%dT%H:%M:%S'),
            'timeZone': 'America/Sao_Paulo',
        },
        'end': {
            'dateTime': fim.strftime('%Y-%m-%dT%H:%M:%S'),
            'timeZone': 'America/Sao_Paulo',
        },
        'reminders': {
            'useDefault': False,
            'overrides': [
                {'method': 'email', 'minutes': 60},
                {'method': 'popup', 'minutes': 15},
            ],
        },
    }

    resultado = service.events().insert(
        calendarId=CALENDAR_ID,
        body=evento
    ).execute()

    link = resultado.get('htmlLink', '')
    print(f"    [CALENDAR] Evento: {inicio.strftime('%d/%m %H:%M')} — {link}")
    return resultado
