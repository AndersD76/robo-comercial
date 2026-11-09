"""E-mails do teste grátis do TurboVenda: do cadastro à assinatura.

Em 05/11/2026 o funil tinha 60 cadastros e nenhuma tentativa de pagamento.
Os avisos de teste existentes nunca saíram (dependiam de um cron que não
existia), então ninguém era lembrado de nada. Este módulo manda um e-mail em
cada momento que pesa na decisão de assinar, uma vez só por pessoa:

  leads   o robô trouxe os 10 primeiros leads com contato
  cota    encheu os 50 leads do teste e pausou
  2dias   faltam 2 dias para o teste acabar
  acabou  o teste acabou (até 3 dias depois)

E a reativação de quem testou antes das correções de 03/11, quando o robô
gravava contato errado (scripts/reativar_testes.py).

Não importa o app: recebe a conexão e a função de envio, o que deixa
testar sem banco nem Resend.
"""
import re
from datetime import timedelta

LEADS_PRIMEIRO_AVISO = 10
COTA_TESTE = 50
DIAS_REATIVACAO = 7
# Nunca dois e-mails do funil para a mesma pessoa no mesmo dia
INTERVALO_MIN = timedelta(hours=20)
# Do mais urgente para o menos: mandar um torna os de baixo obsoletos
ETAPAS = ('acabou', '2dias', 'cota', 'leads')
COLUNA = {
    'acabou': 'trial_email_expired_sent',
    '2dias': 'trial_email_3d_sent',
    'cota': 'trial_email_cota_sent',
    'leads': 'trial_email_leads_sent',
}
MIGRACOES = [
    'ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_email_3d_sent BOOLEAN DEFAULT FALSE',
    'ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_email_expired_sent BOOLEAN DEFAULT FALSE',
    'ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_email_cota_sent BOOLEAN DEFAULT FALSE',
    'ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_email_leads_sent BOOLEAN DEFAULT FALSE',
    'ALTER TABLE users ADD COLUMN IF NOT EXISTS funil_ultimo_email_em TIMESTAMP',
    'ALTER TABLE users ADD COLUMN IF NOT EXISTS reativacao_enviada_em TIMESTAMP',
    # pagantes: guarda para qual vencimento o aviso já saiu (um por ciclo)
    'ALTER TABLE users ADD COLUMN IF NOT EXISTS renovacao_aviso_para TIMESTAMP',
    'ALTER TABLE users ADD COLUMN IF NOT EXISTS renovacao_vencido_para TIMESTAMP',
    'ALTER TABLE pagamentos ADD COLUMN IF NOT EXISTS lembrete_em TIMESTAMP',
    # descadastro em 1 clique (LGPD): vale para os e-mails de teste e de PIX não pago;
    # o aviso de vencimento de quem paga é transacional e continua
    'ALTER TABLE users ADD COLUMN IF NOT EXISTS emails_marketing_off BOOLEAN DEFAULT FALSE',
    'ALTER TABLE users ADD COLUMN IF NOT EXISTS depoimento_pedido_em TIMESTAMP',
]
DIAS_AVISO_RENOVACAO = 3
NOMES_PLANO = {'starter': 'Starter', 'pro': 'Pro'}
_EMAIL_OK = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
_SCHEMA_OK = re.compile(r'^emp_\d+$')
# O banco grava em UTC; o cliente lê no horário de Brasília (sem horário de verão)
_BRASILIA = timedelta(hours=-3)


# ---------------------------------------------------------------------------
# Números do lead para o e-mail
# ---------------------------------------------------------------------------

