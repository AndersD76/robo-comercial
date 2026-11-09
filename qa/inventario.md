# Inventário (Fase 0 do Prompt 3) — TurboVenda

Levantado em 09/11/2026 a partir do código. Lista completa de rotas, gerada do `app.py` por `qa/ferramentas/inventario.py`: [`qa/rotas.md`](rotas.md) (141 rotas).

## Contexto

| Item | Valor |
|---|---|
| Front | HTML renderizado no servidor (Jinja) + JS sem framework no painel (`templates/dashboard.html`, `index.html`, `config.html`) |
| Back | Flask 3.1 (um arquivo, `app.py`, ~11 mil linhas) em gunicorn 23 (1 processo, 8 threads) atrás de nginx |
| Banco | PostgreSQL no Neon; um schema por cliente (`emp_<id>`) + schema `public` (usuários, pagamentos, telemetria, base de empresas) |
| Hospedagem | Railway (Docker, imagem Playwright/Python 3.10), deploy pelo GitHub com "Wait for CI" e healthcheck em `/health` |
| Ambientes | local (sem banco: testes com banco falso e base sintética) e produção. **Não há staging** |
| Autenticação | sessão Flask (cookie assinado, HttpOnly, Secure, SameSite=Lax, 8 h), senha com bcrypt; admin por `ADMIN_KEY`; API v1 por token Bearer (plano Pro) |
| Multi-tenant | sim, isolamento por schema; o schema vem sempre da sessão (`_get_schema()`), nunca da requisição |
| Papéis | visitante, cliente (teste/Starter/Pro), cliente via token de API, admin, lead (link de agendamento), provedores (webhooks) |
| Integrações | Mercado Pago (Pix, cartão), Resend (e-mail), Unipile (e-mail/LinkedIn), Anthropic (IA), Google Search Console, Bing, IndexNow, DuckDuckGo/Serper (busca do robô) |
| Dados sensíveis | e-mail, senha (hash), CPF do titular do cartão (só repassado ao MP), dados de contato de empresas e sócios (públicos da Receita, mas pessoais quando MEI), conteúdo de e-mails e mensagens |
| IA no produto | gerador de mensagem (ferramenta pública), textos do robô e e-mails |

## Pontos de entrada

| Tipo | Itens |
|---|---|
| Páginas públicas | landing, preços, blog, `/empresas/*` (~10 mil), ferramentas, dados, imprensa, cadastro, login, recuperação de senha |
| API do painel (sessão) | `/api/<bot>/*` (leads, configuração, robô, e-mail, agenda, tarefas), `/api/meu-plano`, `/api/pagamento/*`, `/api/checkout`, `/api/meus-dados/*` |
| API pública (token) | `/api/v1/leads*` |
| Admin | `/admin*` (ADMIN_KEY, 5 tentativas/min) |
| Links com token | `/agendar/<token>` (lead), `/t/<token>/open.png` e `/click` (rastreio de e-mail), `/descadastrar/<id>.<hmac>`, `/redefinir-senha/<token>` |
| Webhooks recebidos | `/webhook/mercadopago` (aviso só dispara consulta ao MP), `/webhook/email` (Resend, assinatura svix), `/webhook/unipile` (name assinado por HMAC) |
| Telemetria do navegador | `/api/t/pv`, `/api/t/cta`, `/api/t/evento` (lista fechada), `/api/csp-report` |
| Jobs internos (threads) | funil de e-mails (hora em hora, 8–20 h), medição (6 h GSC/Bing, 7 h share of voice mensal, aha por hora, relatório semanal), IndexNow (10 URLs/min), conciliação do MP (10 min), telemetria (lote a cada 2 s) |
| Processos do robô | `robo_pili/run_busca.py`, `run_full.py` (WhatsApp), `linkedin_bot.py`, disparados por cliente |
| PC do dono | worker da Receita (15 min), atualização mensal da base e do relatório de dados |

## Fluxo de dados pessoais

| Dado | Entra por | Fica em | Vai para | Retenção |
|---|---|---|---|---|
| E-mail e senha do cliente | cadastro | `users` (senha em bcrypt) | Resend (e-mails do sistema) | enquanto a conta existir; `/api/meus-dados/excluir` apaga |
| Dados de leads (nome, e-mail, telefone, sócio) | robô (busca na web, Receita) | `emp_<id>.empresas`, `contatos` | e-mails/WhatsApp do cliente (Resend/SMTP/Unipile) | enquanto a conta existir |
| CPF do titular do cartão | modal de pagamento | não é gravado | Mercado Pago (tokenização no navegador) | — |
| Origem da visita | cookies `tv_ft`/`tv_lt` (sem dado pessoal) | `users.first_touch/last_touch` | — | 90 dias no cookie |
| Logs | servidor | Railway | — | retenção do Railway; e-mail, CPF e segredos mascarados desde 09/11 |
