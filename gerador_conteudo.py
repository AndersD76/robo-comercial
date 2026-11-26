# -*- coding: utf-8 -*-
"""Produção de páginas com o Claude, em lote (Message Batches: metade do
preço, sem pressa), sempre a partir do dado da célula e do template do tipo.

Fluxo: conteudo_paginas.status 'pendente' (alvo definido pelas sementes e
pelo mapa de buscas) -> lote -> resultado JSON (saída estruturada) -> HTML
limpo -> portão de qualidade -> 'aprovada' (vai para a onda), 'revisao'
(depende do dono) ou 'rascunho' (reprovada, fica para reforço).

Orçamento: CONTEUDO_PAGINAS_DIA (padrão 80) e CONTEUDO_ORCAMENTO_MES_USD
(padrão 60). Modelo: CONTEUDO_MODELO (padrão claude-opus-5-5).
"""
import datetime as _dt
import hashlib
import json
import os

import conteudo_motor as cm
import crescimento as cfg
import iscas

MODELO = os.environ.get('CONTEUDO_MODELO', 'claude-opus-5-5')
# US$ por milhão de tokens na API de lotes (50% do preço normal)
PRECO_LOTE = {'claude-opus-5-5': (2.0, 10.0), 'claude-sonnet-5-5': (1.0, 5.0), 'claude-haiku-5-5': (0.05, 0.25)}
CUSTO_ESTIMADO_PAGINA = 0.08   # para o teto do mês antes do resultado chegar

PRODUTO = {
    'nome': 'TurboVenda',
    'o_que_faz': 'Software brasileiro de prospecção B2B: encontra empresas do perfil do cliente na base pública de CNPJ '
                 'da Receita Federal e em buscadores, completa telefone, e-mail, CNPJ e o sócio que decide, e faz o '
                 'primeiro contato por e-mail e WhatsApp com mensagem escrita por IA.',
    'planos': [{'nome': 'Starter', 'preco_mes_reais': 97, 'leads_mes': 500},
               {'nome': 'Pro', 'preco_mes_reais': 297, 'leads': 'ilimitados'}],
    'teste_gratis_dias': 14,
    'teste_gratis_leads': 50,
    'teste_gratis_sem_cartao': True,
    'cadastro': '/cadastro',
}

ESQUEMA = {
    'type': 'object',
    'properties': {
        'titulo': {'type': 'string'},
        'descricao': {'type': 'string'},
        'h1': {'type': 'string'},
        'resposta': {'type': 'string'},
        'secoes': {'type': 'array', 'items': {
            'type': 'object', 'properties': {'titulo': {'type': 'string'}, 'html': {'type': 'string'}},
            'required': ['titulo', 'html'], 'additionalProperties': False}},
        'faq': {'type': 'array', 'items': {
            'type': 'object', 'properties': {'pergunta': {'type': 'string'}, 'resposta': {'type': 'string'}},
            'required': ['pergunta', 'resposta'], 'additionalProperties': False}},
        'valor_proprio': {'type': 'string'},
        'fontes_usadas': {'type': 'array', 'items': {'type': 'string'}},
        'termo': {'type': 'string'},
    },
    'required': ['titulo', 'descricao', 'h1', 'resposta', 'secoes', 'faq', 'valor_proprio', 'fontes_usadas', 'termo'],
    'additionalProperties': False,
}

SISTEMA = """Você é redator sênior de vendas B2B e SEO no Brasil, escrevendo para o site do TurboVenda.
Leitor: dono ou gerente comercial de pequena e média empresa que vende para outras empresas.

Regras que não podem ser quebradas:
1. Português do Brasil, acentuação correta, no vocabulário que esse leitor usa ao pesquisar no Google.
2. Nenhum número, porcentagem, valor em reais, prazo, artigo de lei, norma, estudo, caso, cliente ou depoimento que não
   esteja em DADOS, FONTES ou PRODUTO. Sem estatística de mercado. Se precisar de número, use só os entregues.
   Em exemplos, use valores claramente hipotéticos e diga que são exemplo ("imagine uma meta de...").
3. Link interno só para URLs da lista LINKS (use o caminho exato, começando com /). Pelo menos 3 links internos no corpo.
   Nenhum link externo no corpo.
4. HTML do corpo só com: p, h3, ul, ol, li, strong, em, a, table, thead, tbody, tr, th, td, blockquote, pre.
   Não use h1 nem h2 no html das seções (o título de cada seção vira h2 sozinho).
5. Título: até 60 caracteres, começando pela consulta principal (ou o termo). Descrição: entre 120 e 155 caracteres,
   com o benefício e um convite à ação. H1: a consulta principal, natural.
6. Resposta: de 40 a 60 palavras, que responde a consulta já na primeira frase. Sem enrolação.
7. Valor próprio obrigatório, algo que as páginas genéricas do Google não têm: tabela com os DADOS da base da Receita,
   modelo pronto para copiar em <pre>, passo a passo em <ol> ou exemplo prático. Descreva em valor_proprio o que é.
8. FAQ com 3 a 5 perguntas que pessoas realmente fazem sobre a consulta, respostas curtas e diretas.
9. Sem "neste artigo", sem "no mundo competitivo de hoje", sem superlativo vazio. Frases curtas. Exemplos concretos.
10. Ao falar do TurboVenda, só o que está em PRODUTO, uma vez no máximo, onde ajuda o leitor. Comparativos são justos:
    dizem para quem cada ferramenta é melhor, inclusive quando não é o TurboVenda.
11. fontes_usadas: os ids de FONTES que você usou (vazio se nenhum). termo: o termo definido (glossário) ou "".
"""

