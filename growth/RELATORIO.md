# Relatório do motor de visibilidade orgânica — TurboVenda

Atualizado em 09/11/2026. Fases 0 e 1 concluídas e em produção; Fases 2 a 6 pendentes (ver seção 5).

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

<!-- POS-ICONES -->

## 3. TODO-VALIDAR (depende de você)

1. **CNPJ da empresa dona da marca** e **perfis oficiais** (LinkedIn, Instagram, YouTube…). Entram no JSON-LD pelas variáveis `MARCA_CNPJ` e `MARCA_PERFIS` (URLs separadas por espaço) no Railway; vazias, não aparecem.
2. **Crawlers só de treino** (CCBot, Bytespider, Applebot-Extended, meta-externalagent): hoje liberados pelo `*`. Decidir se bloqueia.
3. **Texto do `/llms.txt`**: diz "Starter: 500 leads/mês", enquanto o checkout diz "até 500 leads". Confirmar qual vale antes da Fase 3.

## 4. Ações manuais (só você pode fazer), em ordem de prioridade

1. **Bing Webmaster Tools** (10 min): bing.com/webmasters → entrar → *Importar do Google Search Console*. O Bing trouxe só 45 visitas em 3 semanas e é o índice usado pelo ChatGPT Search e pelo Copilot. O IndexNow já envia tudo; falta a conta para ver o resultado.
2. **Search Console → Configurações → Estatísticas de rastreamento** (5 min): ver se o Googlebot vinha recebendo 429 antes de 08/11 e se a curva de rastreio sobe agora.
3. **Acesso do Search Console por API** (15 min, necessário para a Fase 6): criar uma conta de serviço no Google Cloud e adicioná-la como usuária (leitura) da propriedade; me passar o JSON da chave por variável de ambiente.
4. **DNS sem www** (30 min): `turbovenda.com.br` ainda não resolve. Passo a passo no README de tráfego (`docs/trafego/README.md`).
5. **Railway → serviço → Settings → "Wait for CI"**: com isso o deploy só acontece se os testes (inclusive os de SEO) passarem.
6. **Perfis em B2B Stack, GetApp, Capterra e SaaSHub**: são as fontes que mais aparecem quando se pergunta "melhor ferramenta de prospecção B2B". Textos prontos virão na Fase 5.

## 5. O que falta (Fases 2 a 6)

| Fase | Situação | Próximo passo |
|---|---|---|
| 2 — Conteúdo e programático | Limiar com noindex já existia; base do Postgres é de ~jul/2026 (abertura mais recente: 14/06) | Atualizar a base de produção para out/2026, dado único por página (abertas no último mês, ranking), motor de links internos, briefs, páginas Sobre e autor |
| 3 — GEO | `llms.txt` existe; robots liberado | `llms-full.txt`, resposta direta de 40–60 palavras nas páginas de conteúdo, `growth/entidade.md`, monitor de crawlers de IA (a tabela de visitas não guarda user-agent), painel de share of voice |
| 4 — Ativos que ganham link | 3 ferramentas já existem | Resultado compartilhável por URL, relatório de dados com embed, kit de imprensa, `alvos-link.csv` |
| 5 — Distribuição | Textos de LinkedIn, diretórios e grupos já existem em `docs/trafego/` | Pipeline de rascunhos por página nova, checklist de diretórios com status, mapa de comunidades, páginas de vídeo |
| 6 — Medição | Telemetria própria (`pageviews`, `cta_cliques`) e `/admin/trafego` | Ingestão diária do GSC e do Bing (depende da ação 3), painel por cluster, relatório semanal |

## 6. Linha de base e meta de 90 dias

| Métrica | Linha de base | Meta 90 dias (até 07/02/2027) | Fonte |
|---|---|---|---|
| Entradas orgânicas Google por semana | ~1.200 (3.680 em 3 semanas) | 3.000 | `pageviews` |
| Entradas vindas do Bing por semana | ~15 | 150 | `pageviews` |
| Entradas e cadastros vindos de IA (ChatGPT, Perplexity, Copilot) | 57 entradas e 10 cadastros em 3 semanas | 300 entradas e 40 cadastros por trimestre | `pageviews`, `users.utm_source` |
| Cadastros por semana | ~10 | 25 | `users` |
| Títulos > 60 / descrições > 155 no crawl | 0 / 0 | manter 0 | `crawl.py` |
| LCP mobile de laboratório nas 10 páginas | 1,2–2,8 s | todas < 2,5 s | Lighthouse diário |
| Páginas indexadas / enviadas | sem acesso | ≥ 70% | Search Console (ação 3) |

As metas são estimativas a partir da curva atual (tráfego de pessoas subiu de 344 para 7.114 páginas vistas por semana em 3 semanas), não promessas.

## 7. Riscos e fora do escopo

- **Troca de títulos em ~10 mil páginas:** a palavra-chave e a contagem continuam no começo, e o H1 manteve a frase completa. Mesmo assim, o Google pode reordenar por algumas semanas. Acompanhar as entradas das programáticas na `/admin/trafego`.
- **Velocidade medida em laboratório:** os números de campo (usuários reais) só estão no Search Console.
- **A pesquisa de SERP** usou um índice que não é o Google Brasil: serve para formato e concorrência, não para posição.
- **Sócios (8,6 mi) estão só no índice local:** uma ferramenta pública de "sócios pelo CNPJ" exigiria subir esses dados para o banco (custo de armazenamento). Fica para decisão.
