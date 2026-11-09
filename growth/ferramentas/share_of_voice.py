"""Share of voice em IA: o TurboVenda é citado quando o cliente pergunta?

Faz cada pergunta de growth/dados/sov-perguntas.txt ao Claude com busca na
web (localização: Brasil) e registra se turbovenda.com.br foi citado, em que
posição entre as fontes, se apareceu nos resultados da busca e quais
concorrentes surgiram. Grava cada resposta na tabela `share_of_voice` (para
a tendência semanal) e um resumo em growth/dados/share-of-voice-AAAA-MM-DD.md.

Custo por rodada de 30 perguntas: algo como US$ 3 a 6 (tokens + buscas a
US$ 10 por mil); o valor real sai no fim, a partir do uso de cada resposta.

    railway run python growth/ferramentas/share_of_voice.py
    (precisa de ANTHROPIC_API_KEY e DATABASE_URL; --sem-banco só gera o .md)
"""
import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import date
from urllib.parse import urlparse

import anthropic

MODELO = 'claude-opus-5-5'
MARCA = 'turbovenda.com.br'
# Nomes como aparecem no texto da resposta: com a busca de filtragem dinâmica
# (web_search_20260209) o modelo cita as fontes pelo nome, sem citação formal
NOMES = {'TurboVenda': ('turbovenda',)}
CONCORRENTES = {
    'econodata.com.br': 'Econodata', 'speedio.com.br': 'Speedio', 'leads2b.com': 'Leads2b',
    'apollo.io': 'Apollo', 'empresaqui.com.br': 'EmpresAqui', 'cnpj.biz': 'CNPJ.biz',
    'casadosdados.com.br': 'Casa dos Dados', 'agendor.com.br': 'Agendor',
    'rdstation.com': 'RD Station', 'ramper.com.br': 'Ramper', 'meetime.com.br': 'Meetime',
    'exactsales.com.br': 'Exact Sales', 'cnpja.com': 'CNPJá', 'lusha.com': 'Lusha',
    'snov.io': 'Snov.io', 'hunter.io': 'Hunter', 'b2bstack.com.br': 'B2B Stack',
    'apify.com': 'Apify',
}
for _dom, _nome in CONCORRENTES.items():
    NOMES.setdefault(_nome, (_nome.lower(), _dom))
# Preços para a estimativa de custo (conferir em platform.claude.com/pricing)
US_ENTRADA, US_SAIDA, US_BUSCA = 4.00 / 1e6, 20.00 / 1e6, 10.00 / 1000
INSTRUCAO = ('Responda como um assistente responderia a um dono de pequena empresa no '
             'Brasil, em português, de forma direta. Pesquise na web e cite as fontes.')
DDL = """CREATE TABLE IF NOT EXISTS share_of_voice (
    id BIGSERIAL PRIMARY KEY,
    rodada DATE NOT NULL,
    pergunta TEXT NOT NULL,
    modelo TEXT NOT NULL,
    citou BOOLEAN NOT NULL,
    posicao INTEGER,
    nos_resultados BOOLEAN NOT NULL,
    dominios_citados JSONB,
    urls_citadas JSONB,
    dominios_resultados JSONB,
    concorrentes JSONB,
    marcas JSONB,
    buscas INTEGER,
    tokens_entrada INTEGER,
    tokens_saida INTEGER,
    erro TEXT DEFAULT '',
    criado_em TIMESTAMPTZ DEFAULT now())"""


def dominio(url):
    host = urlparse(url or '').netloc.lower()
    return host[4:] if host.startswith('www.') else host


def perguntar(client, pergunta):
    """Uma pergunta, com o laço de pause_turn que a busca do servidor pode pedir."""
    mensagens = [{'role': 'user', 'content': f'{INSTRUCAO}\n\n{pergunta}'}]
    blocos, usos = [], []
    for _ in range(4):
        r = client.beta.messages.create(
            model=MODELO, max_tokens=8000,
            betas=['server-side-fallback-2026-07-01'], fallbacks='default',
            output_config={'effort': 'low'},
            tools=[{'type': 'web_search_20260209', 'name': 'web_search', 'max_uses': 3,
                    'user_location': {'type': 'approximate', 'country': 'BR',
                                      'region': 'Rio Grande do Sul', 'city': 'Porto Alegre',
                                      'timezone': 'America/Sao_Paulo'}}],
            messages=mensagens)
        blocos += list(r.content)
        usos.append(r.usage)
        if r.stop_reason != 'pause_turn':
            break
        mensagens.append({'role': 'assistant', 'content': r.content})
    return blocos, usos, r.stop_reason


