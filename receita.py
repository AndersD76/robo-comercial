# -*- coding: utf-8 -*-
"""Painel de receita orgânica (Fase 8 do Prompt 2): funil por semana, MRR,
receita por página de entrada e páginas com visita e sem conversão.

Só agregados, lidos das tabelas do próprio app: busca_consultas (Search
Console), cta_cliques, users (first_touch, aha_em), eventos e pagamentos
(aplicado_em = compra conferida no Mercado Pago). Sem dado pessoal.
"""
from datetime import date, timedelta

from medicao import _existe, _q, tipo_de_pagina

PRECOS = {'starter': 97.0, 'pro': 297.0}


def _contar(cur, tabela, sql, params):
    return (_q(cur, sql, params)[0]['n'] or 0) if _existe(cur, tabela) else 0


def funil(cur, ini, fim):
    """Contagens de cada etapa entre ini (inclusive) e fim (exclusive)."""
    p = (ini, fim)
    tem_gsc = _existe(cur, 'busca_consultas')
    return {
        'cliques_google': (_q(cur, """SELECT COALESCE(SUM(cliques), 0) AS n FROM busca_consultas
                                      WHERE fonte = 'google' AND consulta = '*'
                                        AND data >= %s AND data < %s""", p)[0]['n'] if tem_gsc else 0),
        'cliques_cta': _contar(cur, 'cta_cliques', 'SELECT COUNT(*) AS n FROM cta_cliques '
                               'WHERE created_at >= %s AND created_at < %s', p),
        'cadastros': _q(cur, 'SELECT COUNT(*) AS n FROM users WHERE criado_em >= %s AND criado_em < %s', p)[0]['n'],
        'aha': _q(cur, 'SELECT COUNT(*) AS n FROM users WHERE aha_em >= %s AND aha_em < %s', p)[0]['n'],
        'viu_oferta': _contar(cur, 'eventos', """SELECT COUNT(DISTINCT user_id) AS n FROM eventos
                              WHERE nome = 'paywall_viewed' AND criado_em >= %s AND criado_em < %s""", p),
        'iniciou_pagamento': _contar(cur, 'eventos', """SELECT COUNT(DISTINCT user_id) AS n FROM eventos
                                     WHERE nome = 'checkout_started' AND criado_em >= %s AND criado_em < %s""", p),
        'pagou': _q(cur, """SELECT COUNT(DISTINCT user_id) AS n FROM pagamentos
                            WHERE aplicado_em >= %s AND aplicado_em < %s""", p)[0]['n'],
        'receita': float(_q(cur, """SELECT COALESCE(SUM(valor), 0) AS n FROM pagamentos
                                    WHERE aplicado_em >= %s AND aplicado_em < %s""", p)[0]['n']),
    }


def taxa(a, b):
    return f'{a / b:.0%}' if b else '—'


def dados_receita(cur, hoje=None, semanas=8):
    hoje = hoje or date.today()
    seg = hoje - timedelta(days=hoje.weekday())
    d = {'semanas': []}
    for i in range(semanas - 1, -1, -1):
        ini = seg - timedelta(days=7 * i)
        d['semanas'].append({'ini': ini, **funil(cur, ini, ini + timedelta(days=7))})
    d['ult28'] = funil(cur, hoje - timedelta(days=28), hoje + timedelta(days=1))
    # MRR: planos pagos em vigor com vencimento (contas internas, sem data, ficam fora)
    ativos = _q(cur, """SELECT plano, COUNT(*) AS n FROM users WHERE plano IN ('starter', 'pro')
                        AND plano_expira > NOW() GROUP BY plano""")
    d['mrr'] = sum(PRECOS.get(r['plano'], 0) * r['n'] for r in ativos)
    d['pagantes'] = sum(r['n'] for r in ativos)
    vencidos = _q(cur, """SELECT COUNT(*) AS n FROM users WHERE plano IN ('starter', 'pro')
                          AND plano_expira BETWEEN NOW() - INTERVAL '30 days' AND NOW()""")[0]['n']
    base = d['pagantes'] + vencidos
    d['churn'] = vencidos / base if base else None
    pagos = _q(cur, 'SELECT COUNT(*) AS n, COALESCE(SUM(valor), 0) AS v FROM pagamentos WHERE aplicado_em IS NOT NULL')[0]
    d['ticket'] = float(pagos['v']) / pagos['n'] if pagos['n'] else None
    d['ltv'] = d['ticket'] / d['churn'] if d['ticket'] and d['churn'] else None
    d['por_entrada'] = _q(cur, """SELECT COALESCE(u.first_touch->>'lp', '(sem registro)') AS entrada,
                                         COUNT(*) AS compras, SUM(p.valor) AS receita
                                  FROM pagamentos p JOIN users u ON u.id = p.user_id
                                  WHERE p.aplicado_em IS NOT NULL GROUP BY 1 ORDER BY receita DESC LIMIT 10""")
    for r in d['por_entrada']:
        r['tipo'] = tipo_de_pagina(r['entrada']) if r['entrada'].startswith('/') else '—'
    d['cadastros_por_entrada'] = _q(cur, """SELECT COALESCE(first_touch->>'lp', '(sem registro)') AS entrada,
                                                   COUNT(*) AS n FROM users
                                            WHERE criado_em > NOW() - INTERVAL '28 days'
                                            GROUP BY 1 ORDER BY n DESC LIMIT 10""")
    d['sem_conversao'] = (_q(cur, """
        SELECT g.pagina, SUM(g.cliques) AS cliques
        FROM busca_consultas g
        WHERE g.fonte = 'google' AND g.consulta = '*' AND g.data >= CURRENT_DATE - 28
          AND NOT EXISTS (SELECT 1 FROM users u WHERE u.first_touch->>'lp' = g.pagina)
        GROUP BY g.pagina HAVING SUM(g.cliques) > 0 ORDER BY cliques DESC LIMIT 10""")
        if _existe(cur, 'busca_consultas') else [])
    d['experimentos'] = experimentos(cur)
    d['cta'] = (_q(cur, """SELECT COALESCE(NULLIF(cta, ''), '(sem nome)') AS cta, COUNT(*) AS n FROM cta_cliques
                           WHERE created_at > NOW() - INTERVAL '28 days' GROUP BY 1 ORDER BY n DESC LIMIT 12""")
                if _existe(cur, 'cta_cliques') else [])
    return d


