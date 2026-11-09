# Relatório do motor de visibilidade orgânica — TurboVenda

Atualizado em 09/11/2026. **Fases 0 a 6 implementadas e no ar.** O que falta depende de dados, acessos ou decisões suas (seções 3, 4 e 5).

## 1. O que foi implementado

### Fase 0 — Diagnóstico (branch `growth/fase-0-diagnostico`)
- `growth/diagnostico.md`: rotas classificadas, crawl, Lighthouse, robots/sitemap/redirects, dados estruturados, tráfego, SERPs e 16 problemas priorizados por impacto × esforço.
- `growth/mapa-intencao.csv`: 23 buscas em 6 clusters, com página-alvo e entradas medidas.
- `growth/pesquisa-serp.md` e `growth/dados/serp.csv`: SERPs das 20 buscas do ICP.
- `growth/ferramentas/crawl.py` (crawl como Googlebot mobile) e `growth/ferramentas/resumo_lighthouse.py`.

### Fase 1 — SEO técnico (branch `growth/fase-1-seo-tecnico`, no ar desde 08/11 19:37)
| Mudança | Arquivos |
|---|---|
| IP real do visitante no limitador (`ProxyFix` com 2 saltos, confirmado no log: o `X-Forwarded-For` chega com 2 valores). Antes, todos os visitantes dividiam um limite só (200/min e 5 cadastros/min) | `app.py` |
| Googlebot, Bingbot e Applebot verificados por DNS reverso + confirmação direta ficam fora do limite (só GET/HEAD; cache de 24 h por IP) | `app.py` |
| Inter servida do próprio site com preload (um arquivo variável, 47 KB) no lugar do Google Fonts com 7 pesos, em 23 templates | `static/fonts/`, `templates/_fontes.html` |
| Font Awesome fora do caminho crítico nas páginas públicas | `templates/_icones.html` |
| Títulos ≤ 60 e descrições ≤ 155 em todos os templates (filtros `titulo_seo`/`descricao_seo`); programáticas com nome curto do segmento e contagem; 15 títulos curtos de post; home, preços, cadastro e blog reescritos com a intenção primeiro | `app.py`, `templates/*` |
| robots.txt num grupo só: Googlebot, Bingbot, Applebot, DuckDuckBot, OAI-SearchBot, ChatGPT-User, GPTBot, PerplexityBot, Perplexity-User, ClaudeBot, Claude-SearchBot, Claude-User e Google-Extended liberados com as mesmas regras de bloqueio da área logada | `app.py` |
| 301 de `/caminho/` para `/caminho` | `app.py` |
| `lastmod` real nas 10 mil programáticas (data da base da Receita) e hubs de segmento indexáveis no sitemap; IndexNow reenvia quando a base muda (no deploy: 10.099 URLs enviadas, todas aceitas) | `app.py` |
| Paginação com canonical próprio; H1 no cadastro; `Blog` e `BreadcrumbList` no JSON-LD de todas as páginas públicas menos a home; `Organization` com `@id`, logo quadrado e espaço para CNPJ/perfis | `app.py`, `templates/*` |
| Guarda no CI: `tests/test_seo.py` (48 páginas fixas) e `tests/test_seo_pseo.py` (programáticas sobre base sintética) num passo próprio do `ci.yml`; Lighthouse diário em produção (`lighthouse.yml`, `lighthouserc.json`) | `.github/workflows/`, `tests/` |

### Fase 3 — GEO (branch `growth/fase-3-geo`)
| Mudança | Arquivos |
|---|---|
| `/llms-full.txt` gerado do próprio conteúdo (ferramentas, comparativos com data de consulta, páginas por segmento e os 30 artigos em texto limpo, ~17 mil palavras); `/llms.txt` aponta para ele | `app.py` |
| Monitor de crawlers: cada acesso de robô conhecido é gravado com nome (GPTBot, OAI-SearchBot, ChatGPT-User, ClaudeBot, Claude-SearchBot, PerplexityBot, Googlebot, Bingbot…) e status, em qualquer resposta (inclusive `llms.txt`, 404 e 429); Googlebot/Bingbot/Applebot verificados por DNS reverso; tabela no `/admin/trafego` | `app.py`, `templates/admin_trafego.html` |
| Resposta direta de 40–60 palavras logo abaixo do H1 nos 6 pilares (resume o próprio post, sem dado novo) | `app.py`, `templates/blog_post.html` |
| Texto canônico da marca em 1 linha, 1 parágrafo e 1 página | `growth/entidade.md` |
| Painel de share of voice: 30 perguntas fixas do ICP feitas ao Claude com busca na web (Brasil), registrando se o TurboVenda é citado, a posição e os concorrentes; histórico na tabela `share_of_voice` | `growth/ferramentas/share_of_voice.py`, `growth/dados/sov-perguntas.txt` |

