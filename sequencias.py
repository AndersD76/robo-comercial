# -*- coding: utf-8 -*-
"""Leads das iscas: gravação com a origem, e-mail do resultado, alerta ao dono
e a sequência de 5 e-mails do cluster terminando na oferta.

O e-mail 1 é o resultado que a pessoa pediu (transacional, sempre sai).
Os e-mails 2 a 5 são marketing: só com o opt-in marcado (desmarcado por
padrão, separado do pedido) e todos com descadastro em 1 clique.
"""
import datetime as _dt
import hashlib
import hmac
import json
import re
from html import escape

import crescimento as cfg
import iscas

EMAIL_OK = re.compile(r'^[^@\s]{1,64}@[a-z0-9.-]+\.[a-z]{2,}$', re.I)
# dias depois da captura em que sai cada e-mail de marketing (passos 2 a 5)
AGENDA = [1, 3, 5, 8]
SO_INSCRICAO = [k for k, v in iscas.ISCAS.items() if v.get('so_inscricao')]

# Dicas por grupo de cluster (texto próprio, sem número de mercado)
_DICAS = {
    'prospeccao': [
        ('O erro que mais custa na prospecção', 'Falar com todo mundo. Uma lista menor, só com quem se encaixa no seu cliente ideal, '
         'responde mais e gasta menos tempo do seu time.', '/ferramentas/gerador-de-icp', 'Escreva o seu cliente ideal'),
        ('Primeira mensagem: 3 linhas bastam', 'Um fato verdadeiro da empresa, o resultado que você entrega e uma pergunta. '
         'Sem anexo e sem link no primeiro contato.', '/ferramentas/gerador-de-mensagem-de-prospeccao', 'Gere a sua mensagem'),
        ('O dinheiro está no follow-up', 'Quem para no primeiro toque perde a maior parte das respostas. Defina a cadência '
         'antes de começar e siga para todo lead.', '/ferramentas/gerador-de-cadencia-de-prospeccao', 'Monte a sua cadência'),
    ],
    'dados': [
        ('Lista boa começa no CNPJ', 'Empresa baixada, inapta ou sem contato público é tempo perdido. Comece pelas ativas, '
         'com telefone ou e-mail, e pelo sócio que decide.', '/empresas', 'Veja empresas por segmento e cidade'),
        ('CNAE certo, lista certa', 'O CNAE principal diz o que a empresa faz de verdade. Filtrar pelo código evita '
         'misturar quem compra com quem vende o mesmo que você.', '/ferramentas/consulta-cnae', 'Consulte o CNAE'),
        ('Do segmento à cidade', 'Começar pela sua cidade e pelas vizinhas encurta a venda: visita possível, referência local '
         'e menos concorrência no primeiro contato.', '/ferramentas/lista-de-empresas', 'Monte a lista da sua cidade'),
    ],
    'gestao': [
        ('Meta sem número de leads é desejo', 'Faça a conta de trás para frente: vendas da meta, conversão de cada etapa e, '
         'no fim, quantos leads novos por mês.', '/ferramentas/calculadora-de-leads', 'Calcule os leads da meta'),
        ('Ache o gargalo antes de contratar', 'Mais vendedor não resolve funil furado. Meça a conversão por etapa e ataque a pior.',
         '/ferramentas/calculadora-de-funil-de-vendas', 'Ache o gargalo'),
        ('CAC: quanto custa cada cliente', 'Some marketing e vendas do mês e divida pelos clientes novos. Se o cliente não paga '
         'isso de volta em poucos meses, o crescimento come o caixa.', '/ferramentas/calculadora-de-cac', 'Calcule o seu CAC'),
    ],
    'lgpd': [
        ('Base legal antes da primeira mensagem', 'Na prospecção B2B costuma-se usar o legítimo interesse, que pede avaliação '
         'registrada e só os dados necessários.', '/ferramentas/checklist-lgpd-prospeccao', 'Faça o checklist'),
        ('Diga de onde veio o contato', 'Transparência é obrigação: quem você é, por que escreveu e como parar de receber.',
         '/lgpd', 'Veja a LGPD explicada'),
        ('Descadastro na hora', 'Pedido de parar é atendido no mesmo dia e o endereço sai de todas as listas.', '/privacidade',
         'Veja como fazemos'),
    ],
}
_GRUPO = {'prospeccao': 'prospeccao', 'abordagem': 'prospeccao', 'whatsapp': 'prospeccao', 'email': 'prospeccao',
          'linkedin': 'prospeccao', 'decisor': 'prospeccao', 'listas': 'dados', 'cnae': 'dados', 'setores': 'dados',
          'metas': 'gestao', 'crm': 'gestao', 'gestao': 'gestao', 'ferramentas': 'gestao', 'lgpd': 'lgpd'}


def grupo_do_cluster(cluster):
    return _GRUPO.get(cluster or '', 'prospeccao')


def token_lead(lead_id, segredo):
    assinatura = hmac.new(str(segredo).encode(), f'lead:{int(lead_id)}'.encode(), hashlib.sha256).hexdigest()[:24]
    return f'l{int(lead_id)}.{assinatura}'