def experimentos(cur):
    """Por experimento e versão: exposições (visitas de pessoa), cliques no
    botão testado (data-cta com sufixo da versão) e cadastros atribuídos."""
    if not _existe(cur, 'eventos'):
        return []
    linhas = {}
    for r in _q(cur, """SELECT props->>'exp' AS exp, props->>'variante' AS v, COUNT(*) AS n
                        FROM eventos WHERE nome = 'experimento_exposto' GROUP BY 1, 2"""):
        linhas[(r['exp'], r['v'])] = {'exp': r['exp'], 'v': r['v'], 'expostos': r['n'],
                                      'cliques': 0, 'cadastros': 0}
    if _existe(cur, 'cta_cliques'):
        for r in _q(cur, """SELECT cta, COUNT(*) AS n FROM cta_cliques
                            WHERE cta LIKE 'pseo-topo-%%' GROUP BY 1"""):
            chave = ('pseo_cta', r['cta'].rsplit('-', 1)[-1])
            if chave in linhas:
                linhas[chave]['cliques'] = r['n']
    for r in _q(cur, """SELECT e.key AS exp, e.value AS v, COUNT(*) AS n FROM eventos,
                               jsonb_each_text(props->'experimentos') e
                        WHERE nome = 'signup_completed' AND jsonb_typeof(props->'experimentos') = 'object'
                          AND e.value IS NOT NULL GROUP BY 1, 2"""):
        if (r['exp'], r['v']) in linhas:
            linhas[(r['exp'], r['v'])]['cadastros'] = r['n']
    for x in linhas.values():
        x['taxa_clique'] = taxa(x['cliques'], x['expostos'])
    return sorted(linhas.values(), key=lambda x: (x['exp'], x['v']))


def secao_relatorio(cur, ini, fim):
    """Linhas de Markdown do funil da semana e ações priorizadas (dinheiro primeiro)."""
    f = funil(cur, ini, fim)
    linhas = ['', '## Funil até a compra', '',
              '| Etapa | Semana | Taxa |', '|---|---|---|',
              f"| Cliques do Google (Search Console) | {f['cliques_google']} | |",
              f"| Cliques em botão de cadastro | {f['cliques_cta']} | |",
              f"| Cadastros | {f['cadastros']} | |",
              f"| Viram valor (1º lead com contato) | {f['aha']} | {taxa(f['aha'], f['cadastros'])} dos cadastros |",
              f"| Viram a oferta paga | {f['viu_oferta']} | |",
              f"| Iniciaram pagamento | {f['iniciou_pagamento']} | {taxa(f['iniciou_pagamento'], f['viu_oferta'])} de quem viu a oferta |",
              f"| Pagaram | {f['pagou']} (R$ {f['receita']:.0f}) | {taxa(f['pagou'], f['iniciou_pagamento'])} de quem iniciou |"]
    acoes = []
    if f['iniciou_pagamento'] > f['pagou']:
        acoes.append(f"{f['iniciou_pagamento'] - f['pagou']} pessoa(s) iniciaram pagamento e não pagaram: o lembrete de PIX sai sozinho; se for cartão recusado, falar com elas.")
    if f['cadastros'] and f['aha'] / f['cadastros'] < 0.5:
        acoes.append(f"Só {taxa(f['aha'], f['cadastros'])} dos cadastros chegaram ao 1º lead: revisar as contas sem lead em /admin (robô sem termos ou travado).")
    if f['cliques_google'] and f['cliques_cta'] / max(f['cliques_google'], 1) < 0.05:
        acoes.append('Menos de 5% dos cliques do Google viram clique em botão: testar outra chamada nas páginas de empresas (ver growth/experimentos.md).')
    return linhas, acoes
