# HANDOFF — /exposicao (2026-06-07)

## O que foi implementado (in-code)
- [x] robots.txt com diretivas AI bots (GPTBot, ClaudeBot, PerplexityBot, Google-Extended)
- [x] sitemap.xml com `<lastmod>` + novas paginas (precos, termos, privacidade)
- [x] /llms.txt completo (descricao, funcionalidades, planos, links)
- [x] IndexNow key route (/b4f7e2a1c9d84f6e8a3b5c7d9e1f0a2b.txt)
- [x] /manifest.json (PWA ready)
- [x] /.well-known/security.txt
- [x] Pagina /termos com conteudo LGPD-compliant
- [x] Pagina /privacidade com tabela de dados, direitos LGPD Art.18
- [x] Pagina /precos com 3 planos + FAQ + schema BreadcrumbList
- [x] Favicon SVG em TODOS os 12 templates
- [x] og-image.png (1200x630) gerada e salva em /static/
- [x] OG tags com imagem em blog.html e blog_post.html
- [x] BreadcrumbList JSON-LD nos blog posts
- [x] Article schema enriquecido (dateModified, publisher.logo, image)
- [x] WebSite + SearchAction schema na landing
- [x] Canonical URLs em login.html e register.html
- [x] Links Termos/Privacidade corrigidos no register.html (era #)
- [x] Nav "Planos" aponta para /precos (era ancora interna)
- [x] Footer com links para /precos, /blog, /termos, /privacidade
- [x] noindex em admin.html, config.html, index.html (dashboard)

---

## HANDOFF — o que VOCE precisa fazer

### Google Search Console (GSC)
- [ ] Acessar https://search.google.com/search-console
- [ ] Adicionar propriedade: `https://turbovenda.com.br`
- [ ] Verificar via meta tag OU DNS TXT (recomendo DNS)
- [ ] Submeter sitemap: `https://turbovenda.com.br/sitemap.xml`

### Bing Webmaster
- [ ] Acessar https://www.bing.com/webmasters
- [ ] Importar do GSC ou verificar manualmente
- [ ] Submeter sitemap

### IndexNow (Bing/Yandex)
- [ ] Apos deploy, chamar:
```
POST https://api.indexnow.org/indexnow
Content-Type: application/json

{
  "host": "turbovenda.com.br",
  "key": "b4f7e2a1c9d84f6e8a3b5c7d9e1f0a2b",
  "urlList": [
    "https://turbovenda.com.br/",
    "https://turbovenda.com.br/precos",
    "https://turbovenda.com.br/blog",
    "https://turbovenda.com.br/termos",
    "https://turbovenda.com.br/privacidade"
  ]
}
```

### DNS — SPF/DKIM/DMARC (para e-mails de suporte@turbovenda.com.br)
- [ ] Adicionar TXT record SPF: `v=spf1 include:resend.com ~all`
- [ ] Configurar DKIM via painel Resend (dominio turbovenda.com.br)
- [ ] Adicionar TXT record DMARC: `v=DMARC1; p=quarantine; rua=mailto:suporte@turbovenda.com.br`

### OG Image (ja gerada, apenas verificar)
- [ ] Apos deploy, testar em: https://developers.facebook.com/tools/debug/
- [ ] Colar URL `https://turbovenda.com.br/` e verificar preview
- [ ] Testar tambem: https://cards-dev.twitter.com/validator

### PWA Icons (opcional, melhora mobile)
- [ ] Gerar icon-192.png e icon-512.png (logo ⚡ sobre fundo #6366f1)
- [ ] Salvar em /static/icon-192.png e /static/icon-512.png
- [ ] O manifest.json ja referencia esses caminhos

### GA4 — Conversao server-side (M5, opcional pra tracao)
- [ ] No GA4, ir em Admin > Data Streams > Measurement Protocol API secrets
- [ ] Gerar um secret
- [ ] Para rastrear sign_up confirmado (server-side), implementar POST para:
  `https://www.google-analytics.com/mp/collect?measurement_id=G-NGSNSF3SPM&api_secret=SEU_SECRET`
  (tarefa futura, nao bloqueia nada agora)

### Railway (N/A — nenhuma env var nova necessaria)
As rotas novas sao estaticas, nao exigem segredos.

---

## Proximos passos (T3 Amplificacao — quando pronto)
1. Listar TurboVenda em diretorios SaaS: ProductHunt, AppSumo, Capterra BR, B2B Stack
2. Configurar Google Ads (keyword: "prospeccao b2b", "crm para vendas")
3. Criar perfil no LinkedIn Company Page + posts semanais
4. Digital PR: publicar pesquisa original (ex: "Estado da prospeccao B2B no Brasil 2026")