INSTRUCOES_TIPO = {
    'glossario': 'Página de glossário: defina o termo em linguagem simples, mostre um exemplo prático de prospecção B2B '
                 '(em <pre> ou tabela), quando usar, erros comuns e termos relacionados. 350 a 900 palavras.',
    'modelo': 'Página de modelo pronto: explique em 2 parágrafos quando usar; o modelo completo dentro de <pre>, com '
              'campos entre chaves como {nome} e {empresa}; depois 2 variações (também em <pre>), como personalizar e '
              'erros comuns. 500 a 1.400 palavras.',
    'satelite': 'Página que responde uma pergunta melhor que as genéricas: resposta direta, passo a passo em <ol>, '
                'exemplo prático e, se houver DADOS, uma tabela com eles. 800 a 1.800 palavras.',
    'setor': 'Guia de prospecção para um segmento: quem decide a compra nesse segmento, onde estão as empresas (tabela '
             'com os DADOS por estado e cidades), como abordar, o que dizer na primeira mensagem (modelo em <pre>), '
             'cadência sugerida. 900 a 2.000 palavras.',
    'comparativo': 'Comparativo justo: tabela lado a lado só com os fatos de DADOS (com a data de consulta), para quem '
                   'cada opção é melhor, quando escolher cada uma e perguntas para decidir. 800 a 1.800 palavras.',
    'norma': 'Lei explicada para quem prospecta empresas: o que o artigo diz (cite o texto oficial de DADOS em '
             '<blockquote>, sem alterar), o que ele pede na prática da prospecção B2B, como provar que cumpre '
             '(evidências) e erros comuns. Diga que o conteúdo é informativo e não é aconselhamento jurídico. '
             'Use a fonte do Planalto. 700 a 1.600 palavras.',
    'pilar': 'Guia completo do tema: visão geral, etapas em <ol>, ferramentas e modelos (links da lista LINKS), '
             'erros comuns e próximos passos. 2.000 a 3.500 palavras.',
}


def custom_id(url):
    return 'p' + hashlib.sha1(url.encode()).hexdigest()[:30]


def preco(modelo):
    return PRECO_LOTE.get(modelo, PRECO_LOTE['claude-opus-5-5'])


def pedido(alvo, contexto):
    """params do Messages API para um alvo. contexto: dados, fontes, links, isca."""
    entrada = {
        'TIPO': alvo['tipo'], 'CONSULTA': alvo['consulta'], 'CLUSTER': cfg.CLUSTERS.get(alvo.get('cluster'), {}).get('nome'),
        'URL_DA_PAGINA': alvo['url'], 'DADOS': contexto.get('dados') or {}, 'FONTES': contexto.get('fontes') or [],
        'LINKS': contexto.get('links') or [], 'ISCA_DO_TEMA': contexto.get('isca') or {}, 'PRODUTO': PRODUTO,
        'INSTRUCAO_DO_TIPO': INSTRUCOES_TIPO.get(alvo['tipo'], INSTRUCOES_TIPO['satelite']),
    }
    return {
        'model': MODELO, 'max_tokens': 16000,
        'system': [{'type': 'text', 'text': SISTEMA, 'cache_control': {'type': 'ephemeral'}}],
        'output_config': {'effort': 'medium', 'format': {'type': 'json_schema', 'schema': ESQUEMA}},
        'messages': [{'role': 'user', 'content': json.dumps(entrada, ensure_ascii=False)}],
    }


