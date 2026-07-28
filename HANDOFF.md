# HANDOFF — TurboVenda Auditoria Completa (2026-07-28)

> Tudo que **voce (humano)** precisa configurar manualmente apos este deploy.
> Itens marcados N/A nao se aplicam a este app.

---

## Railway / Render / Fly (hosting)

| Variavel | Valor / Acao | Status |
|---|---|---|
| `SECRET_KEY` | Gerar com `python -c "import secrets;print(secrets.token_hex(32))"` e colar como variavel de ambiente. **OBRIGATORIO** — app agora faz `sys.exit(1)` se nao estiver definido em producao. | **ACAO NECESSARIA** |
| `MP_PUBLIC_KEY` | Chave publica do Mercado Pago (comeca com `APP_USR-` ou `TEST-`). Necessaria para tokenizacao de cartao no frontend via MercadoPago.js. Pegar em: Mercado Pago > Suas integracoes > Credenciais. | **ACAO NECESSARIA** |
| `MP_WEBHOOK_SECRET` | Ja configurado (webhook rejeita sem ele). Confirmar que esta definido. | Verificar |
| `MP_ACCESS_TOKEN` | Ja configurado. Sem mudanca. | OK |
| `DATABASE_URL` | Ja configurado. Sem mudanca. | OK |
| `FERNET_KEY` | Ja configurado. Sem mudanca. | OK |

### Pos-deploy: migracao de banco

O app roda as migracoes automaticamente no startup, mas estas mudancas precisam de atencao:

1. **UNIQUE index em `pagamentos.mp_payment_id`** — criado automaticamente via `CREATE UNIQUE INDEX IF NOT EXISTS`. Se houver duplicatas pre-existentes, o index vai falhar silenciosamente e o log mostrara o erro. Nesse caso:
   ```sql
   -- Encontrar duplicatas
   SELECT mp_payment_id, COUNT(*) FROM pagamentos GROUP BY mp_payment_id HAVING COUNT(*) > 1;
   -- Remover duplicatas mantendo o mais recente
   DELETE FROM pagamentos a USING pagamentos b
   WHERE a.id < b.id AND a.mp_payment_id = b.mp_payment_id;
   -- Recriar index
   CREATE UNIQUE INDEX idx_pagamentos_mp_id ON pagamentos (mp_payment_id);
   ```

2. **Indexes nos schemas de usuario** (`empresas.email_track_token`, `empresas.agenda_token`, `empresas.status`, `contatos(empresa_id, decisor)`, `sequencia_leads(proximo_envio)`) — criados automaticamente na proxima vez que cada user schema for inicializado.

---

## DNS

N/A — sem mudancas de DNS neste release.

---

## Google Search Console

| Item | Acao | Status |
|---|---|---|
| Verificacao GSC | Ja presente em todos os templates. Sem mudanca. | OK |
| Resubmeter sitemap | Apos deploy, submeter `https://www.turbovenda.com.br/sitemap.xml` novamente — foram adicionados `/empresas` e `/empresas/sobre-os-dados`. | **ACAO RECOMENDADA** |

---

## Google Analytics (GA4)

| Item | Acao | Status |
|---|---|---|
| Measurement ID | Todos os templates agora usam `{{ ga_id }}` via variavel do servidor. Nenhum mais tem ID hardcoded. | OK |
| Consent mode | GA4 so carrega com `cookie_consent === 'accepted'` no `localStorage`. Banner na landing.html. | OK |

---

## Mercado Pago

| Item | Acao | Status |
|---|---|---|
| `MP_PUBLIC_KEY` | **CONFIGURAR** como variavel de ambiente. Sem ela, pagamento por cartao mostra "indisponivel". PIX e boleto continuam funcionando. | **ACAO NECESSARIA** |
| Frontend cartao | Agora usa MercadoPago.js SDK para tokenizar no browser. Dados de cartao nunca mais transitam pelo servidor. | Mudanca PCI-DSS |
| Webhook | Usa `INSERT ON CONFLICT` — pagamentos duplicados nao sao mais inseridos. Retorna 500 em caso de excecao (antes retornava 200). | OK |
| PIX/Boleto | Ativam o plano imediatamente quando status == 'approved'. | OK |