**Linha de base do share of voice (09/11/2026, `growth/dados/share-of-voice-2026-11-09.md`):** o TurboVenda foi citado em **0 de 30** respostas e apareceu nos resultados da busca em 2. Quem aparece: Econodata e Agendor (11 respostas cada), EmpresAqui (9), Speedio (8), Leads2b (6), Apollo (5). Custo da rodada: US$ 4,27. A medição usa a busca do Claude; o ChatGPT usa outro índice e já trouxe 10 cadastros em 3 semanas, então os dois sinais se complementam.

### Fase 2 — Conteúdo e links internos (branch `growth/fase-2-conteudo`)
| Mudança | Arquivos |
|---|---|
| Motor de links internos: 6 clusters do mapa de intenção, cada um com pilar e satélites; cada post linka o pilar, os 3 satélites mais parecidos (TF-IDF) e 1 post de outro tema, e as ferramentas/dados do tema. O pilar lista todos os satélites. Antes, cada post listava os outros 29 | `links_internos.py`, `templates/blog_post.html` |
| Zero post órfão, garantido por teste (todo post é linkado por outro post, além do índice do blog) | `tests/test_seo.py` |
| Data visível "Publicado em dd/mm/aaaa" e "atualizado em" (campo `atualizado` no post), com `dateModified` no JSON-LD | `templates/blog_post.html`, `app.py` |
| Fila de frescor com a telemetria própria (Google/Bing por página, 28 contra 28 dias), até haver dados do Search Console | `growth/ferramentas/frescor.py`, `growth/fila-atualizacao.md` |
| 4 briefs para buscas sem página: empresas abertas recentemente, WhatsApp, comparativo de ferramentas, sócios pelo CNPJ | `growth/briefs/` |
| Rascunhos de página Sobre e política editorial (não publicados: dependem de TODO-VALIDAR) | `growth/rascunhos/` |

Já existiam e cumprem a Fase 2: limiar de conteúdo com noindex automático nas programáticas, FAQ específica por página, contagem por porte, bairro e ano de abertura, links para segmentos e cidades vizinhas.

### Fase 4 — Ativos que ganham link (branch `growth/fase-4-ativos`)
| Mudança | Arquivos |
|---|---|
| Relatório **/dados/empresas-ativas-no-brasil**: 26,2 mi empresas ativas com contato por estado, ano de abertura, segmento e porte, com tabela, metodologia, "como citar" e JSON-LD `Dataset`. Calculado no PC a partir da base completa de out/2026 (só o agregado vai para o banco) e recalculado sozinho a cada atualização mensal da base | `scripts/relatorio_dados.py`, `app.py`, `templates/relatorio_dados.html` |
| 4 gráficos SVG sem JavaScript (cor validada para fundo claro e escuro, tooltip e tabela em cada um) e versão para incorporar em `/embed/<gráfico>` (fundo próprio, liberada para iframe, com link de atribuição) | `relatorio_graficos.py`, `templates/relatorio_embed.html` |
| Kit de imprensa **/imprensa**: números para citar, frases prontas, gráficos, logo e contato (sem porta-voz nem citação inventada) | `templates/imprensa.html` |
| Calculadora com resultado no endereço, botão "copiar link" e CTA no resultado; lista de empresas com "copiar link" | `templates/ferramenta_*.html` |
| 28 alvos de link (diretórios, veículos, associações, dados abertos, universidades) com ângulo de abordagem. Nada enviado | `growth/alvos-link.csv` |

### Fase 5 — Distribuição (branch `growth/fase-5-distribuicao`)
| Mudança | Arquivos |
|---|---|
| Pipeline de reaproveitamento: a cada post, ferramenta ou relatório novo/atualizado, gera post de LinkedIn, roteiro de 60 s, roteiro de YouTube com capítulos, sequência de posts e trecho de newsletter, com UTM. Primeiros 10 rascunhos gerados (pilares, ferramentas, relatório). Nada é publicado | `growth/ferramentas/distribuicao.py`, `growth/fila-distribuicao/` |
| Checklist dos 22 diretórios com status (textos prontos em `docs/trafego/distribuicao/diretorios.md`) | `growth/diretorios.md` |
| Mapa de comunidades do ICP e 10 respostas-modelo | `growth/comunidades.md` |
| Páginas de vídeo `/videos/<slug>` com `VideoObject`, capítulos (Clip) e transcrição; aparecem quando um vídeo for cadastrado | `videos.py`, `templates/video.html` |

