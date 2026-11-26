# -*- coding: utf-8 -*-
"""Páginas de dados por CNAE: descrição oficial do IBGE (CONCLA) + contagem
de empresas ativas com contato, da base da Receita (cnae_estatisticas).

Matriz programática: /cnae/<código> (1.332 subclasses) e /cnae/<código>/<uf>.
Abaixo do limiar de dado a página fica noindex e fora do sitemap.
"""
import json
import re
import unicodedata

IBGE_URL = 'https://servicodados.ibge.gov.br/api/v2/cnae/subclasses'
IBGE_FONTE = {'nome': 'IBGE — Comissão Nacional de Classificação (CONCLA), CNAE 2.3, API de serviços de dados',
              'url': 'https://concla.ibge.gov.br/'}
RECEITA_FONTE = {'nome': 'Receita Federal — Dados Abertos do CNPJ',
                 'url': 'https://www.gov.br/receitafederal/pt-br/assuntos/orientacao-tributaria/cadastros/consultas/dados-publicos-cnpj'}
LIMIAR_CNAE = 30        # empresas ativas com contato para indexar /cnae/<código>
LIMIAR_CNAE_UF = 300    # para indexar /cnae/<código>/<uf>
PORTES = {'00': 'Não informado', '01': 'Microempresa', '03': 'Pequena (EPP)', '05': 'Demais (média e grande)'}

DDL_BUSCA = "ALTER TABLE cnae_ibge ADD COLUMN IF NOT EXISTS busca TEXT"


MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']


def mes_da_base(valor):
    """'2026-10-13' -> 'out/2026' (data da base da Receita)."""
    m = re.match(r'(\d{4})-(\d{2})', str(valor or ''))
    return f'{MESES[int(m.group(2)) - 1]}/{m.group(1)}' if m and 1 <= int(m.group(2)) <= 12 else (valor or '')


def _cidades_oficiais(est):
    """A Receita grava o município sem acento; mostra o nome oficial do IBGE."""
    try:
        from pseo_data import nome_municipio
    except Exception:
        return est
    for c in est.get('cidades') or []:
        c['municipio'] = nome_municipio(c['municipio'], c.get('uf'))
    for uf, u in (est.get('ufs') or {}).items():
        for c in u.get('cidades') or []:
            c['municipio'] = nome_municipio(c['municipio'], uf)
    return est


def sem_acento(t):
    return ''.join(c for c in unicodedata.normalize('NFD', t or '') if unicodedata.category(c) != 'Mn')


def formatado(codigo):
    c = re.sub(r'\D', '', str(codigo))
    return f'{c[:4]}-{c[4]}/{c[5:]}' if len(c) == 7 else c


def frase(descricao):
    """'TRANSPORTE RODOVIÁRIO DE CARGA' -> 'Transporte rodoviário de carga'."""
    d = (descricao or '').strip().lower()
    return d[:1].upper() + d[1:]


def _texto_busca(item):
    partes = [item['id'], item['descricao']] + list(item.get('atividades') or [])
    return sem_acento(' '.join(partes)).lower()