def montar_pagina(alvo, saida, contexto):
    """JSON do modelo -> campos da página (HTML limpo, fontes resolvidas)."""
    corpo = ''.join(f"<h2>{cm.texto_puro(s['titulo'])}</h2>{s['html']}" for s in saida.get('secoes') or [])
    corpo = cm.html_limpo(corpo)
    # link interno só para o que estava na lista; o resto vira texto
    validos = {l['url'] for l in contexto.get('links') or []} | {'/cadastro', '/precos'}
    import re
    corpo = re.sub(r'<a href="(/[^"]*)">(.*?)</a>',
                   lambda m: m.group(0) if m.group(1).split('?')[0].split('#')[0] in validos else m.group(2), corpo)
    corpo = re.sub(r'<a href="https://[^"]*"(?: rel="noopener")?>(.*?)</a>', r'\1', corpo)
    fontes_por_id = {f['id']: f for f in contexto.get('fontes') or []}
    fontes = [{k: v for k, v in fontes_por_id[i].items() if k != 'id'} for i in saida.get('fontes_usadas') or []
              if i in fontes_por_id]
    if alvo['tipo'] == 'norma':   # a fonte oficial é obrigatória nessa página
        for f in contexto.get('fontes') or []:
            if 'planalto.gov.br' in f.get('url', '') and f not in fontes:
                fontes.append({k: v for k, v in f.items() if k != 'id'})
    faq = [{'pergunta': cm.texto_puro(f['pergunta'])[:200], 'resposta': cm.texto_puro(f['resposta'])[:900]}
           for f in (saida.get('faq') or [])[:6]]
    extra = dict(alvo.get('extra') or {})
    extra.update({'valor_proprio': saida.get('valor_proprio', '')[:300], 'dados_usados': bool(contexto.get('dados')),
                  'termo': saida.get('termo') or extra.get('termo') or ''})
    return {'titulo': cm.texto_puro(saida.get('titulo'))[:70], 'descricao': cm.texto_puro(saida.get('descricao'))[:170],
            'h1': cm.texto_puro(saida.get('h1'))[:140], 'resposta': cm.texto_puro(saida.get('resposta'))[:700],
            'corpo': corpo, 'faq': faq, 'fontes': fontes, 'extra': extra}


def gasto_do_mes(cur):
    cur.execute("""SELECT COALESCE(SUM(CASE WHEN processado_em IS NULL THEN pedidos * %s ELSE custo_usd END), 0) AS usd
                   FROM conteudo_lotes WHERE criado_em >= date_trunc('month', now())""", (CUSTO_ESTIMADO_PAGINA,))
    return float(cur.fetchone()['usd'])


def gerados_hoje(cur):
    cur.execute("SELECT COALESCE(SUM(pedidos), 0) AS n FROM conteudo_lotes WHERE criado_em >= date_trunc('day', now())")
    return int(cur.fetchone()['n'])


def quanto_gerar(cur):
    por_dia = int(os.environ.get('CONTEUDO_PAGINAS_DIA', '80'))
    teto = float(os.environ.get('CONTEUDO_ORCAMENTO_MES_USD', '60'))
    sobra_dia = max(0, por_dia - gerados_hoje(cur))
    sobra_mes = max(0, int((teto - gasto_do_mes(cur)) / CUSTO_ESTIMADO_PAGINA))
    return min(sobra_dia, sobra_mes)


def enviar_lote(conn, client, contexto_de, limite=None):
    """Monta e envia um lote com os próximos alvos pendentes. Devolve (id, n)."""
    cur = conn.cursor()
    n = quanto_gerar(cur) if limite is None else limite
    if n <= 0:
        return None, 0
    cur.execute("""SELECT url, tipo, cluster, consulta, isca, extra FROM conteudo_paginas WHERE status = 'pendente'
                   ORDER BY COALESCE((extra->>'prioridade')::int, 50) DESC, criado_em LIMIT %s""", (n,))
    alvos = [dict(r) for r in cur.fetchall()]
    if not alvos:
        return None, 0
    pedidos, itens = [], []
    for a in alvos:
        if isinstance(a.get('extra'), str):
            a['extra'] = json.loads(a['extra'])
        ctx = contexto_de(cur, a)
        pedidos.append({'custom_id': custom_id(a['url']), 'params': pedido(a, ctx)})
        itens.append(a['url'])
    lote = client.messages.batches.create(requests=pedidos)
    cur.execute("INSERT INTO conteudo_lotes (id, status, pedidos) VALUES (%s, %s, %s)",
                (lote.id, lote.processing_status, len(pedidos)))
    cur.execute("""UPDATE conteudo_paginas SET status = 'gerando',
                   extra = COALESCE(extra, '{}'::jsonb) || jsonb_build_object('lote', %s::text)
                   WHERE url = ANY(%s)""", (lote.id, itens))
    conn.commit()
    return lote.id, len(pedidos)


