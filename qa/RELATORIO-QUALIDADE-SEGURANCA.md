# Relatório de qualidade e segurança — TurboVenda (Prompt 3)

09/11/2026. Inventário em `qa/inventario.md` e `qa/rotas.md`, ameaças em `qa/modelo-ameacas.md`, autorização em `qa/matriz-autorizacao.csv` e SBOM em `qa/sbom.cdx.json`.

## 1. Resumo executivo

O app **está em produção e ficou bem mais seguro hoje, mas ainda não tem a cobertura que o Prompt 3 exige para dizer "pronto"**. A revisão achou e corrigiu 5 falhas que afetavam clientes de verdade:

- **Duas falhas entre clientes:** a sessão e o QR Code do WhatsApp e do LinkedIn eram compartilhados; e qualquer pessoa trocava a conta de e-mail de outro cliente por um webhook sem autenticação.
- **XSS armazenado no painel:** dados raspados da internet viravam HTML sem escape.
- **E-mails com a marca errada:** a prospecção dos clientes saía com o modelo da Pili Equipamentos.
- **Sem recuperação de senha.**

Todas têm teste de regressão no CI. Para o "pronto" faltam três coisas:
- **Ambiente de homologação:** sem ele, não rodei teste ativo (ZAP, fuzzing e carga não rodam em produção).
- **Testes de ponta a ponta no navegador.**
- **Teste de restauração do backup.**

Também ficaram 25 commits de 29/10 que nunca foram integrados e precisam de decisão (seção 3).

## 2. Vulnerabilidades

| ID | Título | Severidade | Onde | Status | Teste de regressão |
|---|---|---|---|---|---|
| QA-SEC-007 | Sessão, QR e status do WhatsApp/LinkedIn eram os mesmos para todos os clientes (um via o QR de outro; o robô usava o WhatsApp de outro número) | **Crítica** | `app.py` (rotas de status/QR), `robo_pili/whatsapp.py`, `linkedin_bot.py` | corrigida (commit 6fade7b trazido da branch abandonada) | `test_whatsapp_e_linkedin_separados_por_cliente` |
| QA-SEC-001 | `/webhook/unipile` sem autenticação trocava a conta de e-mail de qualquer cliente (schema sequencial) | Alta | `app.py` | corrigida (name assinado por HMAC, com validade) | `test_webhook_unipile_recusa_nome_sem_assinatura` |
| QA-SEC-003 | XSS armazenado: nome, e-mail, site, decisor e descrição de empresas raspadas entravam no HTML do painel; site ia para `href` (aceitava `javascript:`) | Alta | `templates/dashboard.html`, `index.html`, `admin.html`, `config.html`, `agendar.html` (71 pontos) | corrigida (`esc`, `escOu`, `urlSegura`) | `test_nenhuma_interpolacao_de_dado_externo_sem_escape` (varre todos os templates) |
| QA-SEC-005 | Dependências com CVE: gunicorn 21.2 (request smuggling), aiohttp (40), cryptography (7), flask, requests, pytest | Alta | `requirements.txt` | corrigida ("No known vulnerabilities found") | auditoria semanal (`.github/workflows/seguranca.yml`) + Dependabot |
| QA-SEC-006 | Troca de senha não derrubava outras sessões; conta desativada mantinha acesso até 8 h | Média | `app.py` (`login_required`) | corrigida (`users.sessao_versao`, cache 60 s) | `test_troca_de_senha_derruba_sessoes_antigas` |
| QA-SEC-002 | `/agendar` e `/api/agendar/*` públicos sem limite; cada acesso abre uma conexão por cliente | Média | `app.py` | corrigida (30/min por IP) | `test_rotas_de_agendamento_tem_limite` |
| QA-SEC-004 | Sem Content-Security-Policy | Média | `app.py` | parcial: `object-src 'none'`, `base-uri 'self'`, `frame-ancestors 'self'` valendo; política completa em Report-Only com relatório em `/api/csp-report` | `test_cabecalhos_de_seguranca` |
| QA-LGPD-001 | Logs gravavam e-mail de lead e de cliente (17 linhas) | Média | `app.py` | corrigida (filtro mascara e-mail, CPF e segredos) | `test_logs_sem_email_cpf_ou_segredo` |
| QA-SEC-009 | Tokens da API v1 guardados em texto puro no banco | Média | `api_tokens` | **pendente** (guardar só o hash) | — |
| QA-SEC-010 | Admin com chave única, sem MFA e sem registro de quem viu dados pessoais | Média | `/admin*` | **pendente** | — |
| QA-SEC-008 | `/health` devolvia a mensagem do driver (host e usuário do banco) | Baixa | `app.py` | corrigida | `test_health_nao_vaza_detalhe_do_banco` |
| QA-SEC-011 | Webhook do Mercado Pago sem assinatura (`MP_WEBHOOK_SECRET` ausente) | Baixa | `app.py` | **aceita**: o aviso só dispara consulta ao MP com o nosso token; com o segredo configurado, a assinatura também é exigida | `tests/test_pagamento.py` |

**Falsos positivos triados:**
- **Bandit B608 (53 casos):** SQL com colunas em lista fechada, marcadores `%s` gerados ou schema validado.
- **B324:** hash só para variar texto entre páginas.
- **B104:** bind em 0.0.0.0 é o padrão de container.
- **Segredo no histórico:** um "token" de 22 caracteres num teste de 29/10 foi comparado com as chaves reais do Railway e não coincide.

## 3. Bugs funcionais

