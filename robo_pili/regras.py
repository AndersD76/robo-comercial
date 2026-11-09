# -*- coding: utf-8 -*-
"""Regras puras do robô, usadas pelo app (app.py) e pelos robôs.

Nada aqui abre banco nem depende do Flask: dá para testar com
DATABASE_URL vazio, como no CI.

- Caminhos por cliente: log, sessão/QR/status do WhatsApp. Antes eram
  arquivos únicos para todos os clientes, e o terminal de um mostrava a
  busca (e os e-mails achados) dos outros.
- Cota de leads: quantos leads novos o robô ainda pode gerar no plano.
  O consumo é um contador em users.leads_consumidos, não COUNT(*) da
  tabela — apagar lead não devolve cota.
"""
import os
import re
from datetime import datetime, timezone

CANAIS = ('busca', 'linkedin', 'wa')

# None = ilimitado. Trial: 50 no total. Starter: 500 por período pago.
LIMITE_LEADS = {
    'trial': 50,
    'starter': 500,
    'pro': None,
    'enterprise': None,
}
DIAS_PERIODO_PAGO = 30

_NOME_SEGURO = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,62}$')


def schema_seguro(schema):
    """Devolve o schema se ele for um nome SQL simples (emp_12, pili).

    Levanta ValueError para qualquer outra coisa — nada de barra, ponto
    ou "..", então o nome nunca escapa da pasta do robô nem colide com o
    de outro cliente.
    """
    s = str(schema or '')
    if not _NOME_SEGURO.match(s):
        raise ValueError(f'schema invalido: {schema!r}')
    return s


def caminho_log(base_dir, schema, canal):
    """Arquivo de log do robô de UM cliente: <base>/logs/<canal>_<schema>.log"""
    if canal not in CANAIS:
        raise ValueError(f'canal invalido: {canal!r}')
    return os.path.join(base_dir, 'logs',
                        f'{canal}_{schema_seguro(schema)}.log')


def caminhos_wa(base_dir, schema):
    """Sessão do navegador, QR e status do WhatsApp de UM cliente."""
    pasta = os.path.join(base_dir, 'wa', schema_seguro(schema))
    return {
        'pasta': pasta,
        'sessao': os.path.join(pasta, 'sessao'),
        'status': os.path.join(pasta, 'status.json'),
        'qr': os.path.join(pasta, 'qr.png'),
    }


def limite_do_plano(plano):
    """Leads por período; None = ilimitado. Plano desconhecido = teste."""
    p = (plano or 'trial').strip().lower()
    if p not in LIMITE_LEADS:
        p = 'trial'
    return LIMITE_LEADS[p]


def _para_datetime(valor):
    if valor is None or valor == '':
        return None
    if isinstance(valor, datetime):
        return valor.replace(tzinfo=None) if valor.tzinfo else valor
    try:
        dt = datetime.fromisoformat(str(valor).replace('Z', '+00:00'))
    except ValueError:
        return None
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


def situacao_cota(plano, plano_expira, leads_consumidos, agora=None):
    """O robô ainda pode gerar lead novo para esta conta?

    plano_expira e agora são comparados como horário sem fuso (o banco
    grava NOW() em UTC sem fuso). Quem chama deve passar o NOW() do
    próprio banco; sem ele, usa o UTC da máquina. Vencimento vale para
    qualquer plano que tenha data; sem data = não vence (contas antigas
    e as liberadas na mão).

    Devolve dict com:
      pode            bool  — pode inserir lead novo agora
      motivo          'ok' | 'vencido' | 'limite'
      plano           plano normalizado
      limite          int ou None (ilimitado)
      consumidos      int
      restantes       int ou None
      vencido         bool
      limite_atingido bool
    """
    p = (plano or 'trial').strip().lower() or 'trial'
    limite = limite_do_plano(p)
    try:
        consumidos = max(0, int(leads_consumidos or 0))
    except (TypeError, ValueError):
        consumidos = 0
    agora = (_para_datetime(agora)
             or datetime.now(timezone.utc).replace(tzinfo=None))
    expira = _para_datetime(plano_expira)
    vencido = bool(expira and expira < agora)
    limite_atingido = limite is not None and consumidos >= limite
    restantes = None if limite is None else max(0, limite - consumidos)
    if vencido:
        motivo = 'vencido'
    elif limite_atingido:
        motivo = 'limite'
    else:
        motivo = 'ok'
    return {
        'pode': motivo == 'ok',
        'motivo': motivo,
        'plano': p,
        'limite': limite,
        'consumidos': consumidos,
        'restantes': restantes,
        'vencido': vencido,
        'limite_atingido': limite_atingido,
    }


_NOMES_PLANO = {'trial': 'teste grátis', 'starter': 'Starter',
                'pro': 'Pro', 'enterprise': 'Enterprise'}


def mensagem_situacao(sit):
    """Texto curto, para o cliente, explicando por que o robô não roda."""
    plano = sit.get('plano') or 'trial'
    nome = _NOMES_PLANO.get(plano, plano)
    if sit.get('motivo') == 'vencido':
        if plano == 'trial':
            return ('Seu teste grátis terminou. Escolha um plano para '
                    'voltar a prospectar.')
        return (f'Seu plano {nome} venceu. Renove para voltar a '
                f'prospectar.')
    if sit.get('motivo') == 'limite':
        limite = sit.get('limite')
        if plano == 'trial':
            return (f'Você já usou os {limite} leads do teste grátis. '
                    f'Escolha um plano para continuar prospectando.')
        return (f'Você já usou os {limite} leads do plano {nome} neste '
                f'período. Para continuar agora, faça upgrade para o Pro.')
    return ''