def processar_lotes(conn, client, contexto_de, avaliar, agora=None):
    """Lotes terminados: grava as páginas, passa no portão e fecha o custo."""
    cur = conn.cursor()
    cur.execute("SELECT id FROM conteudo_lotes WHERE processado_em IS NULL ORDER BY criado_em")
    feitos = []
    for (lote_id,) in [(r['id'],) for r in cur.fetchall()]:
        lote = client.messages.batches.retrieve(lote_id)
        if lote.processing_status != 'ended':
            cur.execute('UPDATE conteudo_lotes SET status = %s WHERE id = %s', (lote.processing_status, lote_id))
            conn.commit()
            continue
        cur.execute("SELECT url, tipo, cluster, consulta, isca, extra FROM conteudo_paginas WHERE extra->>'lote' = %s",
                    (lote_id,))
        alvos = {custom_id(r['url']): dict(r) for r in cur.fetchall()}
        tin = tout = ok = falhas = 0
        modelo = MODELO
        for res in client.messages.batches.results(lote_id):
            alvo = alvos.get(res.custom_id)
            if not alvo:
                continue
            if isinstance(alvo.get('extra'), str):
                alvo['extra'] = json.loads(alvo['extra'])
            if res.result.type != 'succeeded':
                falhas += 1
                _devolver(cur, alvo, f'lote: {res.result.type}')
                continue
            msg = res.result.message
            modelo = getattr(msg, 'model', modelo) or modelo
            tin += msg.usage.input_tokens + (getattr(msg.usage, 'cache_read_input_tokens', 0) or 0)
            tout += msg.usage.output_tokens
            if msg.stop_reason != 'end_turn':
                falhas += 1
                _devolver(cur, alvo, f'stop_reason {msg.stop_reason}')
                continue
            texto = ''.join(b.text for b in msg.content if getattr(b, 'type', '') == 'text')
            try:
                saida = json.loads(texto)
            except ValueError:
                falhas += 1
                _devolver(cur, alvo, 'JSON inválido')
                continue
            ctx = contexto_de(cur, alvo)
            campos = montar_pagina(alvo, saida, ctx)
            pg = dict(alvo, **campos)
            r = avaliar(cur, pg, ctx)
            status = 'revisao' if r['revisao'] else ('aprovada' if r['aprovado'] else 'rascunho')
            pin, pout = preco(modelo)
            custo = (msg.usage.input_tokens * pin + msg.usage.output_tokens * pout) / 1e6
            cm.salvar(cur, alvo['url'], dict(campos, status=status, origem='llm', modelo=modelo,
                                             tokens_entrada=msg.usage.input_tokens, tokens_saida=msg.usage.output_tokens,
                                             custo_usd=round(custo, 4),
                                             revisar_em=(_dt.date.today() + _dt.timedelta(days=180))))
            cm.registrar_avaliacao(cur, alvo['url'], r)
            ok += 1
        pin, pout = preco(modelo)
        cur.execute("""UPDATE conteudo_lotes SET status = 'ended', concluidos = %s, falhas = %s, tokens_entrada = %s,
                       tokens_saida = %s, custo_usd = %s, processado_em = now() WHERE id = %s""",
                    (ok, falhas, tin, tout, round((tin * pin + tout * pout) / 1e6, 4), lote_id))
        conn.commit()
        feitos.append((lote_id, ok, falhas))
    return feitos


def _devolver(cur, alvo, motivo):
    """Falhou: volta para a fila (até 2 tentativas), depois fica como rascunho."""
    extra = dict(alvo.get('extra') or {})
    extra['tentativas'] = int(extra.get('tentativas') or 0) + 1
    extra['ultimo_erro'] = motivo
    status = 'pendente' if extra['tentativas'] < 3 else 'rascunho'
    cur.execute('UPDATE conteudo_paginas SET status = %s, extra = %s, atualizado_em = now() WHERE url = %s',
                (status, json.dumps(extra, ensure_ascii=False), alvo['url']))


def iscas_validas():
    return set(iscas.ISCAS)