def resumo_leads(cur, schema):
    """Leads com contato, com CNPJ e com decisor. Mesmo critério da cota do
    teste: só conta lead com telefone, e-mail ou WhatsApp."""
    vazio = {'validos': 0, 'cnpj': 0, 'decisor': 0}
    if not _SCHEMA_OK.match(schema or ''):
        return vazio
    cur.execute('SELECT to_regclass(%s) AS t', (f'{schema}.empresas',))
    if not cur.fetchone()['t']:
        return vazio
    cur.execute('SELECT to_regclass(%s) AS t', (f'{schema}.contatos',))
    tem_contatos = bool(cur.fetchone()['t'])
    decisor = (f'COUNT(*) FILTER (WHERE EXISTS (SELECT 1 FROM {schema}.contatos ct '
               f'WHERE ct.empresa_id = e.id AND ct.decisor = 1))'
               if tem_contatos else '0')
    cur.execute(f"""SELECT COUNT(*) AS validos,
                           COUNT(*) FILTER (WHERE COALESCE(e.cnpj, '') <> '') AS cnpj,
                           {decisor} AS decisor
                    FROM {schema}.empresas e
                    WHERE COALESCE(e.telefone, '') <> '' OR COALESCE(e.email, '') <> ''
                       OR COALESCE(e.whatsapp, '') <> ''""")
    r = cur.fetchone()
    return {'validos': r['validos'] or 0, 'cnpj': r['cnpj'] or 0,
            'decisor': r['decisor'] or 0}


def _data_br(ts):
    if not ts:
        return ''
    return (ts + _BRASILIA).strftime('%d/%m')


def _reais(valor):
    return f'R$ {valor:.0f}' if float(valor).is_integer() else f'R$ {valor:.2f}'.replace('.', ',')


def _numeros(r):
    partes = [f'<strong>{r["validos"]}</strong> com telefone ou e-mail']
    if r['cnpj']:
        partes.append(f'<strong>{r["cnpj"]}</strong> com CNPJ')
    if r['decisor']:
        partes.append(f'<strong>{r["decisor"]}</strong> com o nome do sócio que decide')
    return ', '.join(partes[:-1]) + (' e ' if len(partes) > 1 else '') + partes[-1]


# ---------------------------------------------------------------------------
# Textos
# ---------------------------------------------------------------------------

