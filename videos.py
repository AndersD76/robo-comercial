"""Páginas de vídeo (/videos/<slug>): vídeo do YouTube + transcrição + capítulos.

Para publicar um vídeo, acrescente um item em VIDEOS depois de subir no
YouTube. A página só existe (e só entra no sitemap) quando há item aqui.
Os roteiros saem da fila em growth/fila-distribuicao/.

Campos:
  slug, titulo, descricao (1–2 frases), youtube_id, publicado (AAAA-MM-DD),
  duracao (ISO 8601, ex. 'PT7M30S'), capitulos [(segundos, 'título')],
  transcricao (texto corrido; parágrafos separados por linha em branco),
  relacionado (caminho da página do site que o vídeo explica, opcional).
"""

VIDEOS = []


def por_slug(slug):
    return next((v for v in VIDEOS if v['slug'] == slug), None)


def ld_video(v, site):
    """VideoObject com os capítulos como Clip (momentos-chave no Google)."""
    capitulos = v.get('capitulos') or []
    fim = [c[0] for c in capitulos[1:]] + [None]
    url = f"{site}/videos/{v['slug']}"
    ld = {
        '@context': 'https://schema.org', '@type': 'VideoObject',
        'name': v['titulo'], 'description': v['descricao'],
        'thumbnailUrl': f"https://i.ytimg.com/vi/{v['youtube_id']}/hqdefault.jpg",
        'uploadDate': v['publicado'], 'duration': v.get('duracao'),
        'embedUrl': f"https://www.youtube-nocookie.com/embed/{v['youtube_id']}",
        'contentUrl': f"https://www.youtube.com/watch?v={v['youtube_id']}",
        'publisher': {'@id': f'{site}/#organizacao'},
        'transcript': v.get('transcricao') or None,
    }
    if capitulos:
        ld['hasPart'] = [{'@type': 'Clip', 'name': nome, 'startOffset': ini,
                          **({'endOffset': f} if f else {}),
                          'url': f"{url}?t={ini}"}
                         for (ini, nome), f in zip(capitulos, fim)]
    return {k: x for k, x in ld.items() if x is not None}
