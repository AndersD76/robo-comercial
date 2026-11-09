"""Gráficos de barras em SVG renderizados no servidor (sem JavaScript).

Usados no relatório de dados (/dados/empresas-ativas-no-brasil) e nas versões
para incorporar (iframe). Uma série por gráfico, uma cor (azul validado com
o validador de paleta no fundo claro e no escuro), barras finas com ponta
arredondada de 4 px, rótulo de valor na ponta, texto nas cores de texto e
tooltip nativo (<title>) em cada barra.
"""
from html import escape

TEMAS = {
    # Site: fundo escuro (#0d1526). Embed: fundo claro próprio, porque o site
    # que incorpora pode ter qualquer cor.
    'escuro': {'barra': '#3987e5', 'texto': '#e2e8f0', 'texto2': '#94a3b8', 'eixo': '#334155'},
    'claro': {'barra': '#2a78d6', 'texto': '#0b0b0b', 'texto2': '#52514e', 'eixo': '#d6d4cf'},
}


def fmt_n(n):
    return f'{n:,}'.replace(',', '.')


def fmt_curto(n):
    if n >= 1_000_000:
        return f'{n / 1_000_000:.1f} mi'.replace('.', ',')
    if n >= 1_000:
        return f'{n / 1_000:.0f} mil'
    return str(n)


def _curto(rotulo, limite=31):
    rotulo = str(rotulo)
    return rotulo if len(rotulo) <= limite else rotulo[:limite - 1].rstrip() + '…'


def _barra_h(x, y, w, h, r=4):
    """Barra horizontal: quadrada na base, 4 px arredondada na ponta."""
    if w <= r:
        return f'M{x},{y}h{w:.1f}v{h}h{-w:.1f}z'
    return (f'M{x},{y}h{w - r:.1f}a{r},{r} 0 0 1 {r},{r}v{h - 2 * r}'
            f'a{r},{r} 0 0 1 {-r},{r}h{-(w - r):.1f}z')


def _coluna(x, base, w, h, r=4):
    """Coluna: quadrada na base, 4 px arredondada no topo."""
    if h <= r:
        return f'M{x},{base}v{-h:.1f}h{w}v{h:.1f}z'
    return (f'M{x},{base}v{-(h - r):.1f}a{r},{r} 0 0 1 {r},{-r}h{w - 2 * r}'
            f'a{r},{r} 0 0 1 {r},{r}v{h - r:.1f}z')


def barras(itens, titulo, unidade='empresas', tema='escuro', largura=640):
    """itens: [(rótulo, valor)] já ordenados. Retorna o <svg>."""
    c = TEMAS[tema]
    rot_w, val_w, linha, esp = 214, 64, 26, 18
    area = largura - rot_w - val_w
    maximo = max((v for _, v in itens), default=1) or 1
    altura = linha * len(itens) + 8
    partes = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {largura} {altura}" '
              f'width="100%" role="img" aria-label="{escape(titulo)}" '
              f'style="font-family:Inter,system-ui,sans-serif;max-width:{largura}px">',
              f'<title>{escape(titulo)}</title>',
              f'<line x1="{rot_w}" y1="0" x2="{rot_w}" y2="{altura - 4}" stroke="{c["eixo"]}" stroke-width="1"/>']
    for i, (rotulo, valor) in enumerate(itens):
        y = 4 + i * linha
        w = max(1.0, area * valor / maximo)
        partes.append(
            f'<g><title>{escape(rotulo)}: {fmt_n(valor)} {unidade}</title>'
            f'<text x="{rot_w - 8}" y="{y + esp / 2 + 4}" text-anchor="end" font-size="12.5" '
            f'fill="{c["texto2"]}">{escape(_curto(rotulo))}</text>'
            f'<path d="{_barra_h(rot_w, y, w, esp)}" fill="{c["barra"]}"/>'
            f'<text x="{rot_w + w + 6:.1f}" y="{y + esp / 2 + 4}" font-size="12.5" '
            f'fill="{c["texto"]}">{fmt_curto(valor)}</text></g>')
    partes.append('</svg>')
    return ''.join(partes)


def colunas(itens, titulo, destacar=(), unidade='empresas', tema='escuro', largura=640):
    """Série no tempo: [(rótulo, valor)]. Valor escrito só nos rótulos em
    `destacar` (nunca em todas as colunas); o resto fica no tooltip."""
    c = TEMAS[tema]
    topo, base_txt, altura_area = 22, 22, 200
    maximo = max((v for _, v in itens), default=1) or 1
    passo = largura / max(1, len(itens))
    w = min(24.0, passo - 6)
    base = topo + altura_area
    partes = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {largura} {base + base_txt}" '
              f'width="100%" role="img" aria-label="{escape(titulo)}" '
              f'style="font-family:Inter,system-ui,sans-serif;max-width:{largura}px">',
              f'<title>{escape(titulo)}</title>',
              f'<line x1="0" y1="{base}" x2="{largura}" y2="{base}" stroke="{c["eixo"]}" stroke-width="1"/>']
    for i, (rotulo, valor) in enumerate(itens):
        x = i * passo + (passo - w) / 2
        h = max(1.0, altura_area * valor / maximo)
        partes.append(f'<g><title>{escape(str(rotulo))}: {fmt_n(valor)} {unidade}</title>'
                      f'<path d="{_coluna(x, base, w, h)}" fill="{c["barra"]}"/>')
        if rotulo in destacar:
            partes.append(f'<text x="{x + w / 2:.1f}" y="{base - h - 6:.1f}" text-anchor="middle" '
                          f'font-size="12" fill="{c["texto"]}">{fmt_curto(valor)}</text>')
        partes.append(f'<text x="{x + w / 2:.1f}" y="{base + 15}" text-anchor="middle" '
                      f'font-size="{10.5 if passo < 40 else 11.5}" fill="{c["texto2"]}">{escape(str(rotulo))}</text></g>')
    partes.append('</svg>')
    return ''.join(partes)
