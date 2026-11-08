# Diagnóstico de visibilidade orgânica — TurboVenda (Fase 0)

Data: 08/11/2026. Método: leitura do repositório, crawl próprio simulando o Googlebot mobile (`growth/ferramentas/crawl.py`), Lighthouse 12.6.1 mobile em 10 páginas, testes de redirect/404 com `curl`, telemetria de tráfego do próprio banco (`pageviews`, `cta_cliques`, `users`) e pesquisa de SERP em 20 buscas do ICP. Nenhum código do app foi alterado nesta fase.

## 1. Contexto (preenchido a partir do repositório)

O bloco CONTEXTO do prompt veio em branco. Preenchi com o que o código e `docs/trafego/contexto.md` (out/2026) mostram; o que depende de você está marcado **TODO-VALIDAR**.

| Campo | Valor |
|---|---|
| App | TurboVenda |
| URL de produção | https://www.turbovenda.com.br (o domínio sem www não tem DNS) |
| O que resolve | Encontra empresas para o cliente vender (buscadores + base da Receita), coleta telefone, e-mail e decisor, e faz a abordagem por WhatsApp e e-mail com IA |
| ICP | Dono/sócio ou gerente comercial de PME B2B com 2–50 funcionários e sem pré-vendas; indústria, distribuidoras, serviços B2B, representantes. Sul primeiro (RS, SC, PR), depois Brasil |
| Oferta | Grátis com 50 leads sem cartão (14 dias), Starter R$ 97/mês (até 500 leads), Pro R$ 297/mês; pagamento por PIX, cartão ou boleto |
| Conversão principal | `/cadastro` |
| Concorrentes | Econodata, Speedio, Leads2b, Apollo (já há comparativos em `/alternativas`) |
| Dado próprio | Base da Receita: 6,7 mi CNPJs ativos no Postgres (páginas `/empresas`) e índice local de 26,2 mi empresas com 8,6 mi sócios (só no PC do operador) |
| Search Console | Propriedade existe (pedidos de indexação feitos em out/2026); **sem acesso por API** daqui |
| Bing Webmaster | **TODO-VALIDAR**: só 45 entradas vindas do Bing em 3 semanas sugerem que não foi configurado |
| Domínio verificado | Sim no Google (propriedade usada em out/2026); Resend também verificado |
| CNPJ, endereço e perfis oficiais da marca | **TODO-VALIDAR**: não existem no código; necessários para `Organization` e página Sobre |

## 2. Resumo executivo

- **O SEO técnico está bom na base** (renderização no servidor, canonical em tudo, 404 reais, limiar de conteúdo nas programáticas, IndexNow, Lighthouse SEO 100). Não é caso de reescrever nada.
- **As páginas programáticas são o motor:** 3.242 das ~3.700 entradas vindas do Google caíram em segmento × cidade, e o tráfego de pessoas subiu de 344 para 7.114 páginas vistas por semana desde 17/10. Os cadastros foram de ~3 para ~10 por semana.
- **Risco nº 1:** o limitador de taxa devolve 429 a quem rastreia rápido, inclusive nas 10 mil páginas públicas. Para o Googlebot isso significa rastreio mais lento e páginas caindo do índice.
- **Oportunidade nº 1 em IA:** o ChatGPT já trouxe 10 cadastros, mas o Bing (índice usado por ChatGPT Search e Copilot) quase não manda ninguém: 45 entradas. Configurar o Bing Webmaster e entrar em B2B Stack/GetApp/Capterra é barato.
- **Velocidade:** LCP mobile de 2,9–3,5 s por causa de CSS de fonte e ícones bloqueando a pintura; corrigível em uma tarde.
- **CTR:** títulos das programáticas com média de 85 caracteres (o Google mostra ~60).
- **Confiança (E-E-A-T):** não há página Sobre, autor, CNPJ nem perfis oficiais ligados à marca. Depende de dados seus (TODO-VALIDAR).
- **Medição:** sem acesso ao Search Console por API, não há consultas, CTR nem posição. É a primeira ação manual.
- **Quem disputa as buscas** é EmpresAqui, CNPJ.biz e diretórios baratos, mais do que Econodata/Speedio. Ganha quem tem dado único por página.

## 3. Rotas públicas e classificação