def mencoes(texto):
    """Marcas citadas no texto, na ordem em que aparecem."""
    t = texto.lower()
    achadas = []
    for nome, chaves in NOMES.items():
        pos = [m.start() for k in chaves for m in re.finditer(re.escape(k), t)]
        if pos:
            achadas.append((min(pos), nome))
    return [nome for _, nome in sorted(achadas)]


def analisar(blocos):
    citadas, resultados = [], []
    texto = ' '.join(b.text for b in blocos if b.type == 'text')
    for url in re.findall(r'https?://[^\s)\]>"]+', texto):
        if url not in citadas:
            citadas.append(url.rstrip('.,;'))
    for b in blocos:
        if b.type == 'text':
            for c in getattr(b, 'citations', None) or []:
                url = getattr(c, 'url', None)
                if url and url not in citadas:
                    citadas.append(url)
        elif b.type == 'web_search_tool_result':
            conteudo = getattr(b, 'content', None)
            if isinstance(conteudo, list):   # erro vem como objeto, sucesso como lista
                resultados += [getattr(x, 'url', '') for x in conteudo]
    dom_citados = list(dict.fromkeys(dominio(u) for u in citadas))
    dom_result = list(dict.fromkeys(dominio(u) for u in resultados if u))
    marcas = mencoes(texto)
    for d in dom_citados:   # citação formal sem o nome no texto também conta
        nome = 'TurboVenda' if d.endswith(MARCA) else next(
            (n for k, n in CONCORRENTES.items() if d.endswith(k)), None)
        if nome and nome not in marcas:
            marcas.append(nome)
    posicao = marcas.index('TurboVenda') + 1 if 'TurboVenda' in marcas else None
    concorrentes = sorted({n for n in marcas if n != 'TurboVenda'} |
                          {nome for d in dom_result for chave, nome in CONCORRENTES.items()
                           if d.endswith(chave)})
    return {'citou': posicao is not None, 'posicao': posicao, 'marcas': marcas,
            'nos_resultados': any(d.endswith(MARCA) for d in dom_result),
            'dominios_citados': dom_citados, 'urls_citadas': citadas,
            'dominios_resultados': dom_result, 'concorrentes': concorrentes}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--perguntas', default='growth/dados/sov-perguntas.txt')
    ap.add_argument('--limite', type=int, default=0, help='só as N primeiras (teste)')
    ap.add_argument('--sem-banco', action='store_true')
    args = ap.parse_args()
    perguntas = [linha.strip() for linha in open(args.perguntas, encoding='utf-8')
                 if linha.strip() and not linha.startswith('#')]
    if args.limite:
        perguntas = perguntas[:args.limite]
    client = anthropic.Anthropic()
    conn = None
    if not args.sem_banco:
        import psycopg2
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        conn.cursor().execute(DDL)
        conn.cursor().execute('ALTER TABLE share_of_voice ADD COLUMN IF NOT EXISTS marcas JSONB')
        conn.commit()

    hoje, linhas = date.today(), []
    custo = 0.0
    for i, pergunta in enumerate(perguntas, 1):
        erro, buscas, ent, sai = '', 0, 0, 0
        try:
            blocos, usos, parada = perguntar(client, pergunta)
            a = analisar(blocos)
            for u in usos:
                ent += (u.input_tokens or 0) + (getattr(u, 'cache_read_input_tokens', 0) or 0)
                sai += u.output_tokens or 0
                stu = getattr(u, 'server_tool_use', None)
                buscas += (getattr(stu, 'web_search_requests', 0) or 0) if stu else 0
            if parada == 'refusal':
                erro = 'recusa'
        except anthropic.APIStatusError as e:
            a = analisar([])
            erro = f'{e.status_code}: {str(e.message)[:200]}'
        except anthropic.APIConnectionError as e:
            a = analisar([])
            erro = f'conexão: {e}'[:200]
        custo += ent * US_ENTRADA + sai * US_SAIDA + buscas * US_BUSCA
        linhas.append({'pergunta': pergunta, **a, 'buscas': buscas, 'erro': erro})
        marca = f"citado em {a['posicao']}º" if a['citou'] else (
            'só nos resultados' if a['nos_resultados'] else 'ausente')
        print(f'[{i}/{len(perguntas)}] {marca} | marcas: {", ".join(a["marcas"][:5])}'
              f'{" | ERRO " + erro if erro else ""}', flush=True)
        if conn:
            conn.cursor().execute(
                'INSERT INTO share_of_voice (rodada, pergunta, modelo, citou, posicao, '
                'nos_resultados, dominios_citados, urls_citadas, dominios_resultados, '
                'concorrentes, marcas, buscas, tokens_entrada, tokens_saida, erro) '
                'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                (hoje, pergunta, MODELO, a['citou'], a['posicao'], a['nos_resultados'],
                 json.dumps(a['dominios_citados']), json.dumps(a['urls_citadas']),
                 json.dumps(a['dominios_resultados']), json.dumps(a['concorrentes']),
                 json.dumps(a['marcas']), buscas, ent, sai, erro))
            conn.commit()
        time.sleep(1)

    validas = [x for x in linhas if not x['erro']]
    citou = sum(x['citou'] for x in validas)
    nos_res = sum(x['nos_resultados'] for x in validas)
    dominios = Counter(d for x in validas for d in x['dominios_resultados'])
    marcas = Counter(m for x in validas for m in x['marcas'])
    conc = Counter(c for x in validas for c in x['concorrentes'])
    saida = f'growth/dados/share-of-voice-{hoje:%Y-%m-%d}.md'
    with open(saida, 'w', encoding='utf-8', newline='\n') as f:
        f.write(f'# Share of voice em IA — {hoje:%d/%m/%Y}\n\n')
        f.write(f'Modelo: `{MODELO}` com busca na web (localização: Porto Alegre, BR). '
                f'{len(validas)} perguntas respondidas de {len(linhas)}. '
                f'Custo estimado da rodada: US$ {custo:.2f}.\n\n')
        f.write(f'- **TurboVenda citado:** {citou} de {len(validas)} respostas'
                f' ({(citou / len(validas) if validas else 0):.0%})\n')
        f.write(f'- **TurboVenda nos resultados da busca (citado ou não):** {nos_res} de {len(validas)}\n\n')
        f.write('## Concorrentes que aparecem (citados ou nos resultados)\n\n| Concorrente | Respostas |\n|---|---|\n')
        for nome, n in conc.most_common():
            f.write(f'| {nome} | {n} |\n')
        f.write('\n## Marcas citadas no texto das respostas\n\n| Marca | Respostas |\n|---|---|\n')
        for m, n in marcas.most_common(20):
            f.write(f'| {m} | {n} |\n')
        f.write('\n## Domínios que mais aparecem nos resultados da busca\n\n| Domínio | Respostas |\n|---|---|\n')
        for d, n in dominios.most_common(20):
            f.write(f'| {d} | {n} |\n')
        f.write('\n## Por pergunta\n\n| Pergunta | TurboVenda | Marcas citadas, em ordem |\n|---|---|---|\n')
        for x in linhas:
            st = (f"citado ({x['posicao']}º)" if x['citou'] else
                  'só nos resultados' if x['nos_resultados'] else
                  ('erro' if x['erro'] else 'ausente'))
            f.write(f"| {x['pergunta']} | {st} | {', '.join(x['marcas'][:5]) or '-'} |\n")
    print(f'\ncitado em {citou}/{len(validas)}; custo estimado US$ {custo:.2f}; resumo em {saida}')
    if conn:
        conn.close()
    return 0 if validas else 1


if __name__ == '__main__':
    sys.exit(main())