| ID | Bug | Severidade | Status |
|---|---|---|---|
| QA-FUN-001 | O envio de e-mail de prospecção dos clientes (`/send-emails`) usava `templates/email_pili.html`: **propaganda de tombadores da Pili Equipamentos, em nome do cliente** | Crítico | corrigido (commit 40b6e43 trazido) |
| QA-FUN-002 | Não havia recuperação de senha (quem esquecia perdia a conta) | Alto | corrigido (commit 59f38f8 trazido) |
| QA-FUN-003 | Sem termos próprios, o robô do cliente buscava com os termos da Pili (cerealistas, silos) e gastava a cota | Alto | corrigido (parte mínima do commit 14fae08) |
| QA-FUN-004 | **31 commits de 29/10 na pasta `D:/projetos/robo-comercial-wt-fix` (branch `fix/funil-conversao`) nunca entraram no master** | Processo | 4 trazidos hoje e 1 já resolvido de outro jeito (log por cliente); **25 a decidir**, lista abaixo |

**Os 25 commits restantes da branch abandonada**, com a recomendação para cada grupo:
- **Trazer, com teste do robô:**
  - telefone e e-mail validados, WhatsApp só de celular (0dcd94f);
  - decisor raspado volta a ser salvo (8c3f3b8);
  - Serper com paginação e chave do cliente decifrada (c7d73e5);
  - score pelo ICP do cliente (3c692b5);
  - nome do lead sem título de página e sem lead repetido (a8bfd05);
  - aviso do worker só para admin (4e89ef1).
- **Já refeitos no master por outro caminho, conferir antes de descartar:**
  - pagamento (291e451, 0a3123d, b2de497);
  - agendador interno (dbffef5);
  - cota por período (481f90a, ef80d6c);
  - robô liga sozinho (bbdbbe0, b7826c0);
  - cadastro com termos (ad46b2f);
  - login com destino (f2342d1);
  - oferta igual à cobrança (36a0b93);
  - textos do teste (3230f20, f067eee, 68c6f8c);
  - painel sem leads (846725c);
  - detalhe do lead (e8698f9);
  - logs (5669e05, fb1cf78);
  - iniciar robô com motivo (a9c2bfa);
  - sessão de 7 dias (b21ba0c).

## 4. Cobertura de testes

| Camada | Situação |
|---|---|
| Regras de negócio e segurança (pytest, sem banco) | 234 testes; 232 passam e 2 exigem banco real (`test_conn_helper`, `/health`). Arquivos novos hoje: `test_seguranca_qa.py`, `test_pagamento.py`, `test_eventos.py`, `test_emails_pagantes.py`, `test_cota.py`, `test_indexnow.py`, `test_trafego.py`, `test_contas.py` |
| Páginas públicas (SEO, JSON-LD, títulos, robots) | `test_seo.py`, `test_seo_pseo.py` (base sintética) |
| Integração com banco real | **pendente**: precisa de Postgres descartável (Docker) ou branch do Neon |
| Contrato e fuzzing da API (OpenAPI/Schemathesis) | **pendente**: o app não tem OpenAPI |
| E2E no navegador (Playwright, 3 motores, celular), regressão visual, acessibilidade (axe) | **pendente** |
| Lighthouse | diário em produção (`lighthouse.yml`) |
| Carga (k6), ZAP, varredura de TLS | **pendente**: só em homologação, ou com sua confirmação para a parte passiva em produção |

## 5. Carga, backup e SLO

- **Carga:** não executada (não há homologação; regra do Prompt: nada de teste ativo em produção).
- **Backup:** o Neon guarda o histórico para restauração (point-in-time), mas **a restauração nunca foi testada**. Ela precisa de acesso ao console do Neon.
- **Metas de SLO sugeridas:**
  - disponibilidade mensal de 99,5%;
  - páginas públicas com p95 abaixo de 800 ms;
  - API do painel com p95 abaixo de 1,5 s;
  - menos de 1% de respostas 5xx;
  - alerta quando `/ready` falhar por 2 minutos.

## 6. Segredos e ações manuais

**Segredos a rotacionar: nenhum.** A varredura do histórico inteiro não achou chave real exposta.

**Ações suas, em ordem:**
1. **Decidir os 25 commits da branch abandonada** (seção 3). Minha recomendação é trazer o grupo "trazer, com teste do robô" e apagar a pasta `robo-comercial-wt-fix` depois.
2. **Criar um ambiente de homologação:**
   - uma branch do banco no Neon;
   - um segundo ambiente no Railway com essa branch.
   
   Com isso eu rodo ZAP, fuzzing, carga e os testes de integração.
3. **Testar a restauração do backup no Neon:**
   1. Restaure um ponto do passado numa branch nova.
   2. Cronometre quanto tempo leva.
   3. Me passe o tempo.
4. **Confirmar a verificação passiva de produção:** cabeçalhos, TLS e portas abertas, sem nenhum ataque.
5. **Opcional:** configurar `MP_WEBHOOK_SECRET` e o webhook do Resend (`RESEND_WEBHOOK_SECRET`).

## 7. Riscos aceitos e fora do escopo

- **CSP completa em Report-Only:** passa a valer depois de algumas semanas de relatórios sem violação legítima.
- **Admin com chave única:** mitigado por limite de tentativas e chave longa. MFA e registro de acesso ficam pendentes.
- **Tokens da API em texto puro:** recurso do plano Pro, sem pagante hoje. Fica pendente.
- **Fora do escopo:**
  - testes do robô de ponta a ponta (dependem de sites de terceiros e contas reais de WhatsApp e LinkedIn);
  - fluxo de cartão real;
  - servidor próprio (não se aplica: hospedagem gerenciada no Railway).