| Rota | Quantidade | Classificação | Observação |
|---|---|---|---|
| `/` | 1 | indexável | SoftwareApplication + Organization + WebSite + FAQPage |
| `/precos` | 1 | indexável | |
| `/cadastro` | 1 | indexável, **thin** (105 palavras) e **sem H1** | variações com UTM têm canonical correto para `/cadastro` |
| `/blog`, `/blog/<slug>` | 1 + 30 | indexável | `/blog` sem JSON-LD; títulos de post com média de 78 caracteres |
| `/para/<slug>` | 6 | indexável | ~430 palavras |
| `/alternativas`, `/alternativas/<slug>` | 1 + 4 | indexável | |
| `/ferramentas`, `/ferramentas/*` | 1 + 3 | indexável | com parâmetros (`?cidade=`) → `noindex` + canonical para a base (correto) |
| `/empresas` | 1 | indexável | hub |
| `/empresas/<cnae>` | ~1.300 | indexável | 4 linkadas e indexáveis ficaram **fora do sitemap** (`abate-de-aves`, `frigorificos`, `oleos-vegetais`, `produtos-quimicos`) |
| `/empresas/<cnae>/estado/<uf>` | 666 | indexável | |
| `/empresas/<cnae>/<cidade>` | ~8.300 | indexável com ≥ 15 empresas; `noindex` com 8–14; 404 com < 8 | já cumpre o "limiar mínimo" da Fase 2 |
| `/empresas/cidade/<cidade>` | 1.135 | indexável | |
| `?pagina=N` nas listas | — | `noindex, follow` + canonical para a página 1 | sinal misturado: canonical para a página 1 não é recomendado em paginação |
| `/empresas/sobre-os-dados`, `/privacidade`, `/termos` | 3 | indexável | |
| `/login` | 1 | `noindex, follow` (correto) | |
| `/empresas/busca` | — | redireciona (correto: busca interna fora do índice) | |
| Área logada (`/dashboard`, `/configurar`, `/api/`, `/admin/`, `/assinar`, `/pagamento/`, `/t/`) | — | bloqueada no robots.txt (correto) | |
| `/llms.txt` | 1 | publicado | `/llms-full.txt` não existe |

Não há página **Sobre**, **página de autor**, **política editorial**, **kit de imprensa** nem **páginas de vídeo**.

## 4. Crawl (Googlebot mobile, 450 URLs)

Sementes: as 53 URLs de `sitemap-pages.xml`, 50 URLs sorteadas de cada `sitemap-empresas-N.xml` e os links achados nas páginas fixas. Dados brutos em `growth/dados/crawl.csv` e `growth/dados/crawl-resumo.json`.

| Verificação | Resultado |
|---|---|
| Status | 408 × 200, **41 × 429**, 1 erro do próprio crawler (link `mailto:`, já corrigido no script) |
| Páginas indexáveis no crawl | 342 |
| Sem title / sem description / sem canonical | 0 / 0 / 0 |
| **Title acima de 60 caracteres** | **314 de 408** (programáticas segmento × cidade: média 85, máx. 120; blog: média 78) |
| **Description acima de 155** | **221 de 408** |
| Title/description duplicados | 56, todos explicados: 29 variações de `/cadastro` com UTM (canonical correto), páginas `?pagina=N` (noindex) e ferramenta com parâmetros (noindex) |
| H1 ausente | 30 (todas variações de `/cadastro`) |
| H1 múltiplo | 0 |
| Thin (< 250 palavras) | 32 (`/cadastro` e variações, `/login`); programáticas têm mediana de 898 palavras |
| JSON-LD | presente em 373; ausente em `/blog`, `/cadastro`; nenhum JSON inválido |
| FAQPage | 286 páginas; conferido que as perguntas do schema aparecem no texto visível |
| `twitter:card` ausente | 88 (alternativas, ferramentas, para, cadastro…) |
| `og:image` ausente | 3 |
| hreflang | nenhum — site só em pt-BR, então não é necessário (o Google só usa hreflang entre versões de idioma) |
| Tempo de resposta (HTML) | p50 210 ms, p90 377 ms |

**O 429 é o achado técnico mais sério.** O Flask-Limiter tem limite padrão de 200 requisições por minuto por IP em todas as rotas, inclusive as 10 mil páginas públicas. O crawler a 4 requisições simultâneas bateu no limite. O Googlebot rastreia de poucos IPs e, quando recebe 429, reduz o ritmo; se persistir, URLs saem do índice. A telemetria mostra 200 mil acessos de robôs em 3 semanas, então o volume de rastreio é alto. Não dá para saber daqui quantos 429 o Googlebot já levou (a tabela `pageviews` não guarda status nem user-agent): ver em Search Console → Configurações → Estatísticas de rastreamento.

## 5. robots.txt, sitemap, redirects e erros