def importar_ibge(cur, lista):
    """Grava/atualiza as subclasses vindas da API do IBGE. Devolve quantas."""
    cur.execute(DDL_BUSCA)
    n = 0
    for it in lista or []:
        codigo = re.sub(r'\D', '', str(it.get('id', '')))
        if len(codigo) != 7 or not it.get('descricao'):
            continue
        classe = it.get('classe') or {}
        grupo = classe.get('grupo') or {}
        divisao = grupo.get('divisao') or {}
        secao = divisao.get('secao') or {}
        hier = {'classe': {'id': classe.get('id'), 'descricao': classe.get('descricao')},
                'grupo': {'id': grupo.get('id'), 'descricao': grupo.get('descricao')},
                'divisao': {'id': divisao.get('id'), 'descricao': divisao.get('descricao')},
                'secao': {'id': secao.get('id'), 'descricao': secao.get('descricao')}}
        obs = [re.sub(r'\s*\r?\n\s*', '\n', o).strip() for o in (classe.get('observacoes') or [])]
        cur.execute("""INSERT INTO cnae_ibge (codigo, descricao, hierarquia, observacoes, atividades, busca, atualizado_em)
                       VALUES (%s, %s, %s, %s, %s, %s, now())
                       ON CONFLICT (codigo) DO UPDATE SET descricao = EXCLUDED.descricao, hierarquia = EXCLUDED.hierarquia,
                       observacoes = EXCLUDED.observacoes, atividades = EXCLUDED.atividades, busca = EXCLUDED.busca,
                       atualizado_em = now()""",
                    (codigo, it['descricao'].strip(), json.dumps(hier, ensure_ascii=False),
                     json.dumps(obs, ensure_ascii=False), json.dumps(it.get('atividades') or [], ensure_ascii=False),
                     _texto_busca({'id': codigo, 'descricao': it['descricao'], 'atividades': it.get('atividades')})))
        n += 1
    return n


def buscar(cur, q, limite=50):
    """Por código (com ou sem pontuação) ou por palavras da atividade."""
    q = (q or '').strip()
    digitos = re.sub(r'\D', '', q)
    if len(digitos) >= 2 and len(digitos) == len(re.sub(r'[\s./-]', '', q)):
        cur.execute("""SELECT i.codigo, i.descricao, (e.dados->>'total')::int AS empresas FROM cnae_ibge i
                       LEFT JOIN cnae_estatisticas e ON e.codigo = i.codigo
                       WHERE i.codigo LIKE %s ORDER BY i.codigo LIMIT %s""", (digitos + '%', limite))
    else:
        palavras = [p for p in re.findall(r'[a-z0-9]{3,}', sem_acento(q).lower())][:5]
        if not palavras:
            return []
        cond = ' AND '.join(['i.busca LIKE %s'] * len(palavras))
        cur.execute(f"""SELECT i.codigo, i.descricao, (e.dados->>'total')::int AS empresas FROM cnae_ibge i
                        LEFT JOIN cnae_estatisticas e ON e.codigo = i.codigo
                        WHERE {cond} ORDER BY COALESCE((e.dados->>'total')::int, 0) DESC LIMIT %s""",
                    [f'%{p}%' for p in palavras] + [limite])
    return [{'codigo': r['codigo'], 'formatado': formatado(r['codigo']), 'descricao': r['descricao'],
             'empresas': r['empresas']} for r in cur.fetchall()]


def dados(cur, codigo, uf=None):
    """Tudo que a página precisa, ou None se o código não existe."""
    cur.execute("""SELECT i.codigo, i.descricao, i.hierarquia, i.observacoes, i.atividades, e.dados, e.base_mes
                   FROM cnae_ibge i LEFT JOIN cnae_estatisticas e ON e.codigo = i.codigo WHERE i.codigo = %s""",
                (codigo,))
    r = cur.fetchone()
    if not r:
        return None
    est = r['dados'] or {}
    if isinstance(est, str):
        est = json.loads(est)
    est = _cidades_oficiais(est)
    d = {'codigo': r['codigo'], 'formatado': formatado(r['codigo']), 'descricao': r['descricao'],
         'nome': frase(r['descricao']), 'hierarquia': r['hierarquia'] or {}, 'observacoes': r['observacoes'] or [],
         'atividades': r['atividades'] or [], 'est': est, 'base_mes': mes_da_base(r['base_mes']),
         'total': est.get('total') or 0}
    compreende, nao = [], []
    for o in d['observacoes']:
        linhas = [x.strip(' -;') for x in o.split('\n') if x.strip(' -;')]
        if not linhas:
            continue
        cab = linhas[0].lower()
        itens = linhas[1:] if len(linhas) > 1 else []
        primeiro = re.sub(r'(?i)^esta (sub)?classe (n[ãa]o )?compreende\s*[-:]?\s*', '', linhas[0]).strip(' -;')
        if primeiro:
            itens = [primeiro] + itens
        (nao if 'não compreende' in cab or 'nao compreende' in cab else compreende).extend(itens)
    d['compreende'], d['nao_compreende'] = compreende, nao
    if uf:
        u = (est.get('ufs') or {}).get(uf)
        if not u:
            return d | {'uf': uf, 'uf_dados': None, 'total_uf': 0}
        n_uf = next((x['n'] for x in est.get('por_uf', []) if x['uf'] == uf), 0)
        d |= {'uf': uf, 'uf_dados': u, 'total_uf': n_uf}
    return d


