# Modelo de ameaças (STRIDE) — TurboVenda

09/11/2026. Ativos mais valiosos, em ordem:
1. **Leads e conversas de cada cliente** (o produto).
2. **Contas conectadas de e-mail, WhatsApp e LinkedIn dos clientes**: quem as controla fala em nome do cliente.
3. **Cobrança**: plano liberado sem pagar, ou pago e não liberado.
4. **Credenciais e chaves**: Mercado Pago, Resend, Anthropic e banco.
5. **Reputação de envio** do domínio compartilhado.

| Componente | S (falsificação) | T (adulteração) | R (repúdio) | I (vazamento) | D (negação de serviço) | E (elevação de privilégio) |
|---|---|---|---|---|---|---|
| Login, cadastro e senha | força bruta → limites por IP; reset sem revelar contas | — | eventos `signup_completed`; sem log de login (pendente) | logs com e-mail → **mascarados** | limites 5–10/min | sessão antiga após troca de senha → **revogada** (sessao_versao) |
| Painel e API do cliente | cookie assinado, HttpOnly, SameSite=Lax; CSRF em formulário | colunas em lista fechada (sem mass assignment) | `atividades` por lead | **XSS armazenado com dados raspados → corrigido** (esc/urlSegura) | limite global 200/min | isolamento por schema da sessão |
| Robô (busca, WhatsApp, LinkedIn) | — | — | logs por cliente | **sessão e QR do WhatsApp/LinkedIn compartilhados → separados por cliente**; termos de outro cliente (Pili) → removidos | processo por cliente | — |
| Pagamento | aviso falso no webhook → só dispara consulta ao MP | valor e plano conferidos no MP | tabela `pagamentos` | — | limite 30/min no webhook | liberação única (`aplicado_em`) |
| Webhook da Unipile | **aviso falso trocava a conta de e-mail de qualquer cliente → name assinado** | — | log | — | 60/min | — |
| Agendamento (lead) | token de 128 bits | — | `agenda` | — | **varria todos os clientes por acesso → limite 30/min** | — |
| Admin | chave única de 27 caracteres; 5 tentativas/min | — | **sem registro de acesso a dados pessoais (pendente)** | — | — | sem MFA (pendente) |
| Páginas públicas | — | — | — | `/health` com detalhe do banco → **genérico** | limites nas ferramentas com IA | — |
| Navegador | — | — | — | CSP só parcial (object-src, base-uri, frame-ancestors); a completa em Report-Only | — | — |
| Cadeia de suprimentos | — | — | — | — | — | 6 pacotes com CVE → **atualizados**; Dependabot e auditoria semanal |

Em **negrito**: o que foi encontrado e corrigido em 09/11. Pendências e riscos aceitos estão em `qa/RELATORIO-QUALIDADE-SEGURANCA.md`.
