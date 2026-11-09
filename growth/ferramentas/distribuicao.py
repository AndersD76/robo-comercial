"""Pipeline de distribuição: rascunhos para cada página nova ou atualizada.

Compara os posts do blog, as ferramentas e o relatório de dados com o que já
foi distribuído (growth/fila-distribuicao/.estado.json) e, para cada item
novo ou com data de atualização mais recente, grava em growth/fila-distribuicao/
um arquivo com: post de LinkedIn, roteiro de vídeo curto (60 s), roteiro de
YouTube com capítulos, sequência de posts curtos e trecho de newsletter, com
links UTM no padrão de growth/utm.md.

Nada é publicado: os arquivos são rascunhos para aprovar e ajustar.

    python growth/ferramentas/distribuicao.py            # só o que é novo
    python growth/ferramentas/distribuicao.py --marcar-tudo  # registra o atual sem gerar
"""
import argparse
import json
import os
import re
import sys
from datetime import date

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, RAIZ)
SITE = 'https://www.turbovenda.com.br'
PASTA = os.path.join(RAIZ, 'growth', 'fila-distribuicao')
ESTADO = os.path.join(PASTA, '.estado.json')


def utm(caminho, fonte, meio, campanha, conteudo=''):
    q = f'utm_source={fonte}&utm_medium={meio}&utm_campaign={campanha}'
    return f'{SITE}{caminho}?{q}' + (f'&utm_content={conteudo}' if conteudo else '')


def _texto(html):
    t = re.sub(r'<[^>]+>', ' ', html or '')
    return re.sub(r'\s+', ' ', t).strip()


def itens_do_site():
    """[(chave, versão, dados)] de tudo o que merece distribuição."""
    os.environ.setdefault('DATABASE_URL', 'postgresql://x:y@127.0.0.1:1/db')
    import app as A  # noqa: E402  (importa o conteúdo; não sobe servidor)
    itens = []
    for p in A.BLOG_POSTS:
        secoes = re.findall(r'<h[23][^>]*>(.*?)</h[23]>', p.get('conteudo', ''), re.S)
        itens.append((f"blog/{p['slug']}", p.get('atualizado') or p['data'], {
            'tipo': 'artigo', 'titulo': p['titulo'], 'caminho': f"/blog/{p['slug']}",
            'slug': p['slug'], 'resumo': p.get('resposta') or p['desc'],
            'secoes': [_texto(x) for x in secoes][:8]}))
    for f in A.FERRAMENTAS:
        itens.append((f"ferramentas/{f['slug']}", '2026-10-17', {
            'tipo': 'ferramenta', 'titulo': f['nome'], 'caminho': f"/ferramentas/{f['slug']}",
            'slug': f['slug'], 'resumo': f['resumo'], 'secoes': []}))
    itens.append(('dados/empresas-ativas-no-brasil', '2026-11-09', {
        'tipo': 'relatório', 'titulo': 'Empresas ativas no Brasil: os números da Receita Federal',
        'caminho': '/dados/empresas-ativas-no-brasil', 'slug': 'relatorio-empresas-ativas',
        'resumo': ('26,2 milhões de empresas ativas com telefone ou e-mail na Receita Federal, '
                   'por estado, ano de abertura, segmento e porte, com gráficos para incorporar.'),
        'secoes': ['Empresas por estado', 'Empresas ativas por ano de abertura',
                   'Segmentos B2B com mais empresas', 'Empresas por porte', 'Metodologia']}))
    return itens


def rascunho(d):
    s, t = d['slug'], d['titulo']
    li = utm(d['caminho'], 'linkedin', 'social', s)
    yt = utm(d['caminho'], 'youtube', 'video', s)
    sh = utm(d['caminho'], 'youtube', 'shorts', s)
    th = utm(d['caminho'], 'x', 'social', s)
    nl = utm(d['caminho'], 'newsletter', 'email', s)
    secoes = d['secoes'] or ['O problema', 'Como resolver', 'Exemplo prático', 'Próximo passo']
    capitulos = '\n'.join(f'{i // 60:02d}:{i % 60:02d} {x}' for i, x in
                          zip([0] + [45 + 75 * k for k in range(len(secoes))], ['Abertura'] + secoes))
    pontos = '\n'.join(f'- {x}' for x in secoes[:4])
    fio = '\n'.join(f'{i + 2}/ {x}' for i, x in enumerate(secoes[:5]))
    return f"""# Rascunhos de distribuição — {t}

Status: **rascunho — aprovar e ajustar antes de publicar**. Tipo: {d['tipo']}. Página: {SITE}{d['caminho']}
Gerado em {date.today():%d/%m/%Y} por `growth/ferramentas/distribuicao.py`. Não use número que não esteja na página.

## Post de LinkedIn

{d['resumo']}

O que você encontra no {d['tipo']}:
{pontos}

Link: {li}

#prospecção #vendasB2B #pequenasempresas

## Roteiro de vídeo curto (60 s — Shorts, Reels, TikTok)

- **0–3 s (gancho):** "{t}" — em 60 segundos.
- **3–40 s:** um ponto por frase, mostrando a tela da página:
{pontos}
- **40–55 s:** um exemplo concreto da página (mostre na tela, não invente número).
- **55–60 s:** "O passo a passo completo está no link da descrição."
- Descrição: {sh}

## Roteiro de YouTube (6–10 min, com capítulos)

Título: {t}
Descrição (primeira linha): {d['resumo']}
Link: {yt}

Capítulos:
{capitulos}

Roteiro: abrir com a pergunta que a página responde; um capítulo por seção, sempre mostrando a página ou a ferramenta;
fechar com o próximo passo (link). Depois de publicar, criar a página de vídeo com transcrição (ver growth/utm.md, seção vídeo).

## Sequência de posts curtos (X, Threads, LinkedIn em carrossel)

1/ {t} — {d['resumo'][:180]}
{fio}
{len(secoes[:5]) + 2}/ Tudo detalhado aqui: {th}

## Trecho de newsletter

**{t}**
{d['resumo']} [Ler na íntegra]({nl})
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--marcar-tudo', action='store_true',
                    help='registra o conteúdo atual como já distribuído, sem gerar')
    ap.add_argument('--so', help='gera só para estas chaves (separadas por vírgula)')
    args = ap.parse_args()
    os.makedirs(PASTA, exist_ok=True)
    estado = {}
    if os.path.exists(ESTADO):
        with open(ESTADO, encoding='utf-8') as f:
            estado = json.load(f)
    alvo = set(args.so.split(',')) if args.so else None
    novos = 0
    for chave, versao, dados in itens_do_site():
        if alvo is not None and chave not in alvo:
            continue
        if not args.marcar_tudo and estado.get(chave) != versao:
            nome = f"{date.today():%Y-%m-%d}-{dados['slug']}.md"
            with open(os.path.join(PASTA, nome), 'w', encoding='utf-8', newline='\n') as f:
                f.write(rascunho(dados))
            novos += 1
        estado[chave] = versao
    with open(ESTADO, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(estado, f, ensure_ascii=False, indent=1, sort_keys=True)
    print(f'{novos} rascunho(s) gerado(s) em {os.path.relpath(PASTA, RAIZ)}')


if __name__ == '__main__':
    main()
