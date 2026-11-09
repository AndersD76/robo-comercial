# Diagnóstico do funil — do visitante orgânico à compra (Fase 0, Prompt 2)

Levantado em 09/11/2026 a partir do código, do banco de produção (só agregados) e do Search Console.

## Contexto (preenchido a partir do repositório)

| Item | Valor |
|---|---|
| App | TurboVenda — https://www.turbovenda.com.br |
| Modelo de venda | self-service, teste grátis de 14 dias com até 50 leads com contato, sem cartão |
| Planos | Starter R$ 97/mês (500 leads nos últimos 30 dias); Pro R$ 297/mês (ilimitado, WhatsApp, sequências). Sem plano anual |
| Pagamento | Mercado Pago (Pix e cartão no painel; checkout do MP pelo `/api/checkout`). Boleto removido em 09/11 a pedido do dono |
| Momento aha | primeiro lead com telefone ou e-mail aparecendo no painel |
| Canal do ICP | e-mail (Resend) e WhatsApp |

## Funil real (código)

```
Google / ChatGPT / direto
  → página de entrada (94% dos cliques do Google: /empresas/<segmento>/<cidade>)
  → botão (data-cta pseo-topo | pseo-tabela | pseo-rodape)          [cta_cliques]
  → /cadastro (empresa*, site, segmento, região, e-mail*, senha*)    [users, utm_*]
  → /configurar
  → robô liga sozinho quando há termos ou descrição                 [_ligar_robo_primeira_vez]
  → aha: 1º lead com contato                                         [<schema>.empresas]
  → e-mails do teste (leads, cota, 2 dias, acabou)                   [emails_funil.py]
  → modal de upgrade no painel ou /assinar → Pix | cartão | checkout MP
  → pagamento confirmado no MP → plano 30 dias                        [pagamentos]
  → (não há renovação automática nem aviso de vencimento)
```

## Números (produção)

| Etapa | Período | Valor | Fonte |
|---|---|---|---|
| Cliques do Google | 28 dias até 07/11 | 1.399 (78.513 aparições, posição média 9,3) | Search Console |
| … nas páginas segmento × cidade | idem | 1.270 (91%) | Search Console |
| Cliques em botão de cadastro | 28 dias | 147 (home 54, /empresas 46, ferramentas 42) | `cta_cliques` |
| Cadastros | 60 dias | 43 (origem: sem utm 15, pseo 9, ChatGPT 9, site 7) | `users` |
| Robô rodou | idem | 19 de 43 (44%) | `<schema>.logs` |
| Aha (≥ 1 lead com contato) | idem | 17 de 43 (40%) | `<schema>.empresas` |
| Pagamento iniciado (Pix/cartão gerado) | desde sempre | **0** | `pagamentos` |
| Pagantes | desde sempre | 0 pagamentos registrados (3 contas com plano pago marcado à mão) | `users`, `pagamentos` |

## Fricções, por ICE (impacto × confiança × facilidade, 1–10)

| # | Fricção | I | C | F | ICE | Situação |
|---|---|---|---|---|---|---|
| 1 | **Pagamento não confirmava**: sem `MP_WEBHOOK_SECRET` o webhook recusa tudo; Pix pago nunca liberava o plano; a volta do checkout dizia "plano ativo" sem conferir | 10 | 10 | 8 | 800 | **corrigido 09/11** (conferência no MP, conciliação, liberação única) |
| 2 | Páginas segmento × cidade falam com quem procura fornecedor, não com quem vende | 8 | 7 | 9 | 504 | **corrigido 09/11** (chamada a quem vende + robô já mirado); medir por `data-cta` |
| 3 | 56% dos cadastros não fazem o robô rodar: sem "segmento" no cadastro (opcional) o robô não liga até salvar a configuração | 9 | 8 | 6 | 432 | Fase 3 |
| 4 | Ninguém abriu o pagamento: a oferta paga só aparece no modal do painel e nos e-mails; não há oferta no momento do aha nem quando a cota de 50 acaba dentro do painel | 9 | 6 | 7 | 378 | Fase 4 |
| 5 | Sem renovação: o plano vence em 30 dias sem cobrança recorrente nem aviso | 8 | 9 | 5 | 360 | Fase 4/5 |
| 6 | Cadastro com 6 campos e sem "Entrar com Google" (`GOOGLE_CLIENT_ID/SECRET` ausentes) | 6 | 7 | 7 | 294 | Fase 3 |
| 7 | Sem plano anual | 5 | 6 | 8 | 240 | Fase 4 |
| 8 | Prova social: nenhum depoimento ou caso real publicado | 6 | 5 | 4 | 120 | TODO-VALIDAR (só com cliente real e autorização) |

## Lacunas de medição

- `checkout_started` e `purchase` só existem no navegador (`gtag`), e o GA4 não está configurado (`GA_MEASUREMENT_ID` ausente): esses eventos se perdem. A compra agora nasce no servidor (`pagamentos`, conferida no MP), mas não há tabela de eventos do funil.
- Atribuição: só `utm_*` no usuário. Falta first-touch completo (página de entrada, referrer, consulta) e o vínculo pagamento → página de entrada orgânica.
- Aha sem data: dá para calcular (primeiro lead), mas não há evento `aha_reached` nem tempo até o aha.
- Telemetria de páginas inflada até 09/11 pelo pré-carregamento do Chrome (corrigido; ver `growth/RELATORIO.md`).

## Próximas fases (ordem)

1. Fase 1: tabela `eventos` (objeto_ação) no servidor + first-touch no primeiro acesso + vínculo com cadastro e pagamento.
2. Fase 4 antes da 2/3 no que toca dinheiro: oferta no momento de valor (cota acabando, aha), aviso de vencimento e renovação em 1 clique.
3. Fase 3: robô ligado para todo cadastro (perguntar "para quem você vende" e gerar termos), Google One Tap.