def indexavel(d, uf=None):
    return (d.get('total_uf') or 0) >= LIMIAR_CNAE_UF if uf else (d.get('total') or 0) >= LIMIAR_CNAE


def relacionados(cur, d, limite=8):
    """Outros códigos da mesma classe e do mesmo grupo (navegação da hierarquia)."""
    grupo = ((d.get('hierarquia') or {}).get('grupo') or {}).get('id') or ''
    if not grupo:
        return []
    cur.execute("""SELECT i.codigo, i.descricao, (e.dados->>'total')::int AS empresas FROM cnae_ibge i
                   LEFT JOIN cnae_estatisticas e ON e.codigo = i.codigo
                   WHERE i.codigo LIKE %s AND i.codigo <> %s
                   ORDER BY COALESCE((e.dados->>'total')::int, 0) DESC LIMIT %s""",
                (re.sub(r'\D', '', grupo) + '%', d['codigo'], limite))
    return [{'codigo': r['codigo'], 'formatado': formatado(r['codigo']), 'nome': frase(r['descricao']),
             'empresas': r['empresas']} for r in cur.fetchall()]


def celulas(cur):
    """(url, total, atualizado_em) de todas as páginas acima do limiar."""
    cur.execute("""SELECT e.codigo, (e.dados->>'total')::int AS total, e.dados->'por_uf' AS por_uf, e.atualizado_em
                   FROM cnae_estatisticas e JOIN cnae_ibge i ON i.codigo = e.codigo""")
    saida = []
    for r in cur.fetchall():
        if (r['total'] or 0) >= LIMIAR_CNAE:
            saida.append((f"/cnae/{r['codigo']}", r['total'], r['atualizado_em']))
        por_uf = r['por_uf'] or []
        if isinstance(por_uf, str):
            por_uf = json.loads(por_uf)
        for x in por_uf:
            if x['n'] >= LIMIAR_CNAE_UF:
                saida.append((f"/cnae/{r['codigo']}/{x['uf'].lower()}", x['n'], r['atualizado_em']))
    return saida


def secoes(cur):
    """Hub /cnae: seções da CNAE com as subclasses de mais empresas."""
    cur.execute("""SELECT i.codigo, i.descricao, i.hierarquia->'secao'->>'id' AS secao,
                          i.hierarquia->'secao'->>'descricao' AS secao_nome, (e.dados->>'total')::int AS empresas
                   FROM cnae_ibge i LEFT JOIN cnae_estatisticas e ON e.codigo = i.codigo ORDER BY i.codigo""")
    por = {}
    for r in cur.fetchall():
        s = por.setdefault(r['secao'] or '?', {'id': r['secao'], 'nome': frase(r['secao_nome']), 'itens': [], 'total': 0})
        s['itens'].append({'codigo': r['codigo'], 'formatado': formatado(r['codigo']), 'nome': frase(r['descricao']),
                           'empresas': r['empresas']})
        s['total'] += r['empresas'] or 0
    for s in por.values():
        s['itens'].sort(key=lambda x: -(x['empresas'] or 0))
    return [por[k] for k in sorted(por)]
