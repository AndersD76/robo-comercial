# Relatório do motor de conversão — TurboVenda (Prompt 2)

Atualizado em 09/11/2026. Diagnóstico completo em `growth/funil-diagnostico.md`; eventos em `growth/eventos.md`; testes em `growth/experimentos.md`. Painel: `/admin/receita`.

## 1. O que foi implementado

### Fase 0 — Diagnóstico
`growth/funil-diagnostico.md`: funil desenhado a partir do código, números de produção, 8 fricções priorizadas por ICE e lacunas de medição. Achado principal: **o pagamento não confirmava** (sem `MP_WEBHOOK_SECRET` o webhook recusava tudo; Pix pago nunca liberava o plano; a volta do checkout dizia "plano ativo" sem conferir). Em 60 dias: 43 cadastros → 19 com robô rodando → 17 com 1º lead → 0 pagamentos iniciados.

### Fase 1 — Instrumentação e atribuição
| Mudança | Arquivos |
|---|---|
| Tabela `eventos` (objeto_ação) gravada no servidor: `signup_completed`, `aha_reached`, `paywall_viewed`, `checkout_started`, `payment_succeeded`, `experimento_exposto`, `referral_signup`, `email_unsubscribed` | `app.py`, `growth/eventos.md` |
| Primeiro e último toque externo (página de entrada, origem, utm, indicação) em cookies próprios sem dado pessoal; gravados no cadastro (`users.first_touch/last_touch`); compra herda pela conta | `app.py` |
| Banner de cookies espelhado no servidor (`tv_consent`): recusa não grava e apaga | `templates/cookie_banner.html` |
| Momento aha marcado a cada hora (`users.aha_em`, horas até o aha) | `app.py` |
| Contador de visitas não conta mais o pré-carregamento do Chrome (inflava ~2,4×) | `app.py` |

### Fase 2 — Páginas que convertem
| Mudança | Arquivos |
|---|---|
| Páginas segmento × cidade (91% dos cliques do Google) falam com quem vende ("Você vende para construtoras?"), com botão no topo, no meio da tabela e no fim | `templates/empresas_cidade.html` |
| O botão leva segmento e cidade ao cadastro: "Seu robô começa por: Construtoras em Caraguatatuba - SP"; a conta nasce com o robô mirado nessas empresas | `app.py`, `templates/register.html` |
| Preços e rodapé com PIX/cartão via Mercado Pago, "sem fidelidade e sem cobrança automática", aviso antes de vencer, CNPJ e contato | `templates/precos.html`, `templates/_rodape_publico.html` |
| Política de privacidade com os cookies de medição, a recusa e o descadastro | `templates/privacidade.html` |

### Fase 3 — Cadastro e ativação
| Mudança | Arquivos |
|---|---|
| Sem página de origem, o cadastro pede "o que você vende e para quem" (sem isso o robô não ligava para 56% das contas) | `app.py`, `templates/register.html` |
| O robô liga no próprio cadastro quando há alvo ou descrição (antes, só ao abrir o painel) | `app.py` |

### Fase 4 — Monetização e checkout
| Mudança | Arquivos |
|---|---|
| Compra conferida no próprio Mercado Pago (`_mp_consultar`/`_mp_aplicar`), plano liberado uma vez por pagamento (`pagamentos.aplicado_em`), só com valor ≥ ao do plano | `app.py` |
| Tela do Pix confirma sozinha (pergunta a cada 5 s); conciliação a cada 10 min; volta do checkout só diz "aprovado" depois de conferir; webhook funciona sem segredo (aviso é só gatilho) | `app.py`, `templates/dashboard.html` |
| Renovação antecipada não perde dias (antes, pagar antes do vencimento zerava o saldo) | `app.py` |
| Boleto removido (pedido do dono) | `app.py`, `templates/dashboard.html`, `emails_funil.py` |
| Oferta no momento de valor: faixa no painel quando a cota do teste enche, o teste está acabando (com 10+ leads) ou acabou, e quando o plano pago vence | `templates/dashboard.html` |
| Cota do Starter conta 500 leads por 30 dias, como anunciado (antes contava o total da conta) | `app.py` |

### Fase 5 — Lifecycle
| Mudança | Arquivos |
|---|---|
| Aviso 3 dias antes do vencimento e no vencimento, um por ciclo, com renovação em 1 clique | `emails_funil.py` |
| Lembrete único de PIX gerado e não pago | `emails_funil.py` |
| Descadastro em 1 clique (link assinado) nos e-mails de marketing; o aviso de vencimento é transacional | `app.py`, `emails_funil.py` |
| Já existiam: e-mails do teste (10 leads, cota, 2 dias, acabou) e a reativação de 53 contas | `emails_funil.py` |

### Fase 6 — Experimentação
Infraestrutura A/B própria (`EXPERIMENTOS`, `variante()`), estável por visitante, exposição só de pessoa, resultado em `/admin/receita`. **Primeiro teste rodando:** botão do topo das páginas de empresas. Cinco hipóteses com métrica, proteção, ICE e amostra mínima em `growth/experimentos.md`.

