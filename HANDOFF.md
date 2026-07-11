# HANDOFF — /exposicao (2026-07-11)

## O que foi implementado (in-code) — Sessão anterior

- [x] robots.txt com diretivas AI bots (GPTBot, ClaudeBot, PerplexityBot, Google-Extended)
- [x] sitemap.xml com `<lastmod>` + novas paginas (precos, termos, privacidade)
- [x] /llms.txt completo (descricao, funcionalidades, planos, links)
- [x] IndexNow key route (/b4f7e2a1c9d84f6e8a3b5c7d9e1f0a2b.txt)
- [x] /manifest.json (PWA ready)
- [x] /.well-known/security.txt
- [x] Pagina /termos com conteudo LGPD-compliant
- [x] Pagina /privacidade com tabela de dados, direitos LGPD Art.18
- [x] Pagina /precos com 3 planos + FAQ + schema BreadcrumbList
- [x] Favicon SVG em TODOS os templates
- [x] og-image.png (1200x630) gerada e salva em /static/
- [x] OG tags com imagem em todas paginas publicas
- [x] BreadcrumbList JSON-LD nos blog posts
- [x] Article schema enriquecido (dateModified, publisher.logo, image)
- [x] WebSite + SearchAction schema na landing
- [x] Canonical URLs em todas as rotas publicas
- [x] noindex em admin, config, dashboard, trial_expirado

## O que foi implementado (in-code) — Sessão atual

- [x] **UTM persistence**: captura utm_source/medium/campaign em localStorage (landing, blog, segmento) → popula hidden fields no cadastro → salvo na tabela `users`
- [x] **Colunas UTM**: ALTER TABLE automático no boot (utm_source, utm_medium, utm_campaign)
- [x] **IndexNow POST**: função `_ping_indexnow()` + rota `POST /admin/indexnow` submete todas URLs ao IndexNow + ping Google sitemap
- [x] **Conteúdo /para/***: expandido de ~50 para ~400+ palavras por segmento (dores do nicho, exemplo de mensagem de prospecção, FAQ única)
- [x] **FAQPage schema**: JSON-LD FAQPage em cada página /para/* (3 perguntas por segmento)
- [x] **Cross-links segmentos**: seção "Outros segmentos atendidos" com links entre as 6 páginas /para/*
- [x] **Blog → /para/***: seção "Prospecção por segmento" em todo blog post com links para as 6 páginas
- [x] **Blog → /precos**: link "Veja planos a partir de R$0" no CTA de cada post
- [x] **Footer landing**: links para as 6 páginas /para/* + links ecossistema (prismabiz, pcmonitor, anderstech, andersdev)
- [x] **twitter:card**: adicionado em precos.html, blog.html, segmento.html (faltava)
- [x] **og:locale + og:site_name**: adicionado em segmento.html (faltava)

---

## HANDOFF — o que VOCÊ precisa fazer

### GA4 (Google Analytics 4) — G-NGSNSF3SPM

| Ação | Onde | Valor |
|------|------|-------|
| Marcar conversões | Admin → Events → Mark as conversion | `sign_up`, `checkout_started`, `click_plan_starter`, `trial_expired` |
| Criar funil | Explore → Funnel | `view_home` → `click_start_free` → `sign_up` → `onboarding_started` → `first_leads_generated` → `checkout_started` |
| Testar eventos | DebugView | Abrir site com `?debug_mode=true` |
| Relatório UTM | Reports → Acquisition | Filtrar por `utm_source` para ver origem dos cadastros |

### Google Search Console

| Ação | Onde | Valor |
|------|------|-------|
| Submeter sitemap | GSC → Sitemaps | `https://www.turbovenda.com.br/sitemap.xml` |
| Solicitar indexação | Inspeção de URL | Inserir cada URL /para/* e clicar "Solicitar indexação" |
| Verificar FAQPage | Rich Results Test | Colar `https://www.turbovenda.com.br/para/agronegocio` |

### IndexNow (pós-deploy)

| Ação | Como |
|------|------|
| Ping automático | `POST /admin/indexnow` (precisa session admin_auth) |
| Alternativa curl | Logar como admin → chamar rota. Ou adaptar auth para API key |

### Bing Webmaster

| Ação | Onde |
|------|------|
| Importar do GSC | https://www.bing.com/webmasters |
| Submeter sitemap | Mesmo URL do GSC |

### DNS — SPF/DKIM/DMARC

| Registro | Valor |
|----------|-------|
| SPF (TXT) | `v=spf1 include:resend.com ~all` |
| DKIM | Configurar via painel Resend |
| DMARC (TXT) | `v=DMARC1; p=quarantine; rua=mailto:suporte@turbovenda.com.br` |

### Mercado Pago (Pagamentos)

| Ação | Onde | Valor |
|------|------|-------|
| Credenciais | Railway env vars | `MP_ACCESS_TOKEN`, `MP_PUBLIC_KEY` |
| Criar planos | Painel MP → Assinaturas | Starter R$97/mês, Pro R$297/mês |

### OG Images (opcional, melhora social sharing)

| Ação | Detalhe |
|------|---------|
| Imagem genérica | `/static/og-image.png` — já existente, verificar se 1200×630 |
| Imagens por segmento (opcional) | Criar `og-agronegocio.png`, `og-industria.png` etc. e atualizar `segmento.html` |
| Testar previews | https://developers.facebook.com/tools/debug/ + https://cards-dev.twitter.com/validator |

### Railway (Deploy)

| Ação | Detalhe |
|------|---------|
| N/A | Nenhuma variável de ambiente nova obrigatória. Colunas UTM adicionadas automaticamente no boot |

---

## Checklist pós-deploy

- [ ] Deploy no Railway
- [ ] Abrir `/para/agronegocio` — conteúdo expandido visível
- [ ] Cadastrar com `?utm_source=teste` — verificar no banco `SELECT utm_source FROM users`
- [ ] GA4 DebugView: evento `sign_up` aparece ao cadastrar
- [ ] GSC: submeter sitemap, solicitar indexação manual das /para/*
- [ ] Rich Results Test: FAQPage válido em `/para/agronegocio`
- [ ] Social: colar URL no validator do Facebook/Twitter
- [ ] POST `/admin/indexnow` — esperar resposta 200/202

---

## Próximos passos (T3 Amplificação)

1. Listar TurboVenda em diretórios SaaS: ProductHunt, AppSumo, Capterra BR, B2B Stack
2. Google Ads: keywords "prospecção b2b", "crm para vendas", "encontrar clientes empresas"
3. LinkedIn Company Page + posts semanais
4. Digital PR: pesquisa original "Estado da Prospecção B2B no Brasil 2026"
5. Programa de indicação (PLG loop) com k-factor tracking
