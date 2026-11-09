# Padrão de UTM do TurboVenda

Todo link que sai do site para um canal externo (e todo CTA interno que leva ao cadastro) leva os quatro parâmetros, **em minúsculas, sem acento, com hífen no lugar de espaço**. O site guarda a UTM da chegada e a grava no cadastro (`users.utm_source`), então é ela que diz de onde veio cada cliente — e é o que o `/admin/trafego` e o `/admin/organico` mostram.

| Parâmetro | O que é | Valores usados |
|---|---|---|
| `utm_source` | onde o link apareceu | `linkedin`, `youtube`, `instagram`, `x`, `whatsapp`, `newsletter`, `diretorio`, `comunidade`, `email`, e internos: `pseo`, `blog`, `ferramentas`, `alternativas`, `dados`, `site` |
| `utm_medium` | tipo de canal | `social`, `video`, `shorts`, `email`, `diretorio`, `comunidade`, `organic` (CTAs internos de páginas que recebem busca orgânica) |
| `utm_campaign` | o conteúdo ou ação | o **slug** da página divulgada (ex.: `base-de-dados-de-empresas-cnpj`) ou o nome da ação (ex.: `calculadora-resultado`, `relatorio`) |
| `utm_content` | variação, quando houver | `post-1`, `carrossel`, `bio`, `comentario` |

Exemplos:
- Post de LinkedIn sobre o guia de CNAE: `/blog/o-que-e-cnae-prospeccao?utm_source=linkedin&utm_medium=social&utm_campaign=o-que-e-cnae-prospeccao`
- Cadastro no B2B Stack: `/ferramentas/lista-de-empresas?utm_source=diretorio&utm_medium=diretorio&utm_campaign=b2bstack`
- CTA do relatório de dados: `/cadastro?utm_source=dados&utm_medium=organic&utm_campaign=relatorio`

Regras:
- **Nunca** UTM em link interno de navegação comum (menu, links entre artigos): só nos CTAs que levam ao cadastro, para medir qual página converte.
- UTM não cria página duplicada: todas as páginas têm canonical sem parâmetros.
- O ChatGPT acrescenta `utm_source=chatgpt.com` sozinho; não use esse valor nos seus links.
- Os rascunhos de `growth/fila-distribuicao/` já saem com UTM neste padrão (`growth/ferramentas/distribuicao.py`).

## Vídeo

Depois de publicar um vídeo no YouTube a partir de um roteiro da fila, cadastre-o em `videos.py` (ID, título, descrição, data, duração, capítulos e transcrição): a página `/videos/<slug>` com `VideoObject` e capítulos passa a existir e entra no sitemap no deploy seguinte.
