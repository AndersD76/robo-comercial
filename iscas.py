# -*- coding: utf-8 -*-
"""Iscas: ferramentas grátis que dão parte do resultado na tela (sem
cadastro, com endereço compartilhável) e o resultado completo por e-mail.

Cada isca define os campos do formulário (GET, para o resultado ficar na
URL) e uma função `calcular(params, ctx)` pura que devolve o resumo da tela
e o completo do e-mail. `ctx` traz o que vem do banco (contagens, CNAE,
preços) para manter este módulo testável sem banco.

Nada de número inventado: os cálculos usam só o que a pessoa digitou, os
preços reais do TurboVenda e as contagens da base da Receita.
"""
import math
from html import escape

import lgpd_textos

UTM = 'utm_source=site&utm_medium=isca&utm_campaign='


def _cta(isca_id, texto='Testar o TurboVenda grátis'):
    return (texto, f'/cadastro?{UTM}{isca_id}')


def _brl(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return '—'
    s = f'{v:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return 'R$ ' + (s[:-3] if s.endswith(',00') else s)


def _int(v):
    try:
        return f'{int(round(float(v))):,}'.replace(',', '.')
    except (TypeError, ValueError):
        return '—'


def _num(params, nome, padrao=0.0, minimo=0.0, maximo=1e12):
    """Número digitado: "1234.5" (campo numérico) ou "1.234,50" (à mão)."""
    bruto = params.get(nome, padrao)
    s = str(bruto).strip().replace('R$', '').replace(' ', '').replace('%', '')
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    try:
        v = float(s) if s else float(padrao)
    except (TypeError, ValueError):
        v = float(padrao)
    if math.isnan(v) or math.isinf(v):
        v = float(padrao)
    return max(minimo, min(maximo, v))


def _lista_html(itens):
    return '<ul class="lista">' + ''.join(f'<li>{i}</li>' for i in itens) + '</ul>'


def _tabela(cab, linhas):
    h = '<table class="dados"><thead><tr>' + ''.join(f'<th>{escape(c)}</th>' for c in cab) + '</tr></thead><tbody>'
    for linha in linhas:
        h += '<tr>' + ''.join(f'<td{" class=num" if i else ""}>{c}</td>' for i, c in enumerate(linha)) + '</tr>'
    return h + '</tbody></table>'


# ---------------------------------------------------------------------------
# 1. Diagnóstico de prospecção (nota 0–100)
# ---------------------------------------------------------------------------
_DIAG = [
    ('icp', 'Tenho o cliente ideal escrito (segmento, porte, região e cargo de quem decide).',
     'Escreva o cliente ideal antes de montar qualquer lista', '/ferramentas/gerador-de-icp'),
    ('lista', 'Minha lista vem de dados verificados (CNPJ ativo, telefone ou e-mail conferidos).',
     'Monte a lista a partir de CNPJ ativo e contato público', '/ferramentas/lista-de-empresas'),
    ('volume', 'Sei quantos contatos novos preciso por mês para bater a meta.',
     'Calcule de trás para frente quantos leads a meta pede', '/ferramentas/calculadora-de-leads'),
    ('cadencia', 'Sigo uma cadência definida (quantos toques e com que intervalo).',
     'Defina uma cadência fixa de toques', '/ferramentas/gerador-de-cadencia-de-prospeccao'),
    ('canais', 'Uso mais de um canal (e-mail, telefone, WhatsApp, LinkedIn).',
     'Combine pelo menos dois canais na mesma cadência', '/ferramentas/gerador-de-cadencia-de-prospeccao'),
    ('personaliza', 'Personalizo a primeira mensagem com algo da empresa do lead.',
     'Abra a primeira mensagem com um fato da empresa do lead', '/ferramentas/gerador-de-mensagem-de-prospeccao'),
    ('registro', 'Registro cada contato num CRM ou numa planilha.',
     'Registre todo contato, com data e próximo passo', '/ferramentas/planilha-de-prospeccao'),
    ('medicao', 'Meço a taxa de resposta e de reunião por canal.',
     'Meça resposta e reunião por canal e por etapa', '/ferramentas/calculadora-de-funil-de-vendas'),
    ('decisor', 'Falo com quem decide (sócio ou gestor), não só com a recepção.',
     'Chegue ao decisor: o sócio consta no CNPJ', '/blog/como-encontrar-o-decisor-da-empresa'),
    ('lgpd', 'Ofereço descadastro e sei a base legal que uso para prospectar (LGPD).',
     'Registre a base legal e ofereça descadastro em todo contato', '/ferramentas/checklist-lgpd-prospeccao'),
]
_RESP = {'sim': 2, 'as_vezes': 1, 'nao': 0}


def diagnostico(params, ctx=None):
    pontos, fracos = 0, []
    respondidas = 0
    for chave, _, rec, link in _DIAG:
        v = params.get(chave)
        if v in _RESP:
            respondidas += 1
            pontos += _RESP[v]
            if _RESP[v] < 2:
                fracos.append((_RESP[v], rec, link))
    if respondidas < len(_DIAG):
        return None
    nota = round(pontos / (2 * len(_DIAG)) * 100)
    nivel = ('Inicial' if nota < 40 else 'Em construção' if nota < 70 else 'Estruturada' if nota < 90 else 'Avançada')
    fracos.sort(key=lambda x: x[0])
    tela = (f'<div class="destaques"><div class="destaque"><b>{nota}/100</b><span>nota da sua prospecção</span></div>'
            f'<div class="destaque"><b>{nivel}</b><span>nível</span></div>'
            f'<div class="destaque"><b>{len(fracos)}</b><span>pontos a melhorar</span></div></div>')
    if fracos:
        tela += '<h3>Comece por aqui</h3>' + _lista_html(
            f'<a href="{link}">{escape(rec)}</a>' for _, rec, link in fracos[:3])
    completo = tela + ('<h3>Todos os pontos, em ordem</h3>' + _lista_html(
        f'<a href="https://www.turbovenda.com.br{link}">{escape(rec)}</a>' for _, rec, link in fracos)
        if fracos else '<p>Todas as práticas em dia. Próximo passo: escalar o volume sem perder a personalização.</p>')
    completo += ('<h3>Plano de 30 dias</h3>' + _lista_html([
        'Semana 1: cliente ideal escrito e lista de 200 empresas que se encaixam nele.',
        'Semana 2: cadência de 6 toques em 2 canais, com mensagem personalizada.',
        'Semana 3: registrar cada contato e medir resposta por canal.',
        'Semana 4: cortar o canal que não responde e dobrar o que responde.']))
    return {'tela': tela, 'completo': completo, 'dados': {'nota': nota, 'nivel': nivel},
            'resumo': f'Nota {nota}/100 ({nivel})'}


# ---------------------------------------------------------------------------
# 2. CAC, LTV e payback
# ---------------------------------------------------------------------------
def cac(params, ctx=None):
    mkt = _num(params, 'marketing', 0, 0, 1e9)
    vendas = _num(params, 'vendas', 0, 0, 1e9)
    novos = _num(params, 'novos', 0, 0, 1e6)
    ticket = _num(params, 'ticket', 0, 0, 1e9)
    meses = _num(params, 'meses', 12, 1, 240)
    margem = _num(params, 'margem', 100, 1, 100)
    if novos <= 0 or (mkt + vendas) <= 0 or ticket <= 0:
        return None
    custo = (mkt + vendas) / novos
    ltv = ticket * meses * margem / 100
    razao = ltv / custo if custo else 0
    payback = custo / (ticket * margem / 100)
    leitura = ('cada cliente custa mais do que devolve' if razao < 1 else
               'o cliente paga o custo, mas sobra pouco para crescer' if razao < 3 else
               'cada cliente devolve três vezes ou mais o que custou')
    tela = (f'<div class="destaques"><div class="destaque"><b>{_brl(custo)}</b><span>CAC (custo por cliente)</span></div>'
            f'<div class="destaque"><b>{_brl(ltv)}</b><span>LTV (margem no tempo de vida)</span></div>'
            f'<div class="destaque"><b>{razao:.1f}x</b><span>LTV ÷ CAC</span></div>'
            f'<div class="destaque"><b>{payback:.1f} meses</b><span>para recuperar o CAC</span></div></div>'
            f'<p>Com esses números, {leitura}. Uma regra prática muito usada em empresas de assinatura é buscar '
            f'LTV de pelo menos 3 vezes o CAC; é uma referência, não uma norma.</p>')
    completo = tela + _tabela(['Item', 'Valor'], [
        ['Gasto de marketing por mês', _brl(mkt)], ['Gasto de vendas por mês', _brl(vendas)],
        ['Clientes novos por mês', _int(novos)], ['Ticket mensal', _brl(ticket)],
        ['Meses que o cliente fica', _int(meses)], ['Margem', f'{margem:.0f}%'],
        ['CAC', _brl(custo)], ['LTV', _brl(ltv)], ['LTV ÷ CAC', f'{razao:.1f}x'], ['Payback', f'{payback:.1f} meses']])
    completo += ('<h3>Como baixar o CAC</h3>' + _lista_html([
        'Prospectar só quem se encaixa no cliente ideal: menos contato perdido por venda.',
        'Automatizar a montagem da lista e o primeiro contato: o custo de vendas cai sem cair o volume.',
        'Medir a conversão por etapa e atacar a pior: cada ponto ganho ali reduz o CAC inteiro.']))
    return {'tela': tela, 'completo': completo, 'resumo': f'CAC {_brl(custo)}, LTV/CAC {razao:.1f}x',
            'dados': {'cac': round(custo, 2), 'ltv': round(ltv, 2), 'razao': round(razao, 2)}}


# ---------------------------------------------------------------------------
# 3. Quanto custa prospectar à mão (e quanto sobra automatizando)
# ---------------------------------------------------------------------------
def roi(params, ctx=None):
    precos = (ctx or {}).get('precos') or {'starter': 97.0, 'pro': 297.0}
    horas = _num(params, 'horas', 0, 0, 168)
    custo_hora = _num(params, 'custo_hora', 0, 0, 10000)
    leads = _num(params, 'leads', 0, 0, 100000)
    pct = _num(params, 'automatizavel', 50, 0, 100)
    plano = params.get('plano') if params.get('plano') in precos else 'starter'
    if horas <= 0 or custo_hora <= 0:
        return None
    semanas = 52 / 12
    custo_mes = horas * semanas * custo_hora
    horas_livres = horas * semanas * pct / 100
    valor_livre = horas_livres * custo_hora
    preco = float(precos[plano])
    saldo = valor_livre - preco
    por_lead = custo_mes / (leads * semanas) if leads else None
    tela = (f'<div class="destaques"><div class="destaque"><b>{_brl(custo_mes)}</b><span>custo da prospecção à mão por mês</span></div>'
            f'<div class="destaque"><b>{_int(horas_livres)} h</b><span>horas que voltam por mês</span></div>'
            f'<div class="destaque"><b>{_brl(saldo)}</b><span>saldo depois do plano {plano.title()} ({_brl(preco)})</span></div></div>')
    if por_lead:
        tela += f'<p>Hoje cada lead custa {_brl(por_lead)} em horas de trabalho.</p>'
    tela += (f'<p>O cálculo usa só os seus números: {pct:.0f}% do tempo em tarefas que um robô faz '
             '(achar empresas, conferir telefone e e-mail, montar a lista e mandar o primeiro contato).</p>')
    completo = tela + _tabela(['Item', 'Valor'], [
        ['Horas de prospecção por semana', _int(horas)], ['Custo da hora', _brl(custo_hora)],
        ['Leads por semana', _int(leads)], ['Parte automatizável', f'{pct:.0f}%'],
        ['Custo por mês', _brl(custo_mes)], ['Horas liberadas por mês', _int(horas_livres)],
        ['Valor das horas liberadas', _brl(valor_livre)], [f'Plano {plano.title()}', _brl(preco)],
        ['Saldo por mês', _brl(saldo)]])
    return {'tela': tela, 'completo': completo, 'resumo': f'Saldo de {_brl(saldo)} por mês',
            'dados': {'custo_mes': round(custo_mes, 2), 'saldo': round(saldo, 2)}}


# ---------------------------------------------------------------------------
# 4. Cliente ideal (ICP) com a contagem real da base
# ---------------------------------------------------------------------------
PORTES = {'todos': 'Todos os portes', '01': 'Microempresa', '03': 'Pequena (EPP)', '05': 'Média ou grande'}


def icp(params, ctx=None):
    ctx = ctx or {}
    segmentos = ctx.get('segmentos') or {}
    seg = params.get('segmento')
    if seg not in segmentos:
        return None
    uf = (params.get('uf') or '').upper()
    uf = uf if uf in (ctx.get('ufs') or {}) else ''
    porte = params.get('porte') if params.get('porte') in PORTES else 'todos'
    cargo = escape((params.get('cargo') or 'sócio ou diretor').strip()[:60])
    dor = escape((params.get('dor') or '').strip()[:200])
    info = segmentos[seg]
    contar = ctx.get('contar')
    n = contar(info['codigo'], uf or None, None if porte == 'todos' else porte) if contar else None
    onde = ctx['ufs'][uf] if uf else 'Brasil'
    link = f"/empresas/{seg}/estado/{uf.lower()}" if uf else f'/empresas/{seg}'
    tela = '<div class="destaques">'
    if n is not None:
        tela += f'<div class="destaque"><b>{_int(n)}</b><span>empresas ativas com contato no perfil ({escape(onde)})</span></div>'
    tela += (f'<div class="destaque"><b>{escape(info["label"])}</b><span>segmento</span></div>'
             f'<div class="destaque"><b>{escape(PORTES[porte])}</b><span>porte</span></div></div>')
    tela += (f'<p><strong>Seu cliente ideal:</strong> {escape(info["label"].lower())} em {escape(onde)}, '
             f'{escape(PORTES[porte].lower())}, falando com {cargo}'
             + (f', que sofre com {dor}' if dor else '') + '.</p>'
             f'<p><a href="{link}">Ver as empresas desse perfil na base da Receita</a></p>')
    perguntas = [
        f'A empresa é de {escape(info["label"].lower())} e está ativa na Receita?',
        f'Fica em {escape(onde)} ou atende essa região?',
        'Tem porte para pagar o seu ticket sem aperto?',
        f'Você consegue falar com {cargo} em até dois toques?',
        'Ela tem o problema que você resolve agora, não "um dia"?',
    ]
    completo = tela + '<h3>5 perguntas para qualificar cada lead</h3>' + _lista_html(perguntas)
    completo += ('<h3>Gancho da primeira mensagem</h3><p>Comece pelo que é verdade sobre a empresa dele '
                 f'(cidade, tempo de mercado, segmento) e só depois diga como você ajuda {cargo} '
                 + (f'com {dor}' if dor else 'a vender mais') + '.</p>')
    return {'tela': tela, 'completo': completo, 'resumo': f'ICP: {info["label"]} em {onde}',
            'dados': {'segmento': seg, 'uf': uf, 'porte': porte, 'empresas': n}}


# ---------------------------------------------------------------------------
# 5. Cadência de prospecção
# ---------------------------------------------------------------------------
_CANAIS = {'email': 'E-mail', 'whatsapp': 'WhatsApp', 'ligacao': 'Ligação', 'linkedin': 'LinkedIn'}
_PASSOS = {
    'email': ['E-mail curto com um fato da empresa e uma pergunta', 'E-mail de valor: um dado ou caso do setor',
              'E-mail de encerramento: "posso fechar seu contato?"'],
    'whatsapp': ['WhatsApp de apresentação em 2 linhas, sem link', 'WhatsApp com a pergunta direta sobre a dor'],
    'ligacao': ['Ligação para confirmar quem decide', 'Ligação de 3 minutos para marcar a conversa'],
    'linkedin': ['Pedido de conexão sem pitch', 'Mensagem no LinkedIn comentando algo da empresa'],
}


def cadencia(params, ctx=None):
    canais = [c for c in _CANAIS if params.get(f'canal_{c}') in ('1', 'on', 'sim', True)]
    if not canais:
        return None
    dias = int(_num(params, 'dias', 14, 7, 30))
    passos = []
    for i in range(max(len(_PASSOS[c]) for c in canais)):
        for c in canais:
            if i < len(_PASSOS[c]):
                passos.append((c, _PASSOS[c][i]))
    passos = passos[:8]
    intervalo = max(1, (dias - 1) // max(1, len(passos) - 1)) if len(passos) > 1 else 1
    linhas = [[f'Dia {1 + k * intervalo}', escape(_CANAIS[c]), escape(t)] for k, (c, t) in enumerate(passos)]
    tela = _tabela(['Quando', 'Canal', 'O que fazer'], linhas[:4])
    if len(linhas) > 4:
        tela += f'<p>Mais {len(linhas) - 4} toques no plano completo, com o texto de cada um.</p>'
    modelos = {
        'email': '<pre>Assunto: {empresa} + {cidade}\n\nOlá, {nome}. Vi que a {empresa} atua em {cidade} há {anos} anos.\n'
                 'Ajudo empresas como a sua a {resultado}. Faz sentido conversar 15 minutos esta semana?</pre>',
        'whatsapp': '<pre>Olá, {nome}! Aqui é {seu_nome}, da {sua_empresa}. Trabalho com {segmento} em {cidade}.\n'
                    'Posso te mandar uma ideia rápida sobre {dor}?</pre>',
        'ligacao': '<pre>"Oi, {nome}, é {seu_nome}. Liguei porque ajudo {segmento} a {resultado}.\n'
                   'Você é a pessoa certa para falar disso ou seria outra pessoa?"</pre>',
        'linkedin': '<pre>Olá, {nome}. Acompanho o setor de {segmento} em {cidade} e gostei do trabalho da {empresa}.\n'
                    'Vamos nos conectar?</pre>',
    }
    completo = _tabela(['Quando', 'Canal', 'O que fazer'], linhas) + '<h3>Modelos de mensagem</h3>' + ''.join(
        f'<h4>{_CANAIS[c]}</h4>{modelos[c]}' for c in canais)
    return {'tela': tela, 'completo': completo, 'resumo': f'Cadência de {len(linhas)} toques em {dias} dias',
            'dados': {'canais': canais, 'dias': dias, 'toques': len(linhas)}}


# ---------------------------------------------------------------------------
# 6. Checklist LGPD na prospecção (com o texto oficial do artigo)
# ---------------------------------------------------------------------------
_ART = lgpd_textos.ARTIGOS
_LGPD = [
    ('base_legal', 'Sei qual base legal uso para prospectar e a registrei', '7', 9,
     'Na prospecção B2B costuma-se usar o legítimo interesse (art. 7º, IX), que exige avaliação e registro.'),
    ('avaliacao', 'Fiz e guardei a avaliação do legítimo interesse', '10', 0,
     'O art. 10 limita o legítimo interesse a finalidades legítimas a partir de situações concretas.'),
    ('minimo', 'Uso só os dados estritamente necessários', '10', 3,
     'Com legítimo interesse, só os dados estritamente necessários podem ser tratados (art. 10, § 1º).'),
    ('transparencia', 'Digo quem sou e de onde veio o contato já na primeira mensagem', '10', 4,
     'O controlador deve garantir a transparência do tratamento baseado em legítimo interesse (art. 10, § 2º).'),
    ('publico', 'Uso dados públicos considerando a finalidade e a boa-fé da publicação', '7', 13,
     'Dado de acesso público também tem regra: finalidade, boa-fé e interesse público (art. 7º, § 3º).'),
    ('descadastro', 'Ofereço descadastro simples e paro na hora', '18', 12,
     'O titular pode se opor a tratamento sem consentimento quando houver descumprimento da lei (art. 18, § 2º).'),
    ('prazo', 'Respondo pedido de acesso aos dados em até 15 dias', '19', 2,
     'A declaração completa ao titular tem prazo de até 15 dias (art. 19, II).'),
    ('registro', 'Mantenho registro das operações de tratamento', '37', 0,
     'Controlador e operador devem registrar as operações, em especial com legítimo interesse (art. 37).'),
    ('canal', 'Tenho canal público para pedidos de titulares (e encarregado, se a lei me exigir)', '41', 1,
     'A identidade e o contato do encarregado devem ser públicos (art. 41, § 1º); a ANPD pode dispensar a indicação conforme o porte (art. 41, § 3º).'),
    ('seguranca', 'Protejo a base com medidas de segurança técnicas e administrativas', '46', 0,
     'Os agentes de tratamento devem adotar medidas de segurança aptas a proteger os dados (art. 46).'),
]


def _trecho(art, i):
    partes = _ART.get(art) or []
    return partes[i] if 0 <= i < len(partes) else (partes[0] if partes else '')


def checklist_lgpd(params, ctx=None):
    marcados = [k for k, *_ in _LGPD if params.get(k) in ('1', 'on', 'sim', True)]
    if 'enviado' not in params and not marcados:
        return None
    faltam = [x for x in _LGPD if x[0] not in marcados]
    nota = round(len(marcados) / len(_LGPD) * 100)
    tela = (f'<div class="destaques"><div class="destaque"><b>{len(marcados)}/{len(_LGPD)}</b><span>práticas em dia</span></div>'
            f'<div class="destaque"><b>{nota}%</b><span>de aderência</span></div></div>')
    if faltam:
        tela += '<h3>O que falta</h3>' + _lista_html(escape(x[1]) for x in faltam[:3])
    completo = tela + ''.join(
        f'<h4>{escape(x[1])}</h4><p>{escape(x[4])}</p><blockquote>{escape(_trecho(x[2], x[3]))}</blockquote>'
        for x in faltam)
    completo += (f'<p><small>Texto da lei: {escape(lgpd_textos.FONTE["nome"])}, consultado em 26/11/2026 '
                 f'({lgpd_textos.FONTE["url"]}). Este checklist é informativo e não substitui orientação jurídica.</small></p>')
    return {'tela': tela, 'completo': completo, 'resumo': f'{len(marcados)} de {len(_LGPD)} práticas',
            'dados': {'marcados': marcados, 'nota': nota}}


# ---------------------------------------------------------------------------
# 7. Consulta de CNAE (descrição oficial do IBGE + empresas ativas)
# ---------------------------------------------------------------------------
def consulta_cnae(params, ctx=None):
    q = (params.get('q') or '').strip()[:80]
    buscar = (ctx or {}).get('buscar_cnae')
    if len(q) < 3 or not buscar:
        return None
    achados = buscar(q, 50)
    if not achados:
        return {'tela': f'<p>Nenhum CNAE com "{escape(q)}". Tente uma palavra mais geral.</p>',
                'completo': '', 'resumo': 'Sem resultado', 'dados': {'q': q, 'n': 0}}
    linhas = [[f'<a href="/cnae/{a["codigo"]}">{escape(a["formatado"])}</a> {escape(a["descricao"].capitalize())}',
               _int(a.get('empresas')) if a.get('empresas') is not None else '—'] for a in achados]
    tela = _tabela(['CNAE', 'Empresas ativas'], linhas[:10])
    if len(linhas) > 10:
        tela += f'<p>Mais {len(linhas) - 10} códigos na lista completa por e-mail.</p>'
    completo = _tabela(['CNAE', 'Empresas ativas'], [[c.replace('href="/', 'href="https://www.turbovenda.com.br/'), n]
                                                      for c, n in linhas])
    return {'tela': tela, 'completo': completo, 'resumo': f'{len(achados)} CNAEs para "{q}"',
            'dados': {'q': q, 'n': len(achados)}}


# ---------------------------------------------------------------------------
# 8. Planilha de prospecção (modelo para baixar)
# ---------------------------------------------------------------------------
COLUNAS_PLANILHA = ['Empresa', 'CNPJ', 'Cidade/UF', 'Segmento', 'Decisor', 'Cargo', 'Telefone', 'E-mail',
                    'Canal do 1º contato', 'Data do 1º contato', 'Próximo passo', 'Data do próximo passo',
                    'Status', 'Observações']
EXEMPLO_PLANILHA = [
    ['Exemplo Indústria Ltda', '00.000.000/0001-00', 'Caxias do Sul/RS', 'Usinagem', 'Nome do sócio', 'Sócio-administrador',
     '(54) 0000-0000', 'contato@exemplo.com.br', 'E-mail', '01/12', 'Ligar para marcar conversa', '04/12', 'Contatado', ''],
]


def planilha_csv():
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=';')
    w.writerow(COLUNAS_PLANILHA)
    for linha in EXEMPLO_PLANILHA:
        w.writerow(linha)
    return '﻿' + buf.getvalue()


def planilha(params, ctx=None):
    tela = _tabela(COLUNAS_PLANILHA[:6], [[escape(c) for c in EXEMPLO_PLANILHA[0][:6]]])
    tela += '<p><a class="cta-btn" href="/ferramentas/planilha-de-prospeccao.csv" download>Baixar a planilha (CSV, abre no Excel)</a></p>'
    completo = ('<p>A planilha tem 14 colunas: ' + escape(', '.join(COLUNAS_PLANILHA)) + '.</p>'
                '<h3>Como usar</h3>' + _lista_html([
                    'Uma linha por empresa; o decisor vem do quadro de sócios do CNPJ.',
                    'Toda linha tem próximo passo e data: lead sem próximo passo é lead esquecido.',
                    'Status: Novo → Contatado → Respondeu → Reunião → Proposta → Ganho/Perdido.',
                    'Toda sexta, filtre por "Data do próximo passo" da semana seguinte.'])
                + '<p><a href="https://www.turbovenda.com.br/ferramentas/planilha-de-prospeccao.csv">Baixar a planilha</a></p>')
    return {'tela': tela, 'completo': completo, 'resumo': 'Planilha de prospecção', 'dados': {}}


# ---------------------------------------------------------------------------
# 9. Funil de vendas: conversão por etapa e o gargalo
# ---------------------------------------------------------------------------
_ETAPAS = [('leads', 'Leads contatados'), ('respostas', 'Responderam'), ('reunioes', 'Reuniões'),
           ('propostas', 'Propostas'), ('vendas', 'Vendas')]


def funil(params, ctx=None):
    v = [_num(params, k, 0, 0, 1e7) for k, _ in _ETAPAS]
    if v[0] <= 0 or any(v[i] > v[i - 1] for i in range(1, len(v))):
        return None
    taxas = [(v[i] / v[i - 1] if v[i - 1] else 0) for i in range(1, len(v))]
    pior = min(range(len(taxas)), key=lambda i: taxas[i])
    ganho = _num(params, 'melhora', 20, 1, 100) / 100
    novas = list(v)
    novas[pior + 1] = v[pior + 1] * (1 + ganho)
    for i in range(pior + 2, len(v)):
        novas[i] = novas[i - 1] * taxas[i - 1]
    linhas = [[escape(_ETAPAS[i + 1][1]), f'{taxas[i] * 100:.1f}%'] for i in range(len(taxas))]
    tela = _tabela(['Etapa', 'Conversão da etapa anterior'], linhas)
    tela += (f'<p>O gargalo é <strong>{escape(_ETAPAS[pior + 1][1].lower())}</strong> ({taxas[pior] * 100:.1f}%). '
             f'Melhorando essa etapa em {ganho * 100:.0f}%, as vendas vão de {_int(v[-1])} para {_int(novas[-1])} por mês, '
             'com o mesmo número de leads.</p>')
    dicas = {0: 'Mensagem mais curta, personalizada e com uma pergunta só.',
             1: 'Peça a reunião com dia e hora, e confirme na véspera.',
             2: 'Descubra a dor e quem decide antes de mandar proposta.',
             3: 'Proposta com prazo, prova e próximo passo marcado.'}
    completo = tela + f'<h3>Como atacar o gargalo</h3><p>{escape(dicas[pior])}</p>'
    return {'tela': tela, 'completo': completo, 'resumo': f'Gargalo: {_ETAPAS[pior + 1][1]}',
            'dados': {'taxas': [round(t, 4) for t in taxas], 'gargalo': _ETAPAS[pior + 1][0]}}


# ---------------------------------------------------------------------------
# 10. Mini-curso por e-mail (só inscrição; as aulas vão na sequência)
# ---------------------------------------------------------------------------
AULAS_CURSO = [
    ('Dia 1: quem é o seu cliente ideal',
     '<p>Antes de prospectar, escreva em uma frase: segmento, porte, região e cargo de quem decide. '
     'Tudo o que não cabe nessa frase é perda de tempo na lista.</p>'
     '<p>Ferramenta: <a href="https://www.turbovenda.com.br/ferramentas/gerador-de-icp">gerador de cliente ideal</a>.</p>'),
    ('Dia 2: a lista certa vale mais que a mensagem perfeita',
     '<p>Monte a lista a partir de empresas ativas na Receita, com telefone ou e-mail público e o sócio que decide. '
     'Lista ruim derruba qualquer texto.</p>'
     '<p>Ferramenta: <a href="https://www.turbovenda.com.br/ferramentas/lista-de-empresas">lista de empresas grátis</a>.</p>'),
    ('Dia 3: a primeira mensagem',
     '<p>Duas a quatro linhas: um fato verdadeiro da empresa, o resultado que você entrega e uma pergunta. '
     'Sem anexo e sem link na primeira.</p>'
     '<p>Ferramenta: <a href="https://www.turbovenda.com.br/ferramentas/gerador-de-mensagem-de-prospeccao">gerador de mensagem</a>.</p>'),
    ('Dia 4: cadência e follow-up',
     '<p>A maior parte das respostas vem depois do primeiro toque. Defina quantos toques, em quais canais e com que '
     'intervalo, e siga o plano para todo lead.</p>'
     '<p>Ferramenta: <a href="https://www.turbovenda.com.br/ferramentas/gerador-de-cadencia-de-prospeccao">gerador de cadência</a>.</p>'),
    ('Dia 5: medir e escalar',
     '<p>Meça resposta, reunião e venda por canal. Corte o que não responde, dobre o que responde e automatize o que '
     'é repetitivo: achar empresas, conferir contato e mandar o primeiro toque.</p>'
     '<p>O TurboVenda faz essa parte sozinho: <a href="https://www.turbovenda.com.br/cadastro?utm_source=email&'
     'utm_medium=isca&utm_campaign=mini-curso">teste grátis</a>.</p>'),
]


def curso(params, ctx=None):
    tela = _lista_html(escape(t) for t, _ in AULAS_CURSO)
    return {'tela': tela, 'completo': AULAS_CURSO[0][1], 'resumo': 'Mini-curso de prospecção B2B', 'dados': {}}


# ---------------------------------------------------------------------------
# Registro
# ---------------------------------------------------------------------------
_SN = [('sim', 'Sim'), ('as_vezes', 'Às vezes'), ('nao', 'Não')]

ISCAS = {
    'diagnostico-prospeccao': {
        'nome': 'Diagnóstico de prospecção B2B', 'cluster': 'prospeccao', 'slug': 'diagnostico-de-prospeccao',
        'titulo': 'Diagnóstico de prospecção B2B: teste grátis em 2 min',
        'descricao': 'Responda 10 perguntas e receba a nota da sua prospecção B2B, os 3 pontos a corrigir primeiro e um plano de 30 dias. Grátis, sem cadastro.',
        'h1': 'Diagnóstico de prospecção B2B',
        'resposta': 'O diagnóstico avalia 10 práticas de prospecção B2B, do cliente ideal à LGPD, e dá uma nota de 0 a 100. '
                    'Na tela você vê a nota, o nível e os três pontos que mais pesam; por e-mail recebe todos os pontos e um plano de 30 dias.',
        'campos': [{'nome': k, 'rotulo': p, 'tipo': 'escolha', 'opcoes': _SN} for k, p, _, _ in _DIAG],
        'calcular': diagnostico, 'botao': 'Ver minha nota',
    },
    'calculadora-cac': {
        'nome': 'Calculadora de CAC, LTV e payback', 'cluster': 'gestao', 'slug': 'calculadora-de-cac',
        'titulo': 'Calculadora de CAC e LTV: custo por cliente e payback',
        'descricao': 'Calcule o CAC (custo de aquisição de cliente), o LTV, a razão LTV/CAC e o payback com os seus números. Grátis e com resultado na hora.',
        'h1': 'Calculadora de CAC, LTV e payback',
        'resposta': 'CAC é quanto você gasta em marketing e vendas para ganhar um cliente: some os gastos do mês e divida pelos clientes novos. '
                    'A calculadora também mostra o LTV, a razão LTV/CAC e em quantos meses o cliente paga o que custou.',
        'campos': [{'nome': 'marketing', 'rotulo': 'Gasto de marketing por mês (R$)', 'tipo': 'numero'},
                   {'nome': 'vendas', 'rotulo': 'Gasto de vendas por mês: salários, comissões e ferramentas (R$)', 'tipo': 'numero'},
                   {'nome': 'novos', 'rotulo': 'Clientes novos por mês', 'tipo': 'numero'},
                   {'nome': 'ticket', 'rotulo': 'Quanto cada cliente paga por mês (R$)', 'tipo': 'numero'},
                   {'nome': 'meses', 'rotulo': 'Quantos meses um cliente fica, em média', 'tipo': 'numero', 'padrao': 12},
                   {'nome': 'margem', 'rotulo': 'Margem bruta (%)', 'tipo': 'numero', 'padrao': 60}],
        'calcular': cac, 'botao': 'Calcular CAC',
    },
    'calculadora-roi': {
        'nome': 'Calculadora de custo da prospecção manual', 'cluster': 'ferramentas', 'slug': 'calculadora-de-roi-da-prospeccao',
        'titulo': 'Quanto custa prospectar à mão? Calculadora de ROI',
        'descricao': 'Descubra quanto a prospecção manual custa por mês e por lead, e quanto sobra automatizando a parte repetitiva. Com os seus números.',
        'h1': 'Quanto custa a sua prospecção manual',
        'resposta': 'Multiplique as horas semanais de prospecção pelo custo da hora e por 4,33 semanas: esse é o custo mensal. '
                    'A calculadora mostra também o custo por lead e quanto sobra quando a parte repetitiva é automatizada.',
        'campos': [{'nome': 'horas', 'rotulo': 'Horas por semana prospectando (achar empresas, telefone, primeiro contato)', 'tipo': 'numero'},
                   {'nome': 'custo_hora', 'rotulo': 'Custo da hora de quem prospecta (R$)', 'tipo': 'numero'},
                   {'nome': 'leads', 'rotulo': 'Leads novos por semana', 'tipo': 'numero'},
                   {'nome': 'automatizavel', 'rotulo': 'Parte desse tempo que é tarefa repetitiva (%)', 'tipo': 'numero', 'padrao': 50},
                   {'nome': 'plano', 'rotulo': 'Plano para comparar', 'tipo': 'escolha',
                    'opcoes': [('starter', 'Starter'), ('pro', 'Pro')]}],
        'calcular': roi, 'botao': 'Calcular',
    },
    'gerador-icp': {
        'nome': 'Gerador de cliente ideal (ICP)', 'cluster': 'decisor', 'slug': 'gerador-de-icp',
        'titulo': 'Gerador de ICP: cliente ideal com dados da Receita',
        'descricao': 'Monte o perfil de cliente ideal (ICP) em 1 minuto e veja quantas empresas ativas se encaixam nele, com dados da Receita Federal. Grátis.',
        'h1': 'Gerador de cliente ideal (ICP)',
        'resposta': 'O ICP (perfil de cliente ideal) descreve a empresa que mais compra de você: segmento, porte, região e quem decide. '
                    'Escolha esses itens e a ferramenta mostra quantas empresas ativas da base da Receita se encaixam, com o link para a lista.',
        'campos': [{'nome': 'segmento', 'rotulo': 'Segmento do cliente', 'tipo': 'segmento'},
                   {'nome': 'uf', 'rotulo': 'Estado (vazio = Brasil)', 'tipo': 'uf'},
                   {'nome': 'porte', 'rotulo': 'Porte', 'tipo': 'escolha', 'opcoes': list(PORTES.items())},
                   {'nome': 'cargo', 'rotulo': 'Cargo de quem decide', 'tipo': 'texto', 'padrao': 'sócio ou diretor'},
                   {'nome': 'dor', 'rotulo': 'Problema que você resolve (opcional)', 'tipo': 'texto'}],
        'calcular': icp, 'botao': 'Gerar meu ICP',
    },
    'cadencia-prospeccao': {
        'nome': 'Gerador de cadência de prospecção', 'cluster': 'abordagem', 'slug': 'gerador-de-cadencia-de-prospeccao',
        'titulo': 'Cadência de prospecção: gerador grátis com modelos',
        'descricao': 'Escolha os canais e o prazo e receba uma cadência de prospecção dia a dia, com o modelo de mensagem de cada toque. Grátis.',
        'h1': 'Gerador de cadência de prospecção',
        'resposta': 'Cadência de prospecção é a sequência planejada de contatos com um lead: quantos toques, em quais canais e com que intervalo. '
                    'Marque os canais e o prazo; a ferramenta monta o plano dia a dia e manda os modelos de mensagem por e-mail.',
        'campos': [{'nome': f'canal_{c}', 'rotulo': n, 'tipo': 'checkbox'} for c, n in _CANAIS.items()] +
                  [{'nome': 'dias', 'rotulo': 'Prazo da cadência', 'tipo': 'escolha',
                    'opcoes': [('7', '7 dias'), ('14', '14 dias'), ('21', '21 dias')], 'padrao': '14'}],
        'calcular': cadencia, 'botao': 'Montar cadência',
    },
    'checklist-lgpd': {
        'nome': 'Checklist LGPD para prospecção', 'cluster': 'lgpd', 'slug': 'checklist-lgpd-prospeccao',
        'titulo': 'Checklist LGPD para prospecção B2B (com a lei)',
        'descricao': 'Confira em 10 itens se a sua prospecção B2B segue a LGPD, com o texto oficial de cada artigo. Grátis; não substitui orientação jurídica.',
        'h1': 'Checklist LGPD para prospecção B2B',
        'resposta': 'Prospectar empresas com dados pessoais (nome e e-mail do sócio, por exemplo) exige base legal, transparência e canal para o titular. '
                    'Marque o que você já faz; a ferramenta mostra o que falta e o artigo da LGPD de cada item.',
        'campos': [{'nome': k, 'rotulo': t, 'tipo': 'checkbox'} for k, t, *_ in _LGPD] +
                  [{'nome': 'enviado', 'tipo': 'oculto', 'padrao': '1'}],
        'calcular': checklist_lgpd, 'botao': 'Ver resultado',
    },
    'consulta-cnae': {
        'nome': 'Consulta de CNAE', 'cluster': 'cnae', 'slug': 'consulta-cnae',
        'titulo': 'Consulta CNAE: código, descrição e empresas ativas',
        'descricao': 'Busque o CNAE por palavra ou código e veja a descrição oficial do IBGE e quantas empresas ativas usam cada código. Grátis.',
        'h1': 'Consulta de CNAE por atividade ou código',
        'resposta': 'CNAE é o código da atividade econômica da empresa, definido pelo IBGE e usado no CNPJ. '
                    'Digite uma atividade ou um código: a consulta mostra a descrição oficial e quantas empresas ativas com contato usam cada um.',
        'campos': [{'nome': 'q', 'rotulo': 'Atividade ou código (ex.: transporte, 4930)', 'tipo': 'texto'}],
        'calcular': consulta_cnae, 'botao': 'Buscar CNAE',
    },
    'planilha-prospeccao': {
        'nome': 'Planilha de prospecção', 'cluster': 'prospeccao', 'slug': 'planilha-de-prospeccao',
        'titulo': 'Planilha de prospecção de clientes grátis (Excel)',
        'descricao': 'Baixe a planilha de prospecção de clientes com 14 colunas e exemplo preenchido. Abre no Excel e no Google Planilhas. Grátis.',
        'h1': 'Planilha de prospecção de clientes',
        'resposta': 'Uma planilha de prospecção registra cada empresa, quem decide, o canal do contato, o próximo passo e o status. '
                    'Esta tem 14 colunas e um exemplo preenchido; baixe direto ou receba por e-mail com o guia de uso.',
        'campos': [], 'calcular': planilha, 'botao': None, 'sempre': True,
    },
    'calculadora-funil': {
        'nome': 'Calculadora de funil de vendas', 'cluster': 'metas', 'slug': 'calculadora-de-funil-de-vendas',
        'titulo': 'Calculadora de funil de vendas: ache o gargalo',
        'descricao': 'Digite leads, respostas, reuniões, propostas e vendas do mês e descubra a conversão de cada etapa e onde está o gargalo do seu funil.',
        'h1': 'Calculadora de funil de vendas',
        'resposta': 'A conversão de cada etapa do funil é o número da etapa dividido pelo da anterior. '
                    'A etapa com a menor taxa é o gargalo; a calculadora mostra quantas vendas a mais vêm ao melhorar só ela.',
        'campos': [{'nome': k, 'rotulo': f'{n} por mês', 'tipo': 'numero'} for k, n in _ETAPAS] +
                  [{'nome': 'melhora', 'rotulo': 'Melhora na etapa mais fraca (%)', 'tipo': 'numero', 'padrao': 20}],
        'calcular': funil, 'botao': 'Achar o gargalo',
    },
    'mini-curso': {
        'nome': 'Mini-curso de prospecção B2B por e-mail', 'cluster': 'prospeccao', 'slug': 'curso-prospeccao-b2b-por-email',
        'titulo': 'Curso grátis de prospecção B2B por e-mail (5 dias)',
        'descricao': 'Cinco aulas curtas por e-mail, uma por dia: cliente ideal, lista, primeira mensagem, cadência e medição. Grátis.',
        'h1': 'Curso de prospecção B2B por e-mail',
        'resposta': 'São cinco aulas curtas, uma por dia, com uma ferramenta grátis em cada: cliente ideal, lista de empresas, '
                    'primeira mensagem, cadência de follow-up e medição. Basta o e-mail para receber a primeira aula hoje.',
        'campos': [], 'calcular': curso, 'botao': None, 'sempre': True, 'so_inscricao': True,
    },
    # As três ferramentas que já existiam (rotas próprias no app)
    'lista-de-empresas': {'nome': 'Lista de empresas por cidade e segmento', 'cluster': 'listas',
                          'slug': 'lista-de-empresas', 'existente': True},
    'gerador-de-mensagem': {'nome': 'Gerador de mensagem de prospecção', 'cluster': 'abordagem',
                            'slug': 'gerador-de-mensagem-de-prospeccao', 'existente': True},
    'calculadora-de-meta': {'nome': 'Calculadora de leads para a meta', 'cluster': 'metas',
                            'slug': 'calculadora-de-leads', 'existente': True},
}
POR_SLUG = {v['slug']: k for k, v in ISCAS.items()}
NOVAS = [k for k, v in ISCAS.items() if not v.get('existente')]


def url_de(isca_id):
    return '/ferramentas/' + ISCAS[isca_id]['slug']


def cta(isca_id):
    return _cta(isca_id)


def ler_params(isca_id, args):
    """Só os campos da isca, como texto curto (nada de parâmetro solto)."""
    campos = ISCAS[isca_id].get('campos') or []
    saida = {}
    for c in campos:
        v = args.get(c['nome'])
        if v is not None:
            saida[c['nome']] = str(v)[:200]
    return saida


def calcular(isca_id, params, ctx=None):
    isca = ISCAS.get(isca_id)
    if not isca or not isca.get('calcular'):
        return None
    try:
        return isca['calcular'](params, ctx or {})
    except Exception:
        return None
