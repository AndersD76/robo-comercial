# -*- coding: utf-8 -*-
"""Motor de conteúdo: páginas no banco (conteudo_paginas), HTML limpo,
portão de qualidade, links internos sem página órfã e publicação em ondas.

Sem Flask aqui: as rotas ficam no app.py e passam o cursor.
"""
import datetime as _dt
import json
import math
import re
import unicodedata
from collections import Counter
from html import escape
from html.parser import HTMLParser

import crescimento as cfg

# ---------------------------------------------------------------------------
# Texto
# ---------------------------------------------------------------------------


def sem_acento(t):
    return ''.join(c for c in unicodedata.normalize('NFD', t or '') if unicodedata.category(c) != 'Mn')


def slugify(t, limite=80):
    s = re.sub(r'[^a-z0-9]+', '-', sem_acento(str(t or '')).lower()).strip('-')
    return s[:limite].rstrip('-')


def texto_puro(html):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html or '')).strip()


_VAZIAS = set('''a o as os um uma uns umas de da do das dos em no na nos nas por para pelo pela
pelos pelas com sem sobre entre e ou que se seu sua seus suas ao aos é são ser foi como mais menos
muito muita já não sim isso esse essa este esta isto ele ela eles elas você vocês nós mas também
quando onde qual quais cada até porque pois então só ainda há tem têm ter vai vão pode podem deve
devem the and turbovenda empresa empresas'''.split())


def tokens(texto):
    t = sem_acento(texto_puro(texto)).lower()
    return [w for w in re.findall(r'[a-z0-9]{3,}', t) if w not in _VAZIAS]


def termos_da_consulta(consulta):
    return [w for w in tokens(consulta) if len(w) >= 3]


# ---------------------------------------------------------------------------
# HTML limpo: só tags de texto; links internos ou https; nada de script
# ---------------------------------------------------------------------------
_TAGS = {'p', 'h2', 'h3', 'h4', 'ul', 'ol', 'li', 'strong', 'em', 'b', 'i', 'a', 'table', 'thead',
         'tbody', 'tr', 'th', 'td', 'blockquote', 'pre', 'code', 'br', 'hr', 'caption', 'small'}
_SEM_FECHAR = {'br', 'hr'}
_DESCARTAR = {'script', 'style', 'iframe', 'object', 'embed', 'form', 'svg', 'math', 'noscript',
              'template', 'textarea', 'select', 'button', 'input'}