| Item | Situação |
|---|---|
| `http://` → `https://` | 301 (ok) |
| `turbovenda.com.br` sem www | **não resolve no DNS** (pendente desde out/2026; ação sua) |
| Domínio `*.up.railway.app` | 404 (ok, não duplica) |
| Barra no final (`/precos/`, `/blog/`) | **404** — deveria ser 301 para a versão sem barra |
| Página inexistente, post inexistente, segmento/cidade inválidos | 404 de verdade (sem soft-404) |
| UTM (`/precos?utm_source=x`) | 200 com canonical para `/precos` (ok) |
| Sitemap index | 4 sitemaps, 10.139 URLs. Páginas fixas com `lastmod` real; as 10 mil programáticas **sem `lastmod`** |
| robots.txt | libera tudo menos área logada; cita GPTBot, ClaudeBot, PerplexityBot e Google-Extended. Não cita OAI-SearchBot, ChatGPT-User, Claude-SearchBot, Bingbot, Applebot (hoje liberados pelo `*`) |
| IndexNow | chave publicada e envio automático a cada deploy (implementado em out/2026); o Bing aceitou 10.139 URLs |

## 6. Performance (Lighthouse mobile, laboratório)

Lighthouse 12.6.1, perfil mobile padrão (4G lento simulado), Chromium 1248. Laboratório, não dado de campo: o relatório de Core Web Vitals do Search Console (dados reais de usuários) não está acessível daqui, e a API pública do PageSpeed Insights esgotou a cota sem chave.

| Página | Perf | SEO | Acess. | LCP | CLS | TBT | INP* | JS (KB) | Peso total (KB) |
|---|---|---|---|---|---|---|---|---|---|
| `/` | 83 | 100 | 86 | 3.4 s | 0.023 | 0 ms | - | 0 | 248 |
| `/precos` | 83 | 100 | 93 | 3.5 s | 0.000 | 0 ms | - | 0 | 231 |
| `/cadastro` | 83 | 100 | 79 | 3.5 s | 0.018 | 0 ms | - | 0 | 230 |
| `/ferramentas/lista-de-empresas` | 90 | 100 | 85 | 2.9 s | 0.007 | 0 ms | - | 0 | 56 |
| `/empresas/cidade/porto-alegre-rs` | 89 | 100 | 84 | 2.9 s | 0.000 | 0 ms | - | 0 | 56 |
| `/empresas/usinagem/caxias-do-sul-rs` | 86 | 100 | 92 | 2.9 s | 0.000 | 192 ms | - | 0 | 57 |
| `/empresas/usinagem` | 90 | 100 | 84 | 2.9 s | 0.010 | 0 ms | - | 0 | 57 |
| `/blog/como-prospectar-clientes-b2b` | 83 | 100 | 86 | 3.5 s | 0.016 | 0 ms | - | 0 | 233 |
| `/alternativas/econodata` | 90 | 100 | 93 | 2.9 s | 0.000 | 0 ms | - | 0 | 57 |
| `/para/industria` | 82 | 100 | 93 | 3.5 s | 0.030 | 0 ms | - | 0 | 227 |

*INP só existe em dado de campo; no laboratório o TBT é o indicador equivalente.

- **SEO 100 em todas.** O problema é velocidade, não marcação.
- **LCP acima da meta (2,5 s) em todas.** O elemento LCP é o próprio H1 (texto), que espera os CSS bloqueantes: Font Awesome inteiro do cdnjs (~1,0 s; 98% das regras sem uso; ~176 KB de fontes de ícone), Inter do Google Fonts com 7 pesos (~0,9 s) e `tokens.css`. Economia estimada pelo Lighthouse: ~1,9 s.
- Páginas com Font Awesome pesam ~230 KB e ficam em 3,4–3,5 s; as que não usam ícones pesam 56 KB e ficam em 2,9 s (ainda presas à fonte do Google).
- CLS ≤ 0,03 e TBT ≈ 0 em todas: nada a corrigir. JavaScript próprio é mínimo.
- Acessibilidade 79–93: `/cadastro` é a pior (79).
- JSON completos em `growth/dados/lighthouse/` (não versionados; regeráveis).

## 7. Dados estruturados

| Página | Tipos | Problema |
|---|---|---|
| Home | Organization, WebSite, SoftwareApplication (ofertas em BRL reais), FAQPage | `Organization.sameAs` vazio, sem `identifier` (CNPJ), logo é a imagem OG (não quadrada) — **TODO-VALIDAR** perfis oficiais e CNPJ |
| Programáticas | BreadcrumbList, ItemList, FAQPage | ok |
| Blog | Article, BreadcrumbList | sem `author` como Person com página própria; `/blog` sem JSON-LD |
| Ferramentas | WebApplication | ok |
| `aggregateRating` | não usado | correto: não há avaliações verificáveis |