def lead_do_token(token, segredo):
    m = re.fullmatch(r'l(\d{1,12})\.[0-9a-f]{24}', token or '')
    if not m:
        return None
    lead_id = int(m.group(1))
    return lead_id if hmac.compare_digest(token_lead(lead_id, segredo), token) else None


def _layout(titulo, corpo, descadastro):
    rodape = (f'<p style="color:#64748b;font-size:12px;margin-top:28px">Você recebe este e-mail porque pediu um resultado '
              f'no TurboVenda. <a href="{descadastro}" style="color:#64748b">Não quero mais receber</a>.</p>'
              if descadastro else '')
    return (f'<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;color:#0f172a;line-height:1.6">'
            f'<h2 style="color:#4f46e5">{escape(titulo)}</h2>{corpo}{rodape}'
            '<p style="color:#94a3b8;font-size:12px">TurboVenda · prospecção B2B automática · '
            '<a href="https://www.turbovenda.com.br" style="color:#94a3b8">turbovenda.com.br</a></p></div>')


def email_resultado(isca_id, resultado, descadastro, oferta_dias=14):
    isca = iscas.ISCAS[isca_id]
    texto_cta, link_cta = iscas.cta(isca_id)
    corpo = (resultado.get('completo') or resultado.get('tela') or '')
    corpo = corpo.replace('class="dados"', 'style="border-collapse:collapse;width:100%" border="1" cellpadding="6"')
    corpo = re.sub(r'href="/', 'href="https://www.turbovenda.com.br/', corpo)
    corpo += (f'<p style="margin-top:22px"><a href="https://www.turbovenda.com.br{link_cta}" style="background:#4f46e5;'
              f'color:#fff;padding:12px 22px;border-radius:8px;text-decoration:none;font-weight:bold">{escape(texto_cta)}</a></p>'
              f'<p style="color:#475569;font-size:14px">O TurboVenda encontra as empresas do seu perfil, confere o contato '
              f'e faz o primeiro toque sozinho. Teste grátis com 50 leads por {int(oferta_dias)} dias, sem cartão.</p>')
    return f'Seu resultado: {isca["nome"]}', _layout(isca['nome'], corpo, descadastro)


def email_passo(passo, cluster, nome, descadastro, oferta_dias=14, isca_id=None):
    """Passos 2 a 5 da sequência (marketing). passo 5 = oferta."""
    saudacao = f'<p>Olá{", " + escape(nome.split()[0]) if nome else ""}!</p>'
    if isca_id == 'mini-curso' and passo - 1 < len(iscas.AULAS_CURSO):
        titulo, html = iscas.AULAS_CURSO[passo - 1]
        return titulo, _layout(titulo, saudacao + html, descadastro)
    if passo >= 5:
        titulo = f'Teste o TurboVenda por {int(oferta_dias)} dias'
        corpo = (saudacao + '<p>Nos últimos dias você viu como montar a lista, falar com quem decide e medir o funil. '
                 'O TurboVenda faz a parte repetitiva sozinho: encontra as empresas do seu perfil na base da Receita, '
                 'confere telefone e e-mail e faz o primeiro contato por e-mail e WhatsApp.</p>'
                 '<p><a href="https://www.turbovenda.com.br/cadastro?utm_source=email&utm_medium=sequencia&utm_campaign='
                 f'{escape(cluster or "geral")}" style="background:#4f46e5;color:#fff;padding:12px 22px;border-radius:8px;'
                 f'text-decoration:none;font-weight:bold">Começar o teste grátis</a></p>'
                 '<p style="color:#475569;font-size:14px">O teste tem 50 leads e não pede cartão. Planos a partir de R$ 97 por mês. '
                 '<a href="https://www.turbovenda.com.br/precos">Ver planos</a>.</p>')
        return titulo, _layout(titulo, corpo, descadastro)
    dicas = _DICAS[grupo_do_cluster(cluster)]
    titulo, texto, link, ancora = dicas[(passo - 2) % len(dicas)]
    corpo = (saudacao + f'<p>{escape(texto)}</p>'
             f'<p><a href="https://www.turbovenda.com.br{link}?utm_source=email&utm_medium=sequencia&utm_campaign='
             f'{escape(cluster or "geral")}">{escape(ancora)}</a></p>')
    return titulo, _layout(titulo, corpo, descadastro)