### Fase 7 — Loops de aquisição
| Mudança | Arquivos |
|---|---|
| Link de indicação por conta (`/?indica=`), assinado; cadastro grava `users.indicado_por`; aparece no painel depois de 10+ leads | `app.py`, `templates/dashboard.html` |
| Pedido de depoimento 3–30 dias após o 1º lead, publicação só com autorização escrita | `emails_funil.py` |
| Já existiam (Prompt 1): resultado compartilhável da calculadora e da lista de empresas | `templates/ferramenta_*.html` |

### Fase 8 — Painel de receita
`/admin/receita`: funil de 28 dias e por semana (Google → botão → cadastro → 1º lead → oferta → pagamento → pagou), MRR, ticket, churn, LTV, receita e cadastros por página de entrada, páginas com clique e sem cadastro, cliques por botão e experimentos. O relatório semanal (segunda, 8 h) ganhou "Funil até a compra" e põe as ações de dinheiro primeiro (`receita.py`, `medicao.py`).

**Testes:** `tests/test_pagamento.py`, `test_eventos.py`, `test_emails_pagantes.py`, `test_cota.py`, mais os casos novos em `test_seo.py` e `test_seo_pseo.py`; todos no passo "Guarda de SEO" do CI.

## 2. TODO-VALIDAR

1. **Prêmio da indicação** (ex.: 1 mês grátis para quem indica quando o indicado pagar). O link já funciona; o painel não promete nada até você decidir.
2. **Plano anual**: valor e desconto (hipótese 4 de `growth/experimentos.md`).
3. **Depoimentos**: só publicar o que vier com autorização escrita do cliente.
4. **Política de privacidade e termos**: revisão jurídica dos textos de cookies, e-mails e base legal (legítimo interesse para a medição sem dado pessoal).
5. **Nota fiscal**: o Mercado Pago não emite NFS-e; hoje nenhuma nota sai automaticamente.

## 3. Ações manuais (só você pode fazer), em ordem

1. **Webhook de e-mail do Resend** (3 min): resend.com → Webhooks → Add Webhook → `https://www.turbovenda.com.br/webhook/email`, eventos `email.bounced` e `email.complained` → copiar o Signing Secret para `RESEND_WEBHOOK_SECRET` no Railway. (A criação pela API foi bloqueada pelo controle de segurança deste ambiente.)
2. **Nota fiscal**: combinar com o contador a emissão de NFS-e por venda (ou um emissor integrado, como NFE.io ou eNotas); com a primeira venda, isso vira obrigação.
3. **Decisões de preço**: prêmio da indicação e plano anual (seção 2).
4. **"Entrar com Google"** (opcional): `GOOGLE_CLIENT_ID` e `GOOGLE_CLIENT_SECRET` no Railway (o código já tem o fluxo; falta a credencial OAuth no projeto `turbovenda` do Google Cloud).
5. **WhatsApp oficial** (opcional): conta Meta Business verificada e modelos aprovados para a Cloud API; os avisos hoje saem por e-mail.
6. **`MP_WEBHOOK_SECRET`** (opcional): o pagamento já confirma sem ele; com ele, o webhook também confere a assinatura.

## 4. Linha de base e meta de 90 dias (até 07/02/2027)

| Etapa | Linha de base | Meta 90 dias | Fonte |
|---|---|---|---|
| Clique no botão ÷ visita do Google (páginas de empresas) | 3,6% (46 de 1.270, 28 dias) | 6% | `cta_cliques`, Search Console |
| Cadastro ÷ clique no botão | 20% (30 de 147, 28 dias) | 25% | `users`, `cta_cliques` |
| 1º lead ÷ cadastro | 40% (17 de 43, 60 dias) | 70% | `users.aha_em` |
| Pagamento iniciado ÷ quem viu a oferta | sem base (eventos desde 09/11) | medir 4 semanas e definir | `eventos` |
| Pagantes | 0 | 10 (MRR ≥ R$ 970) | `pagamentos`, `/admin/receita` |

As metas são estimativas a partir do volume atual, não promessas.

## 5. Riscos, dependências e fora do escopo

- **Volume baixo para testes:** com ~1.300 visitas do Google por mês nas páginas de empresas, só diferenças grandes aparecem em 1 mês; os testes rodam um por vez.
- **Intenção do tráfego:** a maior parte de quem chega procura um fornecedor, não uma ferramenta de vendas; a conversão dessas páginas tem teto. O blog e as ferramentas (intenção de quem vende) ainda aparecem pouco no Google (posição média ~25).
- **Sem cobrança recorrente:** o Mercado Pago só renova sozinho no cartão; a renovação depende do aviso por e-mail e da faixa no painel.
- **Fora do escopo:** isca de lead por e-mail com contatos de empresas (risco de LGPD com dados de MEI; ficou como hipótese 5), login por link mágico, WhatsApp oficial e emissão de nota fiscal.