def _escapar(s):
    return (str(s or '').replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;').replace('"', '&quot;'))


def _layout(empresa, paragrafos, botao, url, rodape=''):
    corpo = ''.join(f'<p style="font-size:16px;line-height:1.6;margin:0 0 16px">{p}</p>'
                    for p in paragrafos)
    return f'''<div style="font-family:Arial,Helvetica,sans-serif;max-width:600px;margin:0 auto;padding:24px;color:#1e293b">
  <p style="color:#6366f1;font-size:22px;font-weight:700;margin:0 0 24px">TurboVenda</p>
  <p style="font-size:16px;line-height:1.6;margin:0 0 16px">Olá, {_escapar(empresa) or 'tudo bem'}.</p>
  {corpo}
  <div style="text-align:center;margin:28px 0">
    <a href="{url}" style="display:inline-block;background:#6366f1;color:#ffffff;text-decoration:none;padding:14px 28px;border-radius:8px;font-size:16px;font-weight:600">{botao}</a>
  </div>
  {f'<p style="font-size:14px;color:#64748b;line-height:1.5;margin:0 0 16px">{rodape}</p>' if rodape else ''}
  <p style="font-size:14px;color:#64748b;line-height:1.5;margin:0">Ficou com dúvida ou algo não funcionou? Responda este e-mail.</p>
  <hr style="border:none;border-top:1px solid #e2e8f0;margin:28px 0 16px">
  <p style="font-size:12px;color:#94a3b8;margin:0">Você recebe este e-mail porque criou uma conta de teste no TurboVenda.</p>
  __DESCADASTRO__
</div>'''


def email_leads(empresa, r, expira, app_url, preco):
    assunto = f'Seus primeiros {r["validos"]} leads chegaram'
    html = _layout(empresa, [
        f'O robô do TurboVenda já encontrou empresas para você vender: {_numeros(r)}.',
        'O próximo passo é falar com elas. No painel, abra um lead e mande a '
        'primeira mensagem pelo WhatsApp ou por e-mail.',
    ], 'Ver meus leads', f'{app_url}/dashboard',
        f'Seu teste grátis vai até {_data_br(expira)}.')
    return assunto, html


def email_cota(empresa, r, expira, app_url, preco):
    assunto = f'Seu robô encontrou {r["validos"]} leads e pausou'
    html = _layout(empresa, [
        f'O robô chegou ao limite de {COTA_TESTE} leads do teste grátis: {_numeros(r)}.',
        f'Ele pausou para não passar disso. Com o plano Starter, por {_reais(preco)} '
        'por mês, ele volta a buscar na hora, até 500 leads.',
    ], 'Continuar com o Starter', f'{app_url}/assinar',
        'Pagamento por PIX ou cartão. Com PIX, libera na hora.')
    return assunto, html


def email_2dias(empresa, r, expira, app_url, preco):
    assunto = 'Seu teste do TurboVenda acaba em 2 dias'
    achados = (f'Até agora o robô encontrou {_numeros(r)}.' if r['validos']
               else 'Seu robô ainda não trouxe leads. Confira a configuração no '
                    'painel: com os termos de busca preenchidos, ele começa sozinho.')
    html = _layout(empresa, [
        f'Seu teste grátis vai até <strong>{_data_br(expira)}</strong>. {achados}',
        'Depois dessa data o robô para de buscar. O que ele já encontrou continua salvo.',
    ], f'Assinar o Starter por {_reais(preco)}/mês', f'{app_url}/assinar',
        'Pagamento por PIX ou cartão. Com PIX, libera na hora.')
    return assunto, html


def email_acabou(empresa, r, expira, app_url, preco):
    if r['validos']:
        assunto = f'Seu teste acabou. Seus {r["validos"]} leads continuam salvos'
        primeiro = (f'O teste grátis terminou e o robô parou. Tudo o que ele '
                    f'encontrou continua na sua conta: {_numeros(r)}.')
    else:
        assunto = 'Seu teste do TurboVenda acabou'
        primeiro = 'O teste grátis terminou e o robô parou.'
    html = _layout(empresa, [
        primeiro,
        f'Para voltar a buscar, assine o Starter: {_reais(preco)} por mês, até 500 leads.',
    ], 'Pagar com PIX e continuar', f'{app_url}/assinar',
        'Também aceitamos cartão.')
    return assunto, html


def email_reativacao(empresa, r, expira, app_url, preco):
    assunto = 'Consertamos o TurboVenda e liberamos mais 7 dias de teste'
    if r['validos']:
        conta = f'Sua conta já tem {_numeros(r)}.'
    else:
        conta = ('Seu robô ainda não trouxe nenhum lead. Entre no painel: com a '
                 'descrição do que você vende preenchida na configuração, ele '
                 'começa a buscar sozinho.')
    html = _layout(empresa, [
        'Você testou o TurboVenda nas últimas semanas, e devemos uma explicação: '
        'o robô estava gravando contatos errados, como telefones e e-mails tirados '
        'de páginas do Google em vez dos da empresa. Isso estragou o seu teste.',
        'Corrigimos. Agora cada lead chega com telefone e e-mail conferidos, '
        'CNPJ e razão social da Receita Federal e, quando a empresa tem, o nome '
        'do sócio que decide a compra.',
        conta,
        f'Para compensar, liberamos <strong>mais {DIAS_REATIVACAO} dias de teste '
        f'grátis, até {_data_br(expira)}</strong>. Não precisa de cartão.',
    ], 'Entrar no meu painel', f'{app_url}/dashboard')
    return assunto, html


def _com_descadastro(html, url):
    """Troca o marcador do rodapé pelo link de descadastro da pessoa (e-mails de
    marketing) ou o remove (transacionais)."""
    link = (f'<p style="font-size:12px;color:#94a3b8;margin:8px 0 0"><a href="{url}" '
            f'style="color:#94a3b8">Não quero mais receber estes e-mails</a></p>') if url else ''
    return html.replace('__DESCADASTRO__', link)


def _rodape_pagante(html):
    return html.replace('Você recebe este e-mail porque criou uma conta de teste no TurboVenda.',
                        'Você recebe este e-mail porque tem uma assinatura do TurboVenda.')


def email_renova(empresa, plano, valor, expira, app_url):
    nome = NOMES_PLANO.get(plano, plano)
    assunto = f'Seu plano {nome} vence em {_data_br(expira)}'
    html = _layout(empresa, [
        f'Seu plano {nome} do TurboVenda vale até <strong>{_data_br(expira)}</strong>.',
        f'Para o robô não parar, renove por {_reais(valor)}. Com PIX, libera na hora '
        'e os 30 dias novos contam a partir do fim do plano atual, sem perder nenhum dia.',
    ], f'Renovar o {nome}', f'{app_url}/assinar?plano={plano}',
        'Não quer renovar? Não precisa fazer nada: nada é cobrado sem você pagar.')
    return assunto, _rodape_pagante(html)


def email_vencido(empresa, plano, valor, expira, app_url, r):
    nome = NOMES_PLANO.get(plano, plano)
    assunto = f'Seu plano {nome} venceu e o robô pausou'
    html = _layout(empresa, [
        f'Seu plano {nome} venceu em {_data_br(expira)} e o robô parou de buscar. '
        + (f'Tudo o que ele encontrou continua salvo: {_numeros(r)}.' if r['validos'] else ''),
        f'Para ele voltar a buscar, renove por {_reais(valor)}. Com PIX, libera na hora.',
    ], f'Renovar o {nome}', f'{app_url}/assinar?plano={plano}')
    return assunto, _rodape_pagante(html)


def email_pix_pendente(empresa, plano, valor, app_url):
    nome = NOMES_PLANO.get(plano, plano)
    assunto = 'Seu PIX do TurboVenda não foi pago'
    html = _layout(empresa, [
        f'Você gerou um PIX de {_reais(valor)} para o plano {nome}, mas ele não foi pago '
        '(o código vale 30 minutos).',
        'Se ainda quiser continuar, gere um código novo: leva um minuto e o plano '
        'libera assim que o PIX cair.',
    ], 'Gerar um PIX novo', f'{app_url}/assinar?plano={plano}',
        'Se você já pagou por outro meio, ignore este e-mail.')
    return assunto, html


def email_depoimento(empresa, r, app_url):
    assunto = 'O TurboVenda está ajudando nas suas vendas?'
    html = _layout(empresa, [
        f'Seu robô já encontrou {_numeros(r)}.',
        'Queremos saber como está sendo: responda este e-mail com uma ou duas frases '
        'sobre o que mudou na sua prospecção, ou sobre o que ainda falta.',
        'Só publicamos o seu comentário no site, com o nome da sua empresa, se você '
        'autorizar por escrito na resposta. Sem autorização, ele fica só entre nós.',
    ], 'Abrir meu painel', f'{app_url}/dashboard')
    return assunto, html


MODELOS = {'leads': email_leads, 'cota': email_cota, '2dias': email_2dias,
           'acabou': email_acabou, 'reativacao': email_reativacao}


# ---------------------------------------------------------------------------
# Envio
# ---------------------------------------------------------------------------

def enviar_resend(api_key, remetente, para, assunto, html):
    """True se o Resend aceitou. Sem chave, não envia."""
    if not api_key:
        return False
    import requests
    try:
        r = requests.post('https://api.resend.com/emails',
                          headers={'Authorization': f'Bearer {api_key}',
                                   'Content-Type': 'application/json'},
                          json={'from': f'TurboVenda <{remetente}>', 'to': [para],
                                'subject': assunto, 'html': html},
                          timeout=15)
        return r.status_code in (200, 201)
    except Exception:
        return False


def migrar(cur):
    for sql in MIGRACOES:
        cur.execute(sql)


def _etapa_devida(u, r, agora):
    """A etapa mais urgente que essa pessoa ainda não recebeu, ou None."""
    expira = u['plano_expira']
    if expira <= agora:
        if expira > agora - timedelta(days=3) and not u[COLUNA['acabou']]:
            return 'acabou'
        return None
    if expira <= agora + timedelta(days=2) and not u[COLUNA['2dias']]:
        return '2dias'
    if r['validos'] >= COTA_TESTE and not u[COLUNA['cota']]:
        return 'cota'
    if r['validos'] >= LEADS_PRIMEIRO_AVISO and not u[COLUNA['leads']]:
        return 'leads'
    return None


def rodar(conn, enviar, app_url, preco, agora=None, descadastro=None):
    """Uma passada do funil. `enviar(para, assunto, html) -> bool`;
    `descadastro(user_id) -> url` põe o link de saída em 1 clique no rodapé.

    Marca antes de enviar, com commit: se o processo cair no meio, a pessoa
    fica sem aquele e-mail em vez de receber dois. Se o envio falhar,
    desmarca para tentar na próxima passada.
    """
    cur = conn.cursor()
    migrar(cur)
    conn.commit()
    cur.execute('SELECT NOW()::timestamp AS agora')
    agora = agora or cur.fetchone()['agora']
    cur.execute(f"""SELECT id, email, empresa_nome, schema_name, plano_expira,
                           funil_ultimo_email_em, {', '.join(COLUNA.values())}
                    FROM users
                    WHERE plano = 'trial' AND ativo = TRUE AND plano_expira IS NOT NULL
                      AND plano_expira > %s AND emails_marketing_off IS NOT TRUE
                    ORDER BY id""", (agora - timedelta(days=3),))
    usuarios = cur.fetchall()
    resultado = {e: 0 for e in ETAPAS}
    resultado['falhas'] = 0
    for u in usuarios:
        if not _EMAIL_OK.match(u['email'] or ''):
            continue
        if u['funil_ultimo_email_em'] and agora - u['funil_ultimo_email_em'] < INTERVALO_MIN:
            continue
        schema = u['schema_name'] or f'emp_{u["id"]}'
        r = resumo_leads(cur, schema)
        etapa = _etapa_devida(u, r, agora)
        if not etapa:
            continue
        # Mandar o mais urgente torna os de baixo obsoletos: quem já soube que
        # o teste acabou não precisa saber depois que os leads chegaram
        marcar = ETAPAS[ETAPAS.index(etapa):]
        sets = ', '.join(f'{COLUNA[e]} = TRUE' for e in marcar)
        cur.execute(f"""UPDATE users SET {sets}, funil_ultimo_email_em = %s
                        WHERE id = %s AND {COLUNA[etapa]} IS NOT TRUE RETURNING id""",
                    (agora, u['id']))
        if not cur.fetchone():
            conn.commit()
            continue   # outra passada (deploy sobreposto) já pegou
        conn.commit()
        assunto, html = MODELOS[etapa](u['empresa_nome'], r, u['plano_expira'],
                                       app_url, preco)
        html = _com_descadastro(html, descadastro(u['id']) if descadastro else None)
        if enviar(u['email'], assunto, html):
            resultado[etapa] += 1
        else:
            antes = {e: u[COLUNA[e]] for e in marcar}
            sets = ', '.join(f'{COLUNA[e]} = %s' for e in marcar)
            cur.execute(f'UPDATE users SET {sets}, funil_ultimo_email_em = %s WHERE id = %s',
                        [antes[e] for e in marcar] + [u['funil_ultimo_email_em'], u['id']])
            conn.commit()
            resultado['falhas'] += 1
    return resultado


def alvos_reativacao(cur, criados_antes):
    """Contas de teste criadas antes das correções e ainda não reativadas."""
    cur.execute("""SELECT id, email, empresa_nome, schema_name, plano_expira
                   FROM users
                   WHERE plano = 'trial' AND ativo = TRUE AND criado_em < %s
                     AND reativacao_enviada_em IS NULL
                   ORDER BY id""", (criados_antes,))
    return [u for u in cur.fetchall() if _EMAIL_OK.match(u['email'] or '')]


def reativar(conn, u, enviar, app_url, preco):
    """Estende o teste em 7 dias (a partir de hoje, se já venceu) e avisa.
    Tudo numa transação: se o e-mail não sair, o teste não muda e a conta
    continua na lista para a próxima tentativa."""
    cur = conn.cursor()
    cur.execute(f"""UPDATE users SET
                      plano_expira = GREATEST(COALESCE(plano_expira, NOW()), NOW())
                                     + INTERVAL '{DIAS_REATIVACAO} days',
                      reativacao_enviada_em = NOW(),
                      funil_ultimo_email_em = NOW(),
                      trial_email_3d_sent = FALSE,
                      trial_email_expired_sent = FALSE,
                      trial_email_leads_sent = TRUE
                    WHERE id = %s AND reativacao_enviada_em IS NULL
                    RETURNING plano_expira""", (u['id'],))
    linha = cur.fetchone()
    if not linha:
        conn.rollback()
        return False
    schema = u['schema_name'] or f'emp_{u["id"]}'
    r = resumo_leads(cur, schema)
    assunto, html = email_reativacao(u['empresa_nome'], r, linha['plano_expira'],
                                     app_url, preco)
    html = _com_descadastro(html, None)
    if enviar(u['email'], assunto, html):
        conn.commit()
        return True
    conn.rollback()
    return False


def rodar_pagantes(conn, enviar, app_url, precos, agora=None, descadastro=None):
    """Avisos de quem já pagou ou tentou pagar (uma passada).

    - plano pago vencendo em até 3 dias: um aviso por vencimento
      (renovacao_aviso_para guarda para qual plano_expira já saiu);
    - plano pago vencido há até 3 dias: um aviso por vencimento;
    - PIX gerado e não pago entre 1 h e 48 h atrás, sem pagamento aprovado
      depois: um lembrete por cobrança (pagamentos.lembrete_em).
    Mesma regra do funil: marca antes de enviar e desmarca se falhar.
    `precos` = {'starter': 97.0, 'pro': 297.0}."""
    cur = conn.cursor()
    migrar(cur)
    conn.commit()
    cur.execute('SELECT NOW()::timestamp AS agora')
    agora = agora or cur.fetchone()['agora']
    res = {'renova': 0, 'vencido': 0, 'pix': 0, 'falhas': 0}

    cur.execute("""SELECT id, email, empresa_nome, schema_name, plano, plano_expira,
                          renovacao_aviso_para, renovacao_vencido_para
                   FROM users WHERE plano IN ('starter', 'pro') AND ativo = TRUE
                     AND plano_expira BETWEEN %s AND %s ORDER BY id""",
                (agora - timedelta(days=3), agora + timedelta(days=DIAS_AVISO_RENOVACAO)))
    for u in cur.fetchall():
        if not _EMAIL_OK.match(u['email'] or ''):
            continue
        vencido = u['plano_expira'] <= agora
        coluna = 'renovacao_vencido_para' if vencido else 'renovacao_aviso_para'
        if u[coluna] == u['plano_expira']:
            continue
        cur.execute(f'UPDATE users SET {coluna} = %s WHERE id = %s AND '
                    f'{coluna} IS DISTINCT FROM %s RETURNING id',
                    (u['plano_expira'], u['id'], u['plano_expira']))
        if not cur.fetchone():
            conn.commit()
            continue
        conn.commit()
        valor = precos.get(u['plano'], 0)
        if vencido:
            r = resumo_leads(cur, u['schema_name'] or f'emp_{u["id"]}')
            assunto, html = email_vencido(u['empresa_nome'], u['plano'], valor,
                                          u['plano_expira'], app_url, r)
        else:
            assunto, html = email_renova(u['empresa_nome'], u['plano'], valor,
                                         u['plano_expira'], app_url)
        html = _com_descadastro(html, None)   # transacional: aviso do plano pago
        if enviar(u['email'], assunto, html):
            res['vencido' if vencido else 'renova'] += 1
        else:
            cur.execute(f'UPDATE users SET {coluna} = %s WHERE id = %s', (u[coluna], u['id']))
            conn.commit()
            res['falhas'] += 1

    cur.execute("""SELECT p.mp_payment_id, p.plano, p.valor, u.id AS uid, u.email, u.empresa_nome
                   FROM pagamentos p JOIN users u ON u.id = p.user_id
                   WHERE p.status = 'pending' AND p.lembrete_em IS NULL
                     AND u.emails_marketing_off IS NOT TRUE
                     AND p.criado_em BETWEEN %s AND %s
                     AND NOT EXISTS (SELECT 1 FROM pagamentos q WHERE q.user_id = p.user_id
                                     AND q.status = 'approved' AND q.criado_em >= p.criado_em)
                   ORDER BY p.criado_em""", (agora - timedelta(hours=48), agora - timedelta(hours=1)))
    avisados = set()
    for p in cur.fetchall():
        if p['uid'] in avisados or not _EMAIL_OK.match(p['email'] or ''):
            continue
        # um lembrete por pessoa: marca todos os PIX pendentes dela de uma vez
        cur.execute("""UPDATE pagamentos SET lembrete_em = %s WHERE user_id = %s
                       AND status = 'pending' AND lembrete_em IS NULL RETURNING mp_payment_id""",
                    (agora, p['uid']))
        marcados = [r['mp_payment_id'] for r in cur.fetchall()]
        conn.commit()
        if not marcados:
            continue
        avisados.add(p['uid'])
        assunto, html = email_pix_pendente(p['empresa_nome'], p['plano'],
                                           float(p['valor'] or 0), app_url)
        html = _com_descadastro(html, descadastro(p['uid']) if descadastro else None)
        if enviar(p['email'], assunto, html):
            res['pix'] += 1
        else:
            cur.execute('UPDATE pagamentos SET lembrete_em = NULL WHERE mp_payment_id = ANY(%s)',
                        (marcados,))
            conn.commit()
            res['falhas'] += 1
    return res


def rodar_depoimentos(conn, enviar, app_url, agora=None, descadastro=None):
    """Pedido de depoimento no pico de satisfação (Fase 7): 3 a 30 dias depois
    do 1º lead, com 10+ leads, uma vez por pessoa, respeitando o descadastro e
    o intervalo mínimo entre e-mails. Publicação só com autorização escrita."""
    cur = conn.cursor()
    migrar(cur)
    conn.commit()
    cur.execute('SELECT NOW()::timestamp AS agora')
    agora = agora or cur.fetchone()['agora']
    cur.execute("""SELECT id, email, empresa_nome, schema_name, funil_ultimo_email_em FROM users
                   WHERE aha_em IS NOT NULL AND aha_em BETWEEN %s AND %s
                     AND depoimento_pedido_em IS NULL AND emails_marketing_off IS NOT TRUE
                     AND ativo = TRUE ORDER BY id""",
                (agora - timedelta(days=30), agora - timedelta(days=3)))
    enviados = 0
    for u in cur.fetchall():
        if not _EMAIL_OK.match(u['email'] or ''):
            continue
        if u['funil_ultimo_email_em'] and agora - u['funil_ultimo_email_em'] < INTERVALO_MIN:
            continue
        r = resumo_leads(cur, u['schema_name'] or f'emp_{u["id"]}')
        if r['validos'] < LEADS_PRIMEIRO_AVISO:
            continue
        cur.execute("""UPDATE users SET depoimento_pedido_em = %s, funil_ultimo_email_em = %s
                       WHERE id = %s AND depoimento_pedido_em IS NULL RETURNING id""",
                    (agora, agora, u['id']))
        if not cur.fetchone():
            conn.commit()
            continue
        conn.commit()
        assunto, html = email_depoimento(u['empresa_nome'], r, app_url)
        html = _com_descadastro(html, descadastro(u['id']) if descadastro else None)
        if enviar(u['email'], assunto, html):
            enviados += 1
        else:
            cur.execute('UPDATE users SET depoimento_pedido_em = NULL, funil_ultimo_email_em = %s '
                        'WHERE id = %s', (u['funil_ultimo_email_em'], u['id']))
            conn.commit()
    return enviados