def registrar(cur, dados, agora=None):
    """Grava o lead e devolve o id. dados: email, nome, empresa, isca, cluster,
    pagina, consulta, utm, first_touch, last_touch, resultado, opt_in."""
    agora = agora or _dt.datetime.now(_dt.timezone.utc)
    # o curso por e-mail é o próprio pedido: as aulas saem mesmo sem opt-in de marketing
    pediu_sequencia = dados.get('opt_in') or iscas.ISCAS.get(dados['isca'], {}).get('so_inscricao')
    proximo = agora + _dt.timedelta(days=AGENDA[0]) if pediu_sequencia else None
    cur.execute("""INSERT INTO leads_isca (email, nome, empresa, isca, cluster, pagina, consulta, utm, first_touch,
                       last_touch, resultado, opt_in_marketing, passo_sequencia, proximo_email_em, user_id, criado_em)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s, %s, %s) RETURNING id""",
                (dados['email'].strip().lower()[:200], (dados.get('nome') or '')[:120] or None,
                 (dados.get('empresa') or '')[:160] or None, dados['isca'], dados.get('cluster'),
                 (dados.get('pagina') or '')[:300], (dados.get('consulta') or '')[:200] or None,
                 json.dumps(dados.get('utm') or {}), json.dumps(dados.get('first_touch')) if dados.get('first_touch') else None,
                 json.dumps(dados.get('last_touch')) if dados.get('last_touch') else None,
                 json.dumps(dados.get('resultado') or {}, ensure_ascii=False), bool(dados.get('opt_in')), proximo,
                 dados.get('user_id'), agora))
    row = cur.fetchone()
    return row['id'] if isinstance(row, dict) else row[0]


def alerta_dono(lead_id, dados):
    """Assunto e corpo do aviso imediato ao dono."""
    isca = iscas.ISCAS.get(dados['isca'], {}).get('nome', dados['isca'])
    linhas = [('E-mail', dados['email']), ('Nome', dados.get('nome') or '—'), ('Empresa', dados.get('empresa') or '—'),
              ('Isca', isca), ('Resultado', (dados.get('resultado') or {}).get('resumo', '—')),
              ('Página', dados.get('pagina') or '—'), ('Busca', dados.get('consulta') or '—'),
              ('Origem', json.dumps(dados.get('utm') or {}, ensure_ascii=False)),
              ('Aceitou marketing', 'sim' if dados.get('opt_in') else 'não')]
    corpo = ''.join(f'<p><b>{escape(k)}:</b> {escape(str(v))}</p>' for k, v in linhas)
    corpo += '<p><a href="https://www.turbovenda.com.br/admin/crescimento#leads">Ver no painel</a></p>'
    return f'Novo lead #{lead_id}: {isca}', _layout('Novo lead de isca', corpo, None)


def rodar(conn, enviar, link_descadastro, agora=None, oferta_dias=14, limite=200):
    """Manda os passos vencidos da sequência (só com opt-in). Devolve o total enviado."""
    agora = agora or _dt.datetime.now(_dt.timezone.utc)
    cur = conn.cursor()
    cur.execute("""SELECT id, email, nome, cluster, isca, passo_sequencia, criado_em FROM leads_isca
                   WHERE (opt_in_marketing OR isca = ANY(%s)) AND descadastrado_em IS NULL
                     AND proximo_email_em IS NOT NULL
                     AND proximo_email_em <= %s AND passo_sequencia < 5
                   ORDER BY proximo_email_em LIMIT %s""",
                (SO_INSCRICAO, agora, limite))
    enviados = 0
    for lead in cur.fetchall():
        passo = lead['passo_sequencia'] + 1
        assunto, html = email_passo(passo, lead['cluster'], lead['nome'], link_descadastro(lead['id']),
                                    oferta_dias, lead['isca'])
        if not enviar(lead['email'], assunto, html):
            continue
        criado = lead['criado_em']
        if criado.tzinfo is None:
            criado = criado.replace(tzinfo=_dt.timezone.utc)
        proximo = criado + _dt.timedelta(days=AGENDA[passo - 1]) if passo - 1 < len(AGENDA) else None
        if proximo is not None and proximo <= agora:
            proximo = agora + _dt.timedelta(days=1)
        cur.execute('UPDATE leads_isca SET passo_sequencia = %s, proximo_email_em = %s WHERE id = %s',
                    (passo, proximo if passo < 5 else None, lead['id']))
        conn.commit()
        enviados += 1
    return enviados


def descadastrar(cur, lead_id, agora=None):
    """Descadastra o lead e todos os outros pedidos do mesmo e-mail."""
    agora = agora or _dt.datetime.now(_dt.timezone.utc)
    cur.execute('SELECT email FROM leads_isca WHERE id = %s', (lead_id,))
    row = cur.fetchone()
    if not row:
        return 0
    cur.execute("""UPDATE leads_isca SET descadastrado_em = %s, proximo_email_em = NULL
                   WHERE LOWER(email) = LOWER(%s) AND descadastrado_em IS NULL""", (agora, row['email']))
    return cur.rowcount


def conversao_por_isca(cur, dias=28):
    cur.execute("""SELECT props->>'isca_id' AS isca, nome, COUNT(*) AS n FROM eventos
                   WHERE criado_em > now() - make_interval(days => %s)
                     AND nome IN ('isca_vista', 'isca_iniciada', 'isca_concluida', 'lead_capturado', 'cta_produto_clicado')
                   GROUP BY 1, 2""", (dias,))
    saida = {}
    for r in cur.fetchall():
        saida.setdefault(r['isca'] or '-', {})[r['nome']] = r['n']
    return saida


# usado pelo painel e pelo resumo semanal
def ofertas_de_cluster():
    return {c: v['isca'] for c, v in cfg.CLUSTERS.items()}