### Fase 6 — Medição (branch `growth/fase-6-medicao`)
| Mudança | Arquivos |
|---|---|
| Padrão de UTM | `growth/utm.md` |
| Ingestão diária (6h) do Search Console (consultas × páginas × dia, sitemaps enviadas × indexadas, inspeção de 10 URLs prioritárias) e do Bing Webmaster, nas tabelas `busca_*`. Liga sozinha quando as credenciais forem configuradas (seção 4) | `medicao.py`, `app.py` |
| Painel **/admin/organico**: entradas de buscadores e de IA, por tipo de página, cadastros por origem, robôs (com 429), share of voice por rodada; com o Search Console: posição 4–15, CTR abaixo do esperado, indexação | `templates/admin_organico.html` |
| Relatório semanal automático (segunda, 8h) em `relatorios_semanais`, visível no painel; o primeiro está em `growth/relatorios/` | `medicao.py` |
| Testes da ingestão com respostas simuladas das APIs | `tests/test_medicao.py` |

## 2. Antes e depois (produção)

| Métrica | Antes (08/11) | Depois (09/11) |
|---|---|---|
| Títulos acima de 60 caracteres (crawl de 450 URLs) | 314 | **0** |
| Descrições acima de 155 | 221 | **0** |
| Respostas 429 no crawl | 41 | 0* |
| Tempo de resposta do HTML (p50 / p90) | 210 / 377 ms | 181 / 222 ms |
| Páginas indexáveis no crawl | 342 | 402 |
| Lighthouse mobile — home (nota / LCP) | 83 / 3,4 s | 90 / 2,8 s |
| Lighthouse mobile — preços | 83 / 3,5 s | 92 / 2,7 s |
| Lighthouse mobile — cadastro | 83 / 3,5 s | 91 / 2,7 s |
| Lighthouse mobile — lista de empresas | 90 / 2,9 s | 99 / **1,2 s** |

\* O segundo crawl foi feito abaixo de 200 req/min, porque o meu IP não é buscador verificado; a isenção do Googlebot está coberta por teste automatizado.

Lighthouse mobile das 10 páginas depois do deploy (09/11, laboratório):

| Página | Perf | SEO | Acess. | LCP | CLS | TBT | INP* | JS (KB) | Peso total (KB) |
|---|---|---|---|---|---|---|---|---|---|
| `/` | 90 | 100 | 86 | 2.8 s | 0.000 | 87 ms | - | 0 | 247 |
| `/precos` | 92 | 100 | 93 | 2.7 s | 0.000 | 0 ms | - | 0 | 230 |
| `/cadastro` | 91 | 100 | 79 | 2.7 s | 0.000 | 0 ms | - | 0 | 229 |
| `/ferramentas/lista-de-empresas` | 99 | 100 | 85 | 1.2 s | 0.000 | 107 ms | - | 0 | 55 |
| `/empresas/cidade/porto-alegre-rs` | 99 | 100 | 84 | 1.2 s | 0.000 | 94 ms | - | 0 | 55 |
| `/empresas/usinagem/caxias-do-sul-rs` | 90 | 100 | 92 | 1.3 s | 0.000 | 413 ms | - | 0 | 56 |
| `/empresas/usinagem` | 98 | 100 | 84 | 1.2 s | 0.000 | 138 ms | - | 0 | 56 |
| `/blog/como-prospectar-clientes-b2b` | 91 | 100 | 86 | 2.7 s | 0.000 | 0 ms | - | 0 | 232 |
| `/alternativas/econodata` | 87 | 100 | 93 | 1.3 s | 0.000 | 495 ms | - | 0 | 56 |
| `/para/industria` | 92 | 100 | 93 | 2.7 s | 0.000 | 0 ms | - | 0 | 226 |

*INP só existe em dado de campo; no laboratório o TBT é o indicador equivalente.

As programáticas e ferramentas caíram para 1,2–1,3 s. As páginas que usam ícones ficaram em 2,7–2,8 s por causa da fonte de ícones (153 KB); a correção (ícones só depois do carregamento) foi publicada em seguida — ver seção 2.1.