class _Limpador(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.saida, self.pilha, self.pular = [], [], 0

    def handle_starttag(self, tag, attrs):
        if tag in _DESCARTAR:
            self.pular += 1
            return
        if self.pular:
            return
        if tag == 'h1':
            tag = 'h2'
        if tag not in _TAGS:
            return
        extra = ''
        if tag == 'a':
            href = (dict(attrs).get('href') or '').strip()
            if not re.match(r'^(/(?![/\\])[^\s"<>]*|https://[^\s"<>]+)$', href):
                return
            extra = f' href="{escape(href, quote=True)}"'
            if href.startswith('https://') and 'turbovenda.com.br' not in href:
                extra += ' rel="noopener"'
        if tag in _SEM_FECHAR:
            self.saida.append(f'<{tag}>')
            return
        self.saida.append(f'<{tag}{extra}>')
        self.pilha.append(tag)

    def handle_startendtag(self, tag, attrs):
        if tag in _SEM_FECHAR and not self.pular:
            self.saida.append(f'<{tag}>')

    def handle_endtag(self, tag):
        if tag in _DESCARTAR:
            self.pular = max(0, self.pular - 1)
            return
        if self.pular:
            return
        if tag == 'h1':
            tag = 'h2'
        if tag in self.pilha:
            while self.pilha:
                t = self.pilha.pop()
                self.saida.append(f'</{t}>')
                if t == tag:
                    break

    def handle_data(self, dado):
        if not self.pular:
            self.saida.append(escape(dado, quote=False))

    def resultado(self):
        while self.pilha:
            self.saida.append(f'</{self.pilha.pop()}>')
        return ''.join(self.saida)


def html_limpo(html):
    p = _Limpador()
    p.feed(html or '')
    p.close()
    return p.resultado()


def com_ancoras(html):
    """Põe id nos <h2> e devolve (html, sumário [(id, título)])."""
    sumario, usados = [], set()

    def troca(m):
        titulo = texto_puro(m.group(1))
        base = slugify(titulo, 50) or 'secao'
        ident, i = base, 2
        while ident in usados:
            ident, i = f'{base}-{i}', i + 1
        usados.add(ident)
        sumario.append((ident, titulo))
        return f'<h2 id="{ident}">{m.group(1)}</h2>'

    return re.sub(r'<h2>(.*?)</h2>', troca, html or '', flags=re.S), sumario


def dividir_no_meio(html):
    """Divide o corpo num <h2> perto da metade, para a isca do meio."""
    posicoes = [m.start() for m in re.finditer(r'<h2[ >]', html or '')]
    if len(posicoes) < 3:
        return html, ''
    alvo = len(html) / 2
    corte = min(posicoes[1:], key=lambda p: abs(p - alvo))
    return html[:corte], html[corte:]


# ---------------------------------------------------------------------------
# Números: o que não veio dos dados entregues vai para revisão
# ---------------------------------------------------------------------------
_RE_NUM = re.compile(r'(R\$\s*)?(\d{1,3}(?:\.\d{3})+|\d+(?:,\d+)?)(\s*%|\s*(?:mil|mi|milh[õo]es|bilh[õo]es))?',
                     re.I)


def _normal(num):
    return num.replace('.', '').replace(',', '.').lstrip('0') or '0'


def numeros_de(obj):
    """Todos os números que aparecem em textos/dados (normalizados)."""
    if isinstance(obj, (dict, list)):
        texto = json.dumps(obj, ensure_ascii=False)
    else:
        texto = str(obj or '')
    saida = set()
    for m in _RE_NUM.finditer(texto):
        n = _normal(m.group(2))
        saida.add(n)
        if '.' in n:
            saida.add(n.split('.')[0])
    # números crus do JSON (ex.: 123456) também valem formatados (123.456)
    for m in re.finditer(r'\d+(?:\.\d+)?', texto):
        saida.add(m.group(0).lstrip('0') or '0')
    return saida


def numeros_suspeitos(texto, permitidos):
    """Números do texto que pedem fonte e não estão nos dados: dinheiro,
    porcentagem, milhões, ou qualquer número ≥ 100 (fora anos 1990–2030)."""
    suspeitos = []
    for m in _RE_NUM.finditer(texto or ''):
        bruto, n = m.group(0).strip(), _normal(m.group(2))
        dinheiro, sufixo = bool(m.group(1)), (m.group(3) or '').strip()
        try:
            valor = float(n)
        except ValueError:
            continue
        ano = 1990 <= valor <= 2030 and n.isdigit() and not dinheiro and not sufixo
        if ano:
            continue
        pede_fonte = dinheiro or sufixo or valor >= 100
        if pede_fonte and n not in permitidos and n.split('.')[0] not in permitidos:
            suspeitos.append(bruto)
    return suspeitos


_RE_NORMA = re.compile(r'\b(lei(?:\s+complementar)?|decreto|resolu[çc][ãa]o|portaria|instru[çc][ãa]o normativa|'
                       r'medida provis[óo]ria|art\.|artigo)\s*(?:n[º°o.]*\s*)?\d', re.I)
DOMINIOS_OFICIAIS = ('planalto.gov.br', 'gov.br', 'ibge.gov.br', 'receita.fazenda.gov.br', 'in.gov.br',
                     'anpd.gov.br', 'senado.leg.br', 'camara.leg.br', 'stf.jus.br', 'stj.jus.br',
                     'anatel.gov.br', 'procon', 'sebrae.com.br', 'bcb.gov.br')


_RE_EXEMPLO = re.compile(r'<(p|li|tr|blockquote)>(?:(?!</\1>).)*?(exemplo hipot[ée]tico|\bimagine\b|\bsuponha\b)'
                         r'(?:(?!</\1>).)*?</\1>', re.S | re.I)


def sem_exemplos(html):
    """Tira o que se declara hipotético (modelo em <pre>, parágrafo que começa
    com "Exemplo hipotético", "imagine", "suponha"): número de exemplo não é
    fato. Número solto fora disso continua pedindo fonte."""
    return _RE_EXEMPLO.sub(' ', re.sub(r'<pre>.*?</pre>', ' ', html or '', flags=re.S))


def fonte_oficial(fontes):
    return any(any(d in (f.get('url') or '') for d in DOMINIOS_OFICIAIS) for f in (fontes or []))


# ---------------------------------------------------------------------------
# Similaridade (TF-IDF) e grafo de links internos
# ---------------------------------------------------------------------------


class Indice:
    """TF-IDF das páginas publicadas/aprovadas, para similaridade e links."""

    def __init__(self, paginas):
        # paginas: [{'url','tipo','cluster','titulo','texto'}]
        self.paginas = {p['url']: p for p in paginas}
        docs = {u: Counter(tokens((p.get('titulo') or '') + ' ' + (p.get('texto') or '')))
                for u, p in self.paginas.items()}
        df = Counter()
        for c in docs.values():
            df.update(set(c))
        n = max(1, len(docs))
        self.idf = {t: math.log((n + 1) / (f + 1)) + 1 for t, f in df.items()}
        self.vet = {u: self._vetor(c) for u, c in docs.items()}

    def _vetor(self, cont):
        v = {t: (1 + math.log(f)) * self.idf.get(t, 1.0) for t, f in cont.items()}
        norma = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {t: x / norma for t, x in v.items()}

    def vetor_de(self, titulo, texto):
        return self._vetor(Counter(tokens((titulo or '') + ' ' + (texto or ''))))

    @staticmethod
    def cosseno(a, b):
        if len(a) > len(b):
            a, b = b, a
        return sum(x * b.get(t, 0.0) for t, x in a.items())

    def mais_parecida(self, titulo, texto, ignorar=None):
        v = self.vetor_de(titulo, texto)
        melhor = (None, 0.0)
        for u, w in self.vet.items():
            if u == ignorar:
                continue
            s = self.cosseno(v, w)
            if s > melhor[1]:
                melhor = (u, s)
        return melhor

    def grafo(self, por_pagina=5, minimo_entrada=3):
        """url -> [urls relacionadas] dentro do cluster, por similaridade, com
        garantia de entrada: toda página aparece em pelo menos `minimo_entrada`
        listas quando o cluster tem páginas suficientes (zero órfã)."""
        por_cluster = {}
        for u, p in self.paginas.items():
            por_cluster.setdefault(p.get('cluster') or '-', []).append(u)
        saida = {}
        for urls in por_cluster.values():
            urls.sort()
            if len(urls) == 1:
                saida[urls[0]] = []
                continue
            k = min(por_pagina, len(urls) - 1)
            entrada = Counter()
            for u in urls:
                viz = sorted((x for x in urls if x != u),
                             key=lambda x: (-self.cosseno(self.vet[u], self.vet[x]), x))[:k]
                saida[u] = viz
                entrada.update(viz)
            precisa = min(minimo_entrada, len(urls) - 1)
            for alvo in urls:
                while entrada[alvo] < precisa:
                    # a página mais parecida que ainda não linka o alvo passa a linkar
                    candidatos = sorted((x for x in urls if x != alvo and alvo not in saida[x]),
                                        key=lambda x: -self.cosseno(self.vet[x], self.vet[alvo]))
                    if not candidatos:
                        break
                    saida[candidatos[0]].append(alvo)
                    entrada[alvo] += 1
        return saida


def entradas(grafo):
    c = Counter()
    for viz in grafo.values():
        c.update(viz)
    return c


# ---------------------------------------------------------------------------
# Portão de qualidade
# ---------------------------------------------------------------------------
LIMIAR_SIMILARIDADE = 0.80
REVISAO_SEMPRE = {'norma'}   # lei explicada: sempre passa pelo dono antes de publicar


def titulo_ok(titulo, consulta):
    if not titulo or len(titulo) > 60:
        return False
    termos = termos_da_consulta(consulta)[:3]
    inicio = sem_acento(titulo[:int(len(titulo) * .7) + 8]).lower()
    return not termos or sum(t in inicio for t in termos) >= max(1, len(termos) - 1)


def avaliar(p, indice=None, links_entrada=0, numeros_permitidos=frozenset(), iscas_validas=frozenset(),
            links_saida_auto=0):
    """Resultado do portão: {'aprovado', 'revisao', 'nota', 'checks', 'motivo'}.

    p: dict com tipo, consulta, titulo, descricao, h1, resposta, corpo, faq,
    fontes, extra, isca, url. revisao=True quando o que falta depende do dono
    (número ou norma sem fonte, lei explicada)."""
    tipo = p.get('tipo')
    corpo = p.get('corpo') or ''
    texto = texto_puro(corpo)
    resposta = p.get('resposta') or ''
    faq_txt = ' '.join(f"{f.get('pergunta', '')} {f.get('resposta', '')}" for f in (p.get('faq') or []))
    extra = p.get('extra') or {}
    checks = {}
    termos = termos_da_consulta(p.get('consulta'))
    n_resp = len(resposta.split())
    cobre = sum(t in sem_acento(resposta).lower() for t in termos) / max(1, len(termos))
    checks['resposta_direta'] = 30 <= n_resp <= 75 and cobre >= .5
    checks['valor_proprio'] = bool(extra.get('valor_proprio')) and bool(
        re.search(r'<(table|pre|ol)\b', corpo) or extra.get('dados_usados'))
    suspeitos = numeros_suspeitos(' '.join([texto_puro(sem_exemplos(corpo)), resposta, faq_txt]), numeros_permitidos)
    checks['numeros_com_fonte'] = not suspeitos
    tem_norma = bool(_RE_NORMA.search(texto + ' ' + faq_txt))
    checks['norma_com_fonte_oficial'] = not tem_norma or fonte_oficial(p.get('fontes'))
    parecida, sim = (None, 0.0)
    if indice is not None:
        parecida, sim = indice.mais_parecida(p.get('titulo'), texto, ignorar=p.get('url'))
    checks['similaridade'] = sim < LIMIAR_SIMILARIDADE
    lo, hi = cfg.TIPOS_PAGINA.get(tipo, {}).get('palavras', (300, 5000))
    n_pal = len(texto.split())
    checks['tamanho'] = lo <= n_pal <= hi
    checks['titulo'] = titulo_ok(p.get('titulo'), p.get('consulta'))
    checks['descricao'] = 70 <= len(p.get('descricao') or '') <= 155
    checks['h1'] = bool(p.get('h1')) and len(p.get('h1')) <= 110
    internos = re.findall(r'<a href="/', corpo)
    checks['links_saida'] = len(internos) + links_saida_auto >= 3
    checks['links_entrada'] = links_entrada >= 3
    checks['isca'] = (p.get('isca') in iscas_validas) if iscas_validas else bool(p.get('isca'))
    checks['faq'] = len(p.get('faq') or []) >= (0 if tipo in ('glossario', 'programatica') else 2)
    falhas = [k for k, ok in checks.items() if not ok]
    revisao = tipo in REVISAO_SEMPRE or not checks['numeros_com_fonte'] or not checks['norma_com_fonte_oficial']
    motivo = ', '.join(falhas)
    if suspeitos:
        motivo += f" | números sem fonte: {', '.join(suspeitos[:6])}"
    if parecida and not checks['similaridade']:
        motivo += f' | parecida com {parecida} ({sim:.2f})'
    return {'aprovado': not falhas, 'revisao': revisao, 'nota': round(100 * (len(checks) - len(falhas)) / len(checks)),
            'checks': checks, 'motivo': motivo.strip(' |,'), 'similar': parecida, 'similaridade': round(sim, 3),
            'palavras': n_pal}


def registrar_avaliacao(cur, url, r):
    cur.execute('INSERT INTO conteudo_qualidade (url, aprovado, nota, checks, motivo) VALUES (%s, %s, %s, %s, %s)',
                (url, r['aprovado'], r['nota'], json.dumps(r['checks']), r['motivo'][:1000]))


# ---------------------------------------------------------------------------
# Banco
# ---------------------------------------------------------------------------
CAMPOS = ('tipo', 'cluster', 'consulta', 'titulo', 'descricao', 'h1', 'resposta', 'corpo', 'faq', 'fontes',
          'extra', 'isca', 'matriz', 'celula', 'status', 'indexavel', 'revisar_em', 'origem', 'modelo',
          'tokens_entrada', 'tokens_saida', 'custo_usd')
_JSON = {'faq', 'fontes', 'extra'}


def salvar(cur, url, dados):
    """Atualiza a página se ela existe; senão insere (aí `tipo` é obrigatório).
    Não mexe em publicado_em/onda. (Um INSERT ... ON CONFLICT sem `tipo`
    falharia: o Postgres confere o NOT NULL antes de resolver o conflito.)"""
    campos = [c for c in CAMPOS if c in dados]
    valores = [json.dumps(dados[c], ensure_ascii=False) if c in _JSON else dados[c] for c in campos]
    sets = ', '.join(f'{c} = %s' for c in campos)
    cur.execute(f'UPDATE conteudo_paginas SET {sets}, atualizado_em = now() WHERE url = %s', valores + [url])
    if cur.rowcount:
        return
    cur.execute(f"""INSERT INTO conteudo_paginas (url, {', '.join(campos)}) VALUES (%s, {', '.join(['%s'] * len(campos))})""",
                [url] + valores)


def pagina(cur, url, so_publicada=True):
    cur.execute('SELECT * FROM conteudo_paginas WHERE url = %s' + (" AND status = 'publicada'" if so_publicada else ''),
                (url,))
    return cur.fetchone()


def publicadas(cur, tipo=None, cluster=None, limite=None):
    sql = "SELECT url, tipo, cluster, titulo, descricao, consulta, atualizado_em, publicado_em, indexavel, celula, extra " \
          "FROM conteudo_paginas WHERE status = 'publicada'"
    params = []
    if tipo:
        sql += ' AND tipo = %s'
        params.append(tipo)
    if cluster:
        sql += ' AND cluster = %s'
        params.append(cluster)
    sql += ' ORDER BY titulo'
    if limite:
        sql += f' LIMIT {int(limite)}'
    cur.execute(sql, params)
    return cur.fetchall()


def tipos_pausados(cur):
    cur.execute('SELECT tipo FROM conteudo_pausas')
    return {r['tipo'] for r in cur.fetchall()}


def publicar_onda(cur, limite_total=400, limite_por_tipo=None, agora=None):
    """Publica as aprovadas em fila, por tipo, respeitando pausas. Devolve
    {tipo: n} e grava a onda (uma por tipo) e a anotação na linha do tempo."""
    agora = agora or _dt.datetime.now(_dt.timezone.utc)
    pausados = tipos_pausados(cur)
    cur.execute("""SELECT tipo, COUNT(*) AS n FROM conteudo_paginas WHERE status = 'aprovada'
                   GROUP BY tipo ORDER BY tipo""")
    filas = {r['tipo']: r['n'] for r in cur.fetchall() if r['tipo'] not in pausados}
    if not filas:
        return {}
    publicado = {}
    sobra = limite_total
    # do tipo com menos fila para o com mais: a cota que um tipo não usa vai
    # para os próximos (as milhares de células de CNAE não travam o resto)
    ordem = sorted(filas, key=lambda t: (filas[t], t))
    for i, tipo in enumerate(ordem):
        por_tipo = limite_por_tipo or max(1, sobra // (len(ordem) - i))
        n = min(filas[tipo], por_tipo, sobra)
        if n <= 0:
            continue
        cur.execute("INSERT INTO conteudo_ondas (tipo, paginas, publicada_em) VALUES (%s, %s, %s) RETURNING id",
                    (tipo, n, agora))
        onda = cur.fetchone()['id']
        cur.execute("""UPDATE conteudo_paginas SET status = 'publicada', publicado_em = %s, onda = %s,
                       atualizado_em = %s
                       WHERE url IN (SELECT url FROM conteudo_paginas WHERE status = 'aprovada' AND tipo = %s
                                     ORDER BY COALESCE((extra->>'prioridade')::int, 50) DESC, criado_em LIMIT %s)""",
                    (agora, onda, agora, tipo, n))
        publicado[tipo] = cur.rowcount
        sobra -= cur.rowcount
        cfg.anotar(cur, 'onda', f'Onda {onda}: {cur.rowcount} páginas do tipo {tipo} publicadas', ref=f'onda:{onda}')
    return publicado


def avaliar_ondas(cur, inspecionar, dias=21, amostra=40, minimo=0.5, agora=None):
    """Ondas com 21+ dias sem medida: inspeciona uma amostra no Search Console
    (inspecionar(url) -> True/False/None) e pausa o tipo se < 50% indexada."""
    agora = agora or _dt.datetime.now(_dt.timezone.utc)
    cur.execute("""SELECT id, tipo FROM conteudo_ondas WHERE medida_em IS NULL
                   AND publicada_em < %s ORDER BY id""", (agora - _dt.timedelta(days=dias),))
    resultado = []
    for onda in cur.fetchall():
        cur.execute("SELECT url FROM conteudo_paginas WHERE onda = %s AND status = 'publicada' ORDER BY random() LIMIT %s",
                    (onda['id'], amostra))
        urls = [r['url'] for r in cur.fetchall()]
        vistos = [inspecionar(u) for u in urls]
        medidos = [v for v in vistos if v is not None]
        if not medidos:
            continue
        taxa = sum(medidos) / len(medidos)
        cur.execute('UPDATE conteudo_ondas SET inspecionadas = %s, indexadas = %s, medida_em = %s WHERE id = %s',
                    (len(medidos), sum(medidos), agora, onda['id']))
        if taxa < minimo:
            cur.execute('INSERT INTO conteudo_pausas (tipo, motivo) VALUES (%s, %s) ON CONFLICT (tipo) DO NOTHING',
                        (onda['tipo'], f'onda {onda["id"]}: {taxa:.0%} indexada em {dias} dias'))
            cfg.anotar(cur, 'pausa', f'Tipo {onda["tipo"]} pausado: onda {onda["id"]} com {taxa:.0%} indexada',
                       ref=f'pausa:{onda["id"]}')
        resultado.append((onda['id'], onda['tipo'], taxa))
    return resultado


# ---------------------------------------------------------------------------
# JSON-LD
# ---------------------------------------------------------------------------


def autor_ld(autor):
    if autor and autor.get('nome'):
        p = {'@type': 'Person', 'name': autor['nome'], 'url': cfg.SITE + autor['url']}
        if autor.get('cargo'):
            p['jobTitle'] = autor['cargo']
        if autor.get('linkedin'):
            p['sameAs'] = [autor['linkedin']]
        return p
    return {'@type': 'Organization', 'name': 'TurboVenda', '@id': cfg.SITE + '/#organization'}


def ld_pagina(p, autor=None, migalhas=()):
    url = cfg.SITE + p['url']
    tipo_ld = cfg.TIPOS_PAGINA.get(p['tipo'], {}).get('schema', 'Article')
    data_pub = (p.get('publicado_em') or p.get('criado_em') or _dt.datetime.now())
    data_mod = p.get('atualizado_em') or data_pub
    lds = []
    if tipo_ld == 'DefinedTerm':
        lds.append({'@context': 'https://schema.org', '@type': 'DefinedTerm', 'name': p.get('extra', {}).get('termo') or p['h1'],
                    'description': p.get('resposta') or p.get('descricao'), 'url': url,
                    'inDefinedTermSet': {'@type': 'DefinedTermSet', 'name': 'Glossário de vendas B2B do TurboVenda',
                                         'url': cfg.SITE + '/glossario'}})
    lds.append({'@context': 'https://schema.org', '@type': 'Article', 'headline': (p.get('h1') or p['titulo'])[:110],
                'description': p.get('descricao'), 'mainEntityOfPage': url, 'inLanguage': 'pt-BR',
                'datePublished': data_pub.isoformat(), 'dateModified': data_mod.isoformat(),
                'author': autor_ld(autor),
                'publisher': {'@type': 'Organization', 'name': 'TurboVenda', '@id': cfg.SITE + '/#organization'}})
    if migalhas:
        lds.append({'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': [
            {'@type': 'ListItem', 'position': i + 1, 'name': nome, 'item': cfg.SITE + link}
            for i, (nome, link) in enumerate(migalhas)]})
    faq = p.get('faq') or []
    if faq:
        lds.append({'@context': 'https://schema.org', '@type': 'FAQPage', 'mainEntity': [
            {'@type': 'Question', 'name': f['pergunta'],
             'acceptedAnswer': {'@type': 'Answer', 'text': texto_puro(f['resposta'])}} for f in faq]})
    return [cfg.json_ld(x) for x in lds]