## 8. Tráfego atual (telemetria própria, 17/10 a 08/11/2026)

| Semana | Páginas vistas (pessoas) | Entradas | Acessos de robôs |
|---|---|---|---|
| 12/10 (desde 17/10) | 344 | 197 | 18.418 |
| 19/10 | 3.670 | 2.496 | 75.612 |
| 26/10 | 6.096 | 4.740 | 52.809 |
| 02/11 | 7.114 | 4.043 | 54.017 |

Entradas de pessoas por origem: direto 7.489 · **Google 3.680** · **ChatGPT 57** (via `utm_source=chatgpt.com`) · pSEO interno 51 · **Bing 45** · DuckDuckGo 17 · outros ~140.

Entradas por tipo de página (total / vindas de Google ou Bing): segmento × cidade 7.690 / 3.242 · segmento × UF 1.042 / 75 · home 720 / 224 · cidade 467 / 59 · blog 344 / 25 · ferramentas 277 / 53 · alternativas 52 / 2.

Cadastros: de ~3 por semana em set/2026 para **~10 por semana** desde 19/10. Origem marcada: pSEO 14 · **chatgpt.com 10** · site 7 · ferramentas 2 · sem UTM 29.

Leitura: as páginas programáticas são o motor orgânico; o ChatGPT já cita o site e gera cadastro; o Bing quase não traz nada, e várias IAs (ChatGPT Search, Copilot) usam o índice do Bing. Blog, alternativas e ferramentas quase não recebem busca orgânica.

## 9. Search Console

Não há acesso por API daqui (precisa de uma conta de serviço adicionada como usuária da propriedade, ou de um export manual). Por isso esta fase não tem consultas, CTR nem posição. Ação manual na lista do relatório.

## 10. SERPs e respostas de IA (20 buscas do ICP)

Detalhe por busca em `growth/pesquisa-serp.md` e `growth/dados/serp.csv`. **Ressalva de método:** a ferramenta de busca usada consulta um índice dos EUA, não o Google Brasil, e não expõe "As pessoas também perguntam" nem respostas de IA. Ela não mostrou nenhuma página do TurboVenda em `site:`, enquanto a telemetria registra 3.680 entradas vindas do Google — então as **posições não valem como ranking real**; os padrões de formato e de quem compete, sim. Volume e dificuldade são estimativas relativas, não medidas. Confirmar no Search Console antes de priorizar.

O que se repete:

- **Quem disputa de verdade não são os concorrentes conhecidos.** EmpresAqui aparece em 15 das 20 buscas e Agendor em 10 (guias). Econodata aparece em 3, Leads2b em 2; Speedio e Apollo só citados por terceiros. Concorrentes baratos (LeadJet, SocialHub, Disparo em Massa, CNPJ.biz, FarejaLeads, Dados Premium) já fazem páginas por cidade, por CNAE e "alternativa à Econodata".
- **O formato vencedor depende da intenção:** guia nas buscas "como fazer"; diretório programático nas buscas locais; página de produto ou ferramenta em CNAE, base de CNPJ e WhatsApp; comparativo (listicle) em "ferramenta" e "alternativa"; ferramenta interativa entra no top 8 em "modelo de mensagem" e "quantos leads".
- **Vitórias rápidas** (dificuldade baixa e página já existe): segmento × cidade, quantos leads preciso, representante comercial, mailing de empresas grátis, lista de clientes B2B, contato de empresas.
- **Evitar por agora:** "como prospectar clientes", "prospecção ativa", "encontrar clientes" (RD Station, Neil Patel, Agendor) e "consultar sócios" (Cora, Contabilizei, bancos) — este só com uma ferramenta grátis.
- **IA:** como aproximação pela busca web, as fontes que as respostas sobre "melhor ferramenta de prospecção B2B" tendem a usar são B2B Stack, GetApp, Capterra e SaaSHub. Perfil da marca nesses sites é barato e é o caminho mais curto para ser citado. Dado concreto: o ChatGPT já trouxe 57 entradas e 10 cadastros (seção 8).

## 11. Problemas priorizados (impacto × esforço)

