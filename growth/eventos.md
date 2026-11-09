# Eventos do funil (Fase 1 do Prompt 2)

Tudo é gravado **no servidor**, na tabela `eventos` do Postgres do app (padrão do portfólio: tabela espelho local, migrável por `INSERT ... SELECT`). Destinos externos (PostHog, GA4) só entram como cópia adicional, com consentimento.

| Evento | Quando nasce | Onde | Propriedades |
|---|---|---|---|
| `cta_clicked` | clique em botão de cadastro ou `[data-cta]` | `cta_cliques` (tabela própria, desde out/2026) | `path`, `cta` (ex.: `pseo-topo`), `destino`, `utm_*` |
| `signup_completed` | conta criada em `/cadastro` | `eventos` | `alvo`, `cidade` (vindos da página de empresas), `utm_source`, `entrada` (página do 1º toque), `origem` (domínio do 1º toque) |
| `aha_reached` | 1º lead com telefone ou e-mail no painel (verificado a cada hora) | `eventos` + `users.aha_em` | `horas_ate_aha` |
| `paywall_viewed` | modal de planos aberto no painel (único evento aceito do navegador) | `eventos` | `origem` |
| `checkout_started` | Pix gerado, cartão enviado ou checkout do MP criado | `eventos` | `plano`, `metodo` (`pix`, `cartao`, `checkout_mp`) |
| `payment_succeeded` | pagamento conferido **no Mercado Pago** e plano liberado (uma vez por pagamento) | `eventos` + `pagamentos.aplicado_em` | `plano`, `valor`, `metodo`, `payment_id` |

A compra **nunca** nasce do navegador: `/api/t/evento` só aceita `paywall_viewed`.

## Atribuição

- `tv_ft` (primeiro toque) e `tv_lt` (último toque externo): cookies próprios, `HttpOnly`, 90 dias, com página de entrada, domínio de origem e utm. Sem IP, sem identificador pessoal.
- No cadastro viram `users.first_touch` e `users.last_touch`. Toda compra herda pela `user_id`: receita por página de entrada orgânica = `pagamentos` aplicados × `users.first_touch->>'lp'`.
- Respeito ao banner: o banner espelha a escolha em `tv_consent`; com `rejected`, nada é gravado e os cookies existentes são apagados. Base legal e texto da política de privacidade: **TODO-VALIDAR** (revisão jurídica).

## Consultas úteis

```sql
-- funil da semana
SELECT nome, COUNT(*) FROM eventos WHERE criado_em > now() - interval '7 days' GROUP BY 1;
-- receita por página de entrada (1º toque)
SELECT u.first_touch->>'lp' AS entrada, COUNT(*) AS compras, SUM(p.valor) AS receita
FROM pagamentos p JOIN users u ON u.id = p.user_id
WHERE p.aplicado_em IS NOT NULL GROUP BY 1 ORDER BY receita DESC;
```