---

## Email / Resend

N/A — sem mudancas. API keys preservadas no save_config (nao mais sobrescritas com vazio).

---

## Segredos / LGPD

| Item | Acao | Status |
|---|---|---|
| Cookie consent banner | Adicionado na landing.html. Respeita localStorage. | OK |
| GA4 consent-gated | Todos os 20 templates condicionam GA4 ao consent. | OK |
| Politica de Privacidade | Acentuacao corrigida, tabela de bases legais presente. | OK |

---

## Mudancas aplicadas automaticamente (sem configuracao manual)

### Seguranca (Fase 2A)
- [x] `SECRET_KEY` obrigatorio em producao (sys.exit se ausente)
- [x] PCI-DSS: cartao tokenizado no browser via MercadoPago.js
- [x] Connection pooling (ThreadedConnectionPool, 2-10 conexoes)
- [x] Config merge: API keys preservadas quando frontend envia vazio
- [x] DB indexes: 5 indexes adicionados nos schemas de usuario
- [x] UNIQUE constraint em `pagamentos.mp_payment_id`
- [x] `TEMPLATES_AUTO_RELOAD = False` e `SEND_FILE_MAX_AGE_DEFAULT = 300` em producao

### Integridade funcional (Fase 2B)
- [x] Expiracao de plano verificada para TODOS os planos (nao so trial)
- [x] PIX e boleto ativam plano quando status == 'approved'
- [x] Webhook retorna 500 em excecao (antes retornava 200)
- [x] Webhook usa `_conn()` ao inves de `psycopg2.connect()` direto
- [x] Idempotency keys sem timestamp
- [x] Funcao `_init_public_schema` unificada (removida duplicata)
- [x] Error handler 500 agora renderiza `500.html` (antes usava 404.html)

### Templates e UX (Fase 2C)
- [x] Acentuacao corrigida em 8 templates
- [x] OG tags adicionadas: login, register, termos, privacidade, empresas_sobre
- [x] GA4 consent-gated em todos os 20 templates
- [x] GA IDs hardcoded removidos (config, register, dashboard, trial_expirado)
- [x] Skip-links adicionados em 5 templates
- [x] Preconnect fonts.gstatic.com adicionado a 12 templates
- [x] `rel="noopener"` adicionado a target="_blank" em config, dashboard
- [x] Duplicate Font Awesome removido de agendar.html
- [x] aggregateRating removido da landing (sem dados reais)
- [x] `robots.txt` — Disallow para /trial-expirado, /pagamento/, /t/
- [x] Sitemap — /empresas e /empresas/sobre-os-dados
- [x] Health check — verifica DB (retorna 503 se down)
- [x] Template `500.html` criado

---

## Itens agora resolvidos (Fase 3)

- [x] CI/CD: `.github/workflows/ci.yml` com syntax check + pytest + template validation
- [x] Testes: 14 testes de seguranca + 31 testes de rotas (45 total)
- [x] LGPD: `/api/meus-dados/exportar` (GET) e `/api/meus-dados/excluir` (POST)
- [x] Cookie consent global: `cookie_banner.html` incluido em todos os 20 templates
- [x] Rate limiting: PIX, cartao, boleto (5/min), webhook (30/min), exclusao (3/hora)
- [x] Logging estruturado: JSON format, `print()` convertido para `logger.*`
- [x] Monitoramento: Sentry SDK integrado (definir `SENTRY_DSN` para ativar)

## Unico item pendente

| Item | Acao | Quem |
|---|---|---|
| `SENTRY_DSN` | Criar projeto em sentry.io > copiar DSN > adicionar como variavel no Railway | Voce |
| Backup Neon | Verificar politica de retencao em neon.tech > Settings > Backups | Voce |