### 2.1 Depois dos ícones fora do caminho crítico (09/11, 10:15)

| Página | Nota | LCP antes da Fase 1 | LCP agora |
|---|---|---|---|
| Home | 81* | 3,4 s | **1,9 s** |
| Blog (pilar) | 98 | 3,5 s | **1,8 s** |
| `/para/industria` | 99 | 3,5 s | **1,8 s** |
| Preços | 93 | 3,5 s | 2,6 s |
| Cadastro | 91 | 3,5 s | 2,7 s |

\* Nota da home puxada por 684 ms de bloqueio de CPU da máquina que mediu (sobrecarregada); o LCP é o que interessa. Em preços e cadastro sobra o CSS próprio bloqueante (`tokens.css` e `components.css`, a internalizar) e, no cadastro, o banner de cookies como maior elemento da tela.


## 3. TODO-VALIDAR (depende de você)

1. ~~CNPJ da AndersTech~~ **feito em 09/11:** `MARCA_CNPJ=42.073.416/0001-80` no Railway (ANDERS CONSULTORIA EM GESTAO EMPRESARIAL LTDA, nome fantasia ANDERSTECH, Passo Fundo/RS, na base da Receita de out/2026). **Falta:** perfis oficiais (LinkedIn, Instagram, YouTube…) em `MARCA_PERFIS` (URLs separadas por espaço); a página da empresa no LinkedIn ainda não existe.
2. **Crawlers só de treino** (CCBot, Bytespider, Applebot-Extended, meta-externalagent): hoje liberados pelo `*`. Decidir se bloqueia.
3. **Página de autor:** quem assina os artigos (nome, função, experiência real). Hoje o autor é a organização; o E-E-A-T pede uma pessoa com página própria.
4. **Briefs em `growth/briefs/`:** aprovar quais viram página. O de sócios pelo CNPJ exige subir os 8,6 mi registros de sócios para o banco (custo de armazenamento); o de empresas recém-abertas exige atualizar a base de produção.
5. **Rascunhos em `growth/rascunhos/`:** completar CNPJ, endereço, fundadores e uso de IA na página Sobre e na política editorial.
6. ~~Texto do `/llms.txt`~~ **resolvido em 09/11:** o site todo vende "500 leads/mês", mas a cota contava o total da conta (o cliente pagante travaria nos primeiros 500). A cota do Starter passou a contar os últimos 30 dias (`_sql_leads_na_cota`, `tests/test_cota.py`).
7. **Rascunhos de distribuição** em `growth/fila-distribuicao/`: revisar e aprovar antes de publicar.
8. **Textos dos diretórios** (out/2026) citam 6,7 mi CNPJs; o relatório novo usa 26,2 mi (base completa). Escolher qual número usar em cada lugar, sempre com a fonte.

## 4. Ações manuais (só você pode fazer), em ordem de prioridade

1. **Bing Webmaster Tools** (10 min): bing.com/webmasters → entrar → *Importar do Google Search Console*. O Bing trouxe só 45 visitas em 3 semanas e é o índice usado pelo ChatGPT Search e pelo Copilot. O IndexNow já envia tudo; falta a conta para ver o resultado.
2. **Search Console → Configurações → Estatísticas de rastreamento** (5 min): ver se o Googlebot vinha recebendo 429 antes de 08/11 e se a curva de rastreio sobe agora.
3. **Search Console por API** (15 min): criar uma conta de serviço no Google Cloud, adicionar o e-mail dela como usuário (leitura) da propriedade e configurar no Railway `GSC_CREDENCIAIS_JSON` (conteúdo do JSON) e `GSC_PROPRIEDADE` (ex.: `sc-domain:turbovenda.com.br`). O `/admin/organico` passa a mostrar consultas, posição, CTR e indexação no dia seguinte.
3.1. **Bing por API** (5 min): Bing Webmaster → Configurações → Acesso à API → gerar chave → `BING_API_KEY` no Railway.
4. ~~DNS sem www~~ **feito em 09/11:** ALIAS `@` na Hostinger para o Railway (porta 5000) + TXT `_railway-verify`; `https://turbovenda.com.br/<caminho>` responde 301 para o www com o mesmo caminho.
5. ~~Railway "Wait for CI"~~ **feito em 09/11** pela API (o deploy só acontece se o CI passar). O healthcheck no `/health` (300 s) ficou gravado direto nas configurações do serviço: o `railway.toml` foi descontinuado pelo Railway (deixa de valer em 01/12/2026) e saiu do repositório.
6. **Perfis em B2B Stack, G2/Capterra/GetApp e SaaSHub**: são as fontes que mais aparecem quando se pergunta "melhor ferramenta de prospecção B2B". Checklist com status em `growth/diretorios.md`.
7. **Imprensa e links**: usar `growth/alvos-link.csv` e o `/imprensa` para as primeiras abordagens (Contábeis e Base dos Dados primeiro).