| # | Problema | Evidência | Impacto | Esforço | Fase | Quem |
|---|---|---|---|---|---|---|
| 1 | Limite de 200 req/min por IP vale também para as páginas públicas: rastreador recebe **429** | 41 × 429 no crawl a 4 req simultâneas | **Alto** (indexação das 10 mil páginas) | Baixo | 1 | eu |
| 2 | **Bing quase ausente** (45 entradas em 3 semanas); ChatGPT Search e Copilot usam o índice do Bing | telemetria | **Alto** (GEO) | Baixo | 1/3 | você (Bing Webmaster) + eu (conferir IndexNow) |
| 3 | **LCP mobile 3,4–3,5 s** (meta < 2,5 s): Font Awesome inteiro do cdnjs (98% sem uso) e Inter com 7 pesos travam a primeira pintura | Lighthouse | Médio-alto | Baixo | 1 | eu |
| 4 | **Títulos longos** nas programáticas (média 85, máx. 120) e blog (78): cortados no Google, CTR menor | crawl | Médio | Baixo | 1 | eu |
| 5 | Domínio **sem www não resolve** | `curl` | Médio (link digitado sem www se perde) | Baixo | 1 | você (DNS) |
| 6 | **E-E-A-T fraco:** sem página Sobre, autor, CNPJ e perfis oficiais; `Organization.sameAs` vazio | crawl + schema | Médio-alto (confiança para Google e IA) | Médio | 1/2/3 | você (dados) + eu |
| 7 | Barra no final (`/precos/`) dá 404 em vez de 301 | `curl` | Baixo-médio | Baixo | 1 | eu |
| 8 | Programáticas **sem `lastmod`**; 4 hubs de CNAE indexáveis fora do sitemap | sitemap | Médio | Baixo | 1 | eu |
| 9 | Sem acesso ao **Search Console por API**: sem consultas, CTR e posição | — | Alto (medição) | Baixo | 6 | você (conta de serviço) |
| 10 | Telemetria não guarda user-agent nem status: impossível ver crawler de IA ou 429 ao Googlebot | código | Médio | Baixo | 3 | eu |
| 11 | Programáticas sem dado único além da lista (ex.: abertas no último mês, ranking por cidade) | conteúdo | Médio-alto (contra EmpresAqui/CNPJ.biz) | Médio | 2 | eu |
| 12 | Marca ausente de B2B Stack, GetApp, Capterra, SaaSHub | pesquisa | Médio (citação em IA) | Baixo | 3/5 | você (cadastro) + eu (textos) |
| 13 | robots.txt sem os crawlers de busca de IA explícitos; sem `/llms-full.txt` | `curl` | Baixo | Baixo | 1/3 | eu |
| 14 | `twitter:card` ausente em 88 páginas; `/cadastro` sem H1; `/blog` sem JSON-LD | crawl | Baixo | Baixo | 1 | eu |
| 15 | Paginação com canonical para a página 1 junto de `noindex` | crawl | Baixo | Baixo | 1 | eu |
| 16 | Blog, alternativas e ferramentas quase sem busca orgânica (blog: 25 entradas orgânicas em 30 posts) | telemetria | Médio | Médio | 2 | eu |

## 12. O que já está bom e não deve ser mexido

- Renderização 100% no servidor (Flask/Jinja): o conteúdo indexável sai no HTML.
- Limiar de conteúdo nas programáticas (404 < 8, noindex 8–14, index ≥ 15) e 404 real para combinações inválidas.
- Canonical em todas as páginas, UTMs e parâmetros sem duplicata.
- FAQPage só onde a FAQ está visível; nenhum `aggregateRating` inventado.
- IndexNow automático, sitemap index segmentado, `llms.txt`, telemetria própria sem IP (LGPD).
- Tempo de resposta do HTML baixo (p50 210 ms) e compressão ativa.

## 13. Aceite da Fase 0

- [x] Rotas públicas mapeadas e classificadas (seção 3)
- [x] Crawl próprio como Googlebot mobile: status, canonical, robots, title, description, H1, palavras, links, JSON-LD, tempo (seção 4; `growth/ferramentas/crawl.py`)
- [x] Lighthouse mobile nas 10 páginas principais (seção 6)
- [x] robots.txt, sitemap, redirects, 404/soft-404, HTTPS, www, barra final (seção 5)
- [ ] Search Console por API — **sem acesso**; vira ação manual (seção 9)
- [x] SERPs das 20 buscas do ICP, com a ressalva de que a ferramenta não reflete o Google Brasil (seção 10)
- [x] Mapa de intenção em `growth/mapa-intencao.csv`
- [x] Problemas priorizados por impacto × esforço (seção 11)
- [x] Nenhuma alteração no código do app