## 5. O que ficou para decisão sua (custo ou dados)

| Item | Por que não fiz sozinho | O que muda |
|---|---|---|
| **Atualizar a base do Postgres** (jul/2026 → out/2026) | operação pesada no banco de produção (6,7 mi linhas) | 10 mil páginas `/empresas` com dados de 5 meses mais novos; destrava o brief de empresas recém-abertas |
| **Subir os 8,6 mi sócios para o banco** | custo de armazenamento no Neon | destrava a ferramenta "sócios pelo CNPJ" (busca de volume alto) |
| **Share of voice semanal** | ~US$ 4 por rodada na API da Anthropic | tendência semanal de citação em IA (hoje só a linha de base de 09/11) |
| **Gerador de mensagem com link compartilhável** | exigiria guardar o texto do usuário ou pagar a IA a cada visita | — |
| **Respostas diretas nos outros 24 posts** | texto novo em cada post; os 6 pilares já têm | formato citável em todo o blog |

## 6. Linha de base e meta de 90 dias

| Métrica | Linha de base | Meta 90 dias (até 07/02/2027) | Fonte |
|---|---|---|---|
| Entradas orgânicas Google por semana | ~1.200 (3.680 em 3 semanas) | 3.000 | `pageviews` |
| Entradas vindas do Bing por semana | ~15 | 150 | `pageviews` |
| Entradas e cadastros vindos de IA (ChatGPT, Perplexity, Copilot) | 57 entradas e 10 cadastros em 3 semanas | 300 entradas e 40 cadastros por trimestre | `pageviews`, `users.utm_source` |
| Share of voice em IA (30 perguntas fixas) | 0 de 30 citações; 2 de 30 nos resultados | citado em 6 de 30 | `share_of_voice` |
| Cadastros por semana | ~10 | 25 | `users` |
| Títulos > 60 / descrições > 155 no crawl | 0 / 0 | manter 0 | `crawl.py` |
| LCP mobile de laboratório nas 10 páginas | 1,2–2,8 s | todas < 2,5 s | Lighthouse diário |
| Páginas indexadas / enviadas | sem acesso | ≥ 70% | Search Console (ação 3) |
| Acessos de robôs de IA de busca (OAI-SearchBot, Claude-SearchBot, PerplexityBot) por semana | 5 (OAI-SearchBot, só 09/11) | crescer semana a semana | `pageviews.robo` |
| Sites que citam ou incorporam o relatório de dados | 0 | 5 | `alvos-link.csv` + Search Console (links) |

As metas são estimativas a partir da curva atual (tráfego de pessoas subiu de 344 para 7.114 páginas vistas por semana em 3 semanas), não promessas.

## 7. Riscos e fora do escopo

- **Troca de títulos em ~10 mil páginas:** a palavra-chave e a contagem continuam no começo, e o H1 manteve a frase completa. Mesmo assim, o Google pode reordenar por algumas semanas. Acompanhar as entradas das programáticas na `/admin/trafego`.
- **Velocidade medida em laboratório:** os números de campo (usuários reais) só estão no Search Console.
- **A pesquisa de SERP** usou um índice que não é o Google Brasil: serve para formato e concorrência, não para posição.
- **Queda de ~40 s em 09/11 (11:48):** um erro de sintaxe meu foi publicado porque o commit não esperou os testes. Corrigido em 80 s; desde então o deploy tem healthcheck no `/health` (versão que não sobe não substitui a que está no ar), espera o CI passar ("Wait for CI") e os módulos são conferidos em Python 3.10, a versão do container.
- **Relatório de dados depende do PC:** a base completa (26,2 mi) está no índice local; se o PC ficar desligado na virada do mês, o relatório fica com os números do mês anterior até a próxima atualização.
- **Sócios (8,6 mi) estão só no índice local:** uma ferramenta pública de "sócios pelo CNPJ" exigiria subir esses dados para o banco (custo de armazenamento). Fica para decisão.
