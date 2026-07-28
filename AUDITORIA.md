# AUDITORIA.md — TurboVenda (robo-comercial)

> **Data**: 2026-07-28 | **Fase**: 1 (somente analise — nenhum codigo foi alterado)
> **Arquivo principal**: app.py (~6700 linhas) | **Stack**: Flask, PostgreSQL (multi-tenant per-schema), Mercado Pago, Jinja2, Playwright
> **Blocos concluidos**: A, B, C, D, E, F, G (todos os 7 blocos)
> **Status**: Aguardando autorizacao para Fase 2 (correcoes)

---

## Resumo por Severidade (COMPLETO — 21 secoes)

| Severidade | Bloco A | Bloco B | Bloco C | Bloco D | Bloco E | Bloco F | Bloco G | **TOTAL** |
|------------|---------|---------|---------|---------|---------|---------|---------|-----------|
| CRITICO    | 4       | 2       | 1       | 3       | 0       | 1       | 2       | **13**    |
| ALTO       | 8       | 9       | 10      | 12      | 3       | 7       | 7       | **56**    |
| MEDIO      | 15      | 12      | 18      | 14      | 13      | 14      | 10      | **96**    |
| BAIXO      | 23      | 10      | 3       | 7       | 11      | 7       | 4       | **65**    |
| **Total**  | 50      | 33      | 32      | 36      | 27      | 29      | 23      | **230**   |

> Nota: Existem ~8 achados duplicados entre blocos (ex: #68/#101 IndexNow, #81/#103 emails, #80/#321 cron token). O total liquido e ~222 achados unicos.

## TOP 10 — Correcoes Mais Urgentes

| # | Sev | Secao | Descricao | Impacto |
|---|-----|-------|-----------|---------|
| #69/#300 | CRITICO | Seg/Pag | Dados de cartao trafegam pelo backend (PCI-DSS) | Legal/financeiro |
| #311/#304 | CRITICO | Planos | Planos pagos nunca expiram na pratica | Receita perdida |
| #271 | CRITICO | LGPD | GA4 carrega sem consentimento (sem cookie banner) | Legal/LGPD |
| #15 | CRITICO | Contratos | Save config apaga credenciais SMTP/Resend/etc | Perda de dados |
| #35/#36 | CRITICO | DB | Falta indice em email_track_token/agenda_token — O(N*M) scan | Performance critica |
| #179/#180 | CRITICO | Testes | <1% cobertura de testes; zero CI/CD | Risco de regressao |
| #313 | ALTO | Planos | Trial expirado so bloqueia add-lead; APIs permanecem abertas | Abuso de trial |
| #166 | CRITICO | Perf | Sem connection pooling; nova conexao a cada request | Escalabilidade |
| #273 | ALTO | LGPD | Sem exclusao/exportacao de dados (Art. 18) | Legal/LGPD |
| #251/#252 | ALTO | Textos | Paginas legais (Privacidade/Termos) sem acentos | Credibilidade |

---

# BLOCO B — ERROS/BUGS (Secao 4) + SEGURANCA (Secao 5)

## Secao 4: Erros e Bugs

#50 [ALTO] app.py:2831 — Rota /api/<bot>/console retorna 200 em caso de erro
A rota retorna jsonify({'lines': [], 'error': 'Erro interno'}) SEM status code de erro (default 200). O frontend recebe sucesso mesmo que o servidor falhou.
Correcao proposta: Retornar status 500: return jsonify({...}), 500
Risco da correcao: Nulo.

#51 [ALTO] app.py:2934-2935 — SQL injection potencial via nomes de campo em f-string
`sets = ', '.join(f'{k} = %s' for k in fields)` — os nomes de campo (keys do dict) sao interpolados diretamente no SQL. Embora filtrados pela whitelist 'allowed' (linha 2884), a mesma logica se repete em api_update_sequencia (3451), public_update_lead (4756) e api_update_evento (4841). Se uma whitelist for ampliada com erro de digitacao ou valor do usuario, vira SQL injection imediata.
Correcao proposta: Usar psycopg2.sql.Identifier() para os nomes de coluna.
Risco da correcao: Baixo.

#52 [MEDIO] app.py:5227-5271 — _find_lead_by_email_token: N+1 scan por TODOS os schemas de TODOS os tenants
Para cada abertura de pixel (open.png) ou clique de link, a funcao carrega TODOS os users, itera schema por schema e faz SELECT em cada um ate achar o token. Complexidade = O(num_tenants). Identico em _find_lead_by_token (5820-5864) e no webhook_email (5391-5418).
Correcao proposta: Criar tabela global email_tracking_tokens(token, schema_name, lead_id).
Risco da correcao: Medio — requer migracao de dados existentes.

#53 [MEDIO] app.py:6616-6637 — N+1 queries no admin_api_stats
Loop por todos os users executando COUNT(*) em cada schema individualmente. Mesmo padrao em admin_api_users_list (6667-6678).
Correcao proposta: Usar query unica cross-schema com psql.SQL ou CTE.
Risco da correcao: Baixo.

#54 [MEDIO] app.py:2948-2962 — Connection leak no api_delete_lead
Se o DELETE falha no meio (e.g. apos deletar interacoes mas antes de deletar empresas), a excecao e capturada mas conn nunca e fechada — nao ha bloco finally.
Correcao proposta: Adicionar try/finally com conn.close().
Risco da correcao: Nulo.

#55 [MEDIO] app.py:2965-2986 — Connection leak no api_clear_all
Mesmo problema: conn e fechada so no caminho feliz (conn.close() na linha 2983), mas se excecao ocorre, conn vaza.
Correcao proposta: Adicionar try/finally com conn.close().
Risco da correcao: Nulo.

#56 [MEDIO] app.py:3170-3190 — Connection leak em _preencher_estado_por_ddd
conn = _conn(schema) sem try/finally. Se c.execute falha, conn vaza. Mesmo padrao em _buscar_redes_decisor (3214-3248), _get_agenda_token (5182-5196) e _get_email_track_token (5199-5223).
Correcao proposta: Envolver em try/finally ou context manager.
Risco da correcao: Nulo.

#57 [MEDIO] app.py:3900-3936 — Connection leak no loop de send-emails
A conn principal (3874) e aberta e fechada (3893) antes do loop, enquanto conn2 criada dentro do loop por lead pode acumular se o close falha no finally.
Correcao proposta: Reutilizar uma unica conexao para todo o loop.
Risco da correcao: Baixo.

#58 [MEDIO] app.py:237 — except Exception: conn.rollback() sem re-raise durante migrations
No _init_public_schema_safe, cada ALTER TABLE que falha faz rollback silencioso (sem log). Se uma migration critica falha, ninguem sabe. Mesmo padrao na linha 482-483 no _init_user_schema.
Correcao proposta: Logar o erro: logger.warning(f'migration skip: {stmt}: {e}')
Risco da correcao: Nulo.

#59 [MEDIO] app.py:2660-2687 — Queries N+1 no pipeline
Loop pelas 6 etapas (stages) executando 2 queries por etapa (COUNT + SELECT) = 12 queries por request. Sem indice explicito em empresas.status.
Correcao proposta: Query unica com GROUP BY status e window function.
Risco da correcao: Baixo.

#60 [MEDIO] app.py:3496 — IndexError potencial se passos estiver vazio
dia_0 = passos[0].get('dia', 0) if passos else 0 — OK aqui. Mas na linha 3575-3576: idx = p['passo_atual']; if idx >= len(passos): — se passos for vazio E passo_atual for 0, marca como concluido por acidente.
Correcao proposta: Validar que passos nao esta vazio ao criar a sequencia.
Risco da correcao: Nulo.

#61 [BAIXO] app.py:6284 — ValueError nao tratado no parsing da validade do cartao
exp_month = int(exp_parts[0]) pode lancar ValueError se o usuario enviar "ab/cd".
Correcao proposta: Envolver em try/except ValueError e retornar 400.
Risco da correcao: Nulo.

#62 [BAIXO] app.py:147 — Error handler 500 renderiza 404.html
O handler de 500 usa render_template('404.html'), mostrando "pagina nao encontrada" para um erro de servidor.
Correcao proposta: Criar template 500.html ou generico de erro.
Risco da correcao: Nulo.

#63 [BAIXO] app.py:67-69 — Fernet key invalida silenciosamente ignorada
Se ENCRYPTION_KEY existe mas e invalida (len != 44), o codigo gera key nova descartavel, e seta _fernet = None. Campos ja encriptados com a key real nunca serao decriptados, retornando ciphertext bruto.
Correcao proposta: Logar WARN e/ou recusar iniciar se ENCRYPTION_KEY e invalida.
Risco da correcao: Pode bloquear deploy se key mal configurada.

#64 [BAIXO] dashboard.html — 67 chamadas fetch, apenas 33 com .catch
Cerca de metade das chamadas fetch no dashboard nao tratam erro de rede. O usuario nao recebe feedback nenhum.
Correcao proposta: Wrapper global fetch com catch padrao que mostra toast.
Risco da correcao: Nulo.

#65 [BAIXO] admin.html — toggleUser e impersonate sem try/catch
As funcoes toggleUser (420) e impersonate (490) NAO tem try/catch, portanto erros de rede viram excecao nao tratada.
Correcao proposta: Envolver em try/catch.
Risco da correcao: Nulo.

#66 [BAIXO] app.py:330 — SET search_path via %s em vez de psql.Identifier
Envia o schema name como string literal, nao como identificador. A linha 279-280 usa psql.Identifier corretamente, criando inconsistencia.
Correcao proposta: Usar psql.Identifier(schema) tambem aqui.
Risco da correcao: Nulo.

#67 [BAIXO] app.py:2856 — api_add_lead retorna 200 quando lead ja existe
Retorna {'ok': True, 'id': ex['id'], 'msg': 'ja existe'} com status 200. O frontend nao distingue "criado" de "ja existia".
Correcao proposta: Adicionar campo 'created': False para o frontend distinguir.
Risco da correcao: Nulo.

---

## Secao 5: Seguranca

#68 [CRITICO] app.py:2026 — _INDEXNOW_KEY hardcoded no codigo fonte
_INDEXNOW_KEY = 'b4f7e2a1c9d84f6e8a3b5c7d9e1f0a2b'. A key esta hardcoded no source code e publicada em repositorio git. RISCO REAL: BAIXO (IndexNow keys sao semi-publicas), mas o padrao e ruim.
Correcao proposta: Mover para env var INDEXNOW_KEY.
Risco da correcao: Nulo.

#69 [CRITICO] app.py:6261-6407 — Dados COMPLETOS de cartao de credito trafegam pelo backend
A rota /api/pagamento/cartao recebe card_number, expiration, cvv, holder_name diretamente no JSON body. O servidor le esses dados em texto claro (6274-6278), entao os envia para o Mercado Pago. Isso viola PCI-DSS: dados de cartao NUNCA devem tocar o servidor. O Mercado Pago oferece tokenizacao client-side (MercadoPago.js).
Correcao proposta: Usar MercadoPago.js no frontend para tokenizar o cartao no browser. O backend recebe apenas o card_token, nunca os dados crus.
Risco da correcao: Medio — requer reescrever o fluxo de pagamento no frontend.

#70 [ALTO] app.py:501 — Hash SHA-256 legado aceito sem sal
_verify_pw ainda aceita SHA-256 puro: hashlib.sha256(pw.encode()).hexdigest(). Vulneravel a rainbow tables. Migracao automatica para bcrypt existe (linhas 949-964), mas o caminho SHA-256 permanece indefinidamente para contas que nunca fazem login.
Correcao proposta: Forcar reset de senha para contas com hash SHA-256 (filtrar WHERE password_hash NOT LIKE '$2%').
Risco da correcao: Medio — usuarios legados precisarao trocar senha.

#71 [ALTO] app.py:36-40 — SECRET_KEY gerada aleatoriamente se nao configurada
Se SECRET_KEY nao esta no ambiente, uma key temporaria e gerada. Sessoes invalidadas a cada restart; em multiplos workers, cada um gera key diferente.
Correcao proposta: Falhar hard (sys.exit) se SECRET_KEY nao esta no ambiente em producao.
Risco da correcao: Baixo.

#72 [ALTO] app.py:1075-1099 — Rota /admin/users tem auth inconsistente com admin panel
A rota usa session.get('admin_auth') + verifica ADMIN_KEY, mas NAO usa o decorator @admin_required como todas as demais rotas /admin/*.
Correcao proposta: Substituir o check manual por @admin_required.
Risco da correcao: Nulo.

#73 [ALTO] app.py:6730-6749 — Impersonation sem audit trail
/admin/api/users/<uid>/impersonate seta session['user_id'] = uid sem logar quem fez o impersonate, quando, de qual IP.
Correcao proposta: Logar: admin_email, target_uid, timestamp, IP. Manter session['impersonated_by'].
Risco da correcao: Nulo.

#74 [ALTO] app.py — API tokens nunca expiram
A tabela api_tokens tem 'ativo' e 'criado_em' mas nenhum campo expires_at. Tokens gerados ficam validos para sempre.
Correcao proposta: Adicionar coluna expires_at com default 90 dias. Checar expiracao no token_required decorator (636-664).
Risco da correcao: Baixo.

#75 [ALTO] app.py:100 — Bypass de CSRF para qualquer request com JSON content-type
Qualquer request com Content-Type contendo "json" pula a checagem CSRF. Protecao acidental via ausencia de CORS, mas se alguem adicionar CORS permissivo, todo CSRF e bypassado.
Correcao proposta: Para rotas JSON autenticadas, validar Origin/Referer header OU manter CSRF via custom header.
Risco da correcao: Medio.

#76 [ALTO] app.py:5843 — SELECT * FROM empresas expoe todos os campos via token
_find_lead_by_token faz SELECT * e retorna dict(lead) completo com campos sensiveis (email_track_token, agenda_token, observacoes).
Correcao proposta: Especificar colunas explicitamente no SELECT.
Risco da correcao: Nulo.

#77 [MEDIO] app.py — Ausencia de CORS headers
Nao ha flask-cors nem headers Access-Control. A API publica (api/v1/*) nao funciona de SPAs externas.
Correcao proposta: Adicionar flask-cors com origins restrito para /api/v1/*.
Risco da correcao: Baixo.

#78 [MEDIO] app.py:523 — SELECT * FROM users retorna password_hash
get_current_user faz SELECT * que inclui password_hash, mp_customer_id, mp_subscription_id.
Correcao proposta: Especificar colunas no SELECT, excluindo password_hash.
Risco da correcao: Nulo.

#79 [MEDIO] app.py:872 — get_bot_config retorna campos sensiveis decriptados
A rota GET /api/<bot>/config (4058-4065) faz cfg.pop('linkedin_password', None) mas NAO remove smtp_password, resend_api_key, serper_api_key, brave_api_key, google_cse_key. Esses campos decriptados sao retornados no JSON.
Correcao proposta: Remover TODOS os _SENSITIVE_FIELDS do response, ou mascarar.
Risco da correcao: Frontend pode depender dos valores — usar placeholder.

#80 [MEDIO] app.py:6897 — Rota /api/cron/trial-emails aceita token via query string
O token no query string aparece em logs de servidor, proxies, analytics.
Correcao proposta: Aceitar APENAS via header X-Cron-Secret.
Risco da correcao: Ajustar o cron externo.

#81 [MEDIO] app.py:240 — Credenciais de email hardcoded
UPDATE users SET plano = 'pro' WHERE email IN ('suporte@pcmonitor.com.br', 'comercial1@pili.ind.br').
Correcao proposta: Mover para env var ADMIN_EMAILS ou remover.
Risco da correcao: Nulo.

#82 [MEDIO] app.py — Rate limiting ausente em rotas sensiveis de pagamento
/api/pagamento/pix, /api/pagamento/cartao, /api/pagamento/boleto e /api/<bot>/send-emails sem @limiter.limit.
Correcao proposta: Adicionar @limiter.limit("10 per minute") nas rotas de pagamento.
Risco da correcao: Nulo.

#83 [MEDIO] app.py:2786-2794 — subprocess.Popen controlado pelo usuario
Parametro 'canal' e validado (in ('busca', 'linkedin', 'wa')), e o script e selecionado de dict fixo. O parâmetro --schema recebe o schema do user. Popen sem shell=True (correto). Risco residual se scripts filhos nao validarem --schema.
Correcao proposta: Auditar scripts filhos.
Risco da correcao: Nulo.

#84 [MEDIO] app.py:102-104 — CSRF bypass para /webhook/* e /t/*
Webhooks legitimamente precisam pular CSRF, mas /t/* e prefixo amplo.
Correcao proposta: Listar rotas exatas em vez de prefixo amplo.
Risco da correcao: Baixo.

#85 [MEDIO] app.py:6580 — Admin login seta session flag simples
session['admin_auth'] = True e um boolean simples. Vulneravel a session fixation.
Correcao proposta: Armazenar admin_auth_at (timestamp) e admin_ip. Considerar sessao admin separada.
Risco da correcao: Baixo.

#86 [MEDIO] app.py:6484-6514 — pagamento_resultado com f-string HTML
Os valores vem do dict hardcoded, NAO do input do usuario. NAO ha XSS ativo. Mas o padrao de retornar f-string HTML e arriscado para manutencao futura.
Correcao proposta: Migrar para render_template.
Risco da correcao: Nulo.

#87 [BAIXO] templates/blog_post.html:162 — {{ post.conteudo|safe }} renderiza HTML cru
Conteudo dos posts e hardcoded em BLOG_POSTS, portanto nao e input de usuario. Mas se migrar para CMS, vira vetor de XSS stored.
Correcao proposta: Documentar que conteudo deve ser sanitizado antes de inserir.
Risco da correcao: Nulo.

#88 [BAIXO] templates/empresas_cidade.html:23-25 — {{ ld_*|safe }} em JSON-LD
Dados de municipios vem da Receita Federal. Risco teorico se nome contiver </script>.
Correcao proposta: Usar json.dumps(..., ensure_ascii=True).
Risco da correcao: Nulo.

#89 [BAIXO] app.py — Session lifetime de 8 horas pode ser excessiva
Para SaaS com dados financeiros, 2-4 horas seria mais prudente.
Correcao proposta: Reduzir para 4 horas. Adicionar inactivity timeout.
Risco da correcao: UX — usuarios precisarao relogar mais.

#90 [BAIXO] app.py — Senhas sem requisito de complexidade
Cadastro aceita qualquer senha >= 6 caracteres.
Correcao proposta: Exigir 8 chars. Opcionalmente checar contra lista de senhas comuns.
Risco da correcao: UX.

#91 [BAIXO] app.py:59-69 — ENCRYPTION_KEY fallback silencioso
Se nao configurada, _fernet = None e campos sensiveis sao armazenados em texto claro sem aviso.
Correcao proposta: Logar WARN explicito no startup.
Risco da correcao: Nulo.

---

# BLOCO C — CONFIGURACAO (Secao 6) + DEPENDENCIAS (Secao 7) + QUALIDADE (Secao 8)

## Secao 6: Configuracao e Ambiente

#100 [MEDIO] app.py:56 — GA_MEASUREMENT_ID tem default hardcoded 'G-NGSNSF3SPM'
O ID real do Google Analytics esta no codigo-fonte. Qualquer fork herdaria esse tracking.
Correcao proposta: Remover o default, exigir a variavel ou usar '' como default.
Risco da correcao: Baixo.

#101 [ALTO] app.py:2026 — _INDEXNOW_KEY hardcoded (duplica #68)
Chave IndexNow exposta no repositorio.
Correcao proposta: Mover para env var INDEXNOW_KEY.
Risco da correcao: Baixo.

#102 [ALTO] app.py:1958-2131 — URL base 'https://www.turbovenda.com.br' hardcoded em 34 ocorrencias
Sitemap, IndexNow, llms.txt, pSEO e links internos usam URL fixa. Impossivel rodar em staging sem editar o codigo.
Correcao proposta: Substituir por BASE_URL (ja usada em algumas rotas, mas nao em todas).
Risco da correcao: Baixo.

#103 [MEDIO] app.py:240 — Emails hardcoded para promocao automatica a 'pro' (duplica #81)
Emails de admin/teste hardcoded no codigo.
Correcao proposta: Mover para env var ADMIN_EMAILS ou remover.
Risco da correcao: Baixo.

#104 [MEDIO] app.py:37 — Segredo legado 'mv-saas-2025-change-in-prod' no codigo
String de comparacao para detectar secret default esta no fonte.
Correcao proposta: Remover o check de igualdade especifica.
Risco da correcao: Nenhum.

#105 [BAIXO] app.py:42-43 — TEMPLATES_AUTO_RELOAD=True e SEND_FILE_MAX_AGE_DEFAULT=0 em producao
Configuracoes de dev que impactam performance em producao.
Correcao proposta: Condicionar a FLASK_ENV == 'development'.
Risco da correcao: Nenhum.

#106 [BAIXO] nixpacks.toml — Arquivo de build nao utilizado (railway.toml aponta para Dockerfile)
Dead config.
Correcao proposta: Remover ou documentar.
Risco da correcao: Nenhum.

Nota: Nao existe .env.example nem documentacao das variaveis de ambiente.

## Secao 7: Dependencias

#107 [ALTO] requirements.txt:4 — anthropic==0.102.0 declarado mas nunca importado em app.py
SDK da Anthropic no requirements mas nao usado pelo app principal. Aumenta container.
Correcao proposta: Remover ou mover para requirements separados.
Risco da correcao: Baixo.

#108 [ALTO] requirements.txt:5 — aiohttp==3.13.1 declarado mas nunca importado
Nao usado no app principal. Apenas nos sub-modulos robo_pili/robo_prima.
Correcao proposta: Remover ou mover.
Risco da correcao: Baixo.

#109 [ALTO] requirements.txt:6 — beautifulsoup4==4.14.2 declarado mas nunca importado
Nao importado em nenhum lugar do app principal.
Correcao proposta: Remover ou mover.
Risco da correcao: Baixo.

#110 [ALTO] requirements.txt:3 — playwright==1.55.0 declarado mas nunca importado em app.py
Usado apenas por scripts utilitarios e robo_pili. O Dockerfile instala browsers Playwright, adicionando ~400MB ao container.
Correcao proposta: Separar em requirements-tools.txt.
Risco da correcao: Medio — se os bots rodam no mesmo container, precisa manter.

#111 [MEDIO] requirements.txt:9-11 — google-api-python-client e deps declarados mas nao usados no app
Tres pacotes Google nao usados no app principal.
Correcao proposta: Mover para sub-requirements.
Risco da correcao: Baixo.

#112 [MEDIO] requirements.txt:15 — pytest==8.3.5 em requirements de producao
Framework de testes nao deve estar no requirements de producao.
Correcao proposta: Mover para requirements-dev.txt.
Risco da correcao: Nenhum.

#113 [BAIXO] app.py — requests (externo) + smtplib (stdlib) para envio de email
Fallback SMTP e uma segunda implementacao que pode divergir.
Correcao proposta: Documentar hierarquia de fallback.
Risco da correcao: Medio.

## Secao 8: Qualidade e Consistencia do Codigo

#114 [MEDIO] _generate_icons.py — Script utilitario standalone na raiz
Nunca importado por app.py. Deveria estar em scripts/.
Correcao proposta: Mover para scripts/.
Risco da correcao: Nenhum.

#115 [MEDIO] _generate_og_image.py — Script utilitario standalone na raiz
Mesmo caso.
Correcao proposta: Mover para scripts/.
Risco da correcao: Nenhum.

#116 [MEDIO] _fix_termos.py — Script de manipulacao direta de app.py na raiz
Ferramenta de dev descartavel.
Correcao proposta: Deletar ou mover para scripts/.
Risco da correcao: Nenhum.

#117 [ALTO] _list_users.py — Script admin que faz UPDATE direto no banco com email de cliente hardcoded
Contem UPDATE users SET plano='pro' WHERE email='luis@nucleopro.com.br'. Nao deveria estar no repo.
Correcao proposta: Deletar. Usar painel admin para alterar planos.
Risco da correcao: Nenhum.

#118 [MEDIO] _test_500.py, _test_termos.py, _test_tracking.py — Testes ad-hoc na raiz
Testes que extraem funcoes do app.py via string parsing. Frageis e nao integrados ao pytest.
Correcao proposta: Migrar logica util para tests/, deletar.
Risco da correcao: Baixo.

#119 [MEDIO] app-Notebook_Anders.py — Copia/versao antiga do app.py
Dead code no repositorio.
Correcao proposta: Deletar.
Risco da correcao: Nenhum.

#120 [MEDIO] templates/config-Notebook_Anders.html — Template de backup
Nunca referenciado por render_template().
Correcao proposta: Deletar.
Risco da correcao: Nenhum.

#121 [MEDIO] templates/index.html — Template legado nao renderizado
Nenhuma rota faz render_template('index.html'). A landing page usa landing.html.
Correcao proposta: Deletar.
Risco da correcao: Baixo.

#122 [MEDIO] templates/email_prisma.html — Template de email nunca referenciado
Nenhuma referencia a email_prisma em app.py.
Correcao proposta: Deletar.
Risco da correcao: Baixo.

#123 [MEDIO] robo_pili/ e robo_prima/ — Subprojetos parcialmente acoplados
app.py referencia robo_pili/ apenas para ler wa_status.json e rodar scripts via subprocess. robo_prima/ nao e referenciado. Ambos possuem seus proprios Procfile/nixpacks.toml/.gitignore.
Correcao proposta: Extrair para repositorios separados ou diretorio bots/ com separacao clara.
Risco da correcao: Medio.

#124 [CRITICO] app.py:162-251 vs app.py:285-320 — Duas funcoes que criam a mesma tabela users
_init_public_schema_safe() e _init_public_schema() ambas fazem CREATE TABLE IF NOT EXISTS users com colunas identicas. Se o dev local roda com python app.py, perde as migrations.
Correcao proposta: Unificar em uma unica funcao. Eliminar _init_public_schema().
Risco da correcao: Baixo.

#125 [ALTO] app.py:396-416 vs app.py:850-870 — Definicao de bot_config duplicada em 3+ lugares
A tabela bot_config e definida por CREATE TABLE em _init_user_schema (396), get_bot_config (850), e as migrations repetem em multiplos locais.
Correcao proposta: Definir schema da tabela em um unico lugar.
Risco da correcao: Baixo.

#126 [MEDIO] app.py:497-501 — Verificacao de senha com fallback SHA-256 legado (relacionado a #70)
O SHA-256 e inseguro para senhas (sem salt). Nao ha como saber se todas ja foram migradas.
Correcao proposta: Adicionar log/metrica para contar logins via SHA-256.
Risco da correcao: Medio.

#127 [MEDIO] app.py — import requests repetido 15 vezes como import local
import requests as http feito dentro de funcoes individuais em vez de no topo do arquivo.
Correcao proposta: Mover import requests para o topo do arquivo.
Risco da correcao: Nenhum.

#128 [MEDIO] app.py — from datetime import datetime repetido 7 vezes localmente
O modulo ja importa import datetime as _dt na linha 7, mas varias funcoes fazem from datetime import datetime localmente.
Correcao proposta: Padronizar usando _dt.datetime em todo o arquivo.
Risco da correcao: Nenhum.

#129 [BAIXO] app.py — Mix generalizado portugues/ingles em nomes
Funcoes: _hash_pw (EN) vs _gerar_termos (PT). Variaveis: empresa_nome (PT), password_hash (EN). Nao e um bug, mas dificulta onboarding.
Correcao proposta: Definir convencao no CLAUDE.md/CONTRIBUTING.md.
Risco da correcao: Alto se renomear existentes; baixo se apenas documentar.

#130 [MEDIO] app.py — 50+ chamadas print() em codigo de producao
O app tem logging.getLogger configurado mas quase nunca usa logger. 50+ print() espalhados.
Correcao proposta: Substituir todos os print() por logger.info/warning/error.
Risco da correcao: Baixo.

#131 [MEDIO] app.py — traceback.print_exc() em 4 locais em producao
Pode vazar informacao sensivel nos logs.
Correcao proposta: Substituir por logger.exception("msg").
Risco da correcao: Nenhum.

#132 [ALTO] app.py — Padrao de erro duplicado mas inconsistente em ~35 rotas
Algumas rotas retornam dados vazios em erro, outras 500, outras silenciam. O frontend nao pode tratar erros uniformemente.
Correcao proposta: Criar decorator ou middleware que padroniza respostas de erro.
Risco da correcao: Medio.

#133 [ALTO] app.py — 167 blocos except Exception (bare catch-all)
Todos os handlers capturam Exception generica, mascaram bugs (TypeError tratado como timeout de DB).
Correcao proposta: Gradualmente especializar: psycopg2.Error para DB, requests.RequestException para HTTP.
Risco da correcao: Medio.

#134 [MEDIO] app.py — Conexoes DB abertas/fechadas manualmente em todas as rotas
Boilerplate identico em dezenas de funcoes. Context manager eliminaria duplicacao e connection leaks.
Correcao proposta: Criar _conn() como context manager.
Risco da correcao: Baixo.

#135 [MEDIO] app.py:3864 — Referencia a templates/email_custom.html que nao existe
O codigo tenta abrir email_custom.html e faz fallback para email_pili.html. O fallback sempre executa.
Correcao proposta: Criar email_custom.html ou remover o try.
Risco da correcao: Nenhum.

---

# BLOCO D — FRONTEND (Secao 9) + PERFORMANCE (Secao 10) + TESTES (Secao 11)

## Secao 9: Frontend Especifico

#150 [ALTO] templates/dashboard.html:1055 — fetch /api/${BOT}/leads sem tratamento de loading
loadWA() faz fetch sem mostrar spinner/esqueleto ao usuario. Quando a resposta demora, a tabela fica vazia sem feedback.
Correcao proposta: Adicionar innerHTML com spinner no inicio de loadWA() e demais funcoes.
Risco da correcao: Baixo.

#151 [ALTO] templates/dashboard.html:1055,2102,2278,2349 — fetch sem tratamento de erro HTTP
loadWA() faz .then(r=>r.json()) direto, sem verificar r.ok. Se o servidor retornar 403 (sessao expirada), o .json() falha silenciosamente. Mesmo padrao em loadWaStats, loadRespostas, loadEmailLeads.
Correcao proposta: Verificar if(!r.ok) throw new Error(r.status) antes de .json().
Risco da correcao: Baixo.

#152 [ALTO] templates/dashboard.html:2102,2278,2349 — Frontend carrega leads sem paginacao (limite=9999/2000)
loadWaStats() pede ?limite=9999, loadRespostas() pede ?limite=2000. O backend ignora o parametro limite (usa per_page/page), mas o codigo JS pretende receber tudo de uma vez.
Correcao proposta: Implementar paginacao server-side nessas abas.
Risco da correcao: Medio.

#153 [MEDIO] templates/dashboard.html:2023-2026 — Multiplos setInterval sem cleanup
Quatro timers rodam permanentemente (30s, 60s, 10s, 120s). Nenhum limpo com clearInterval ao sair/ocultar a pagina.
Correcao proposta: Usar document.addEventListener('visibilitychange', ...).
Risco da correcao: Baixo.

#154 [MEDIO] templates/dashboard.html:1900 — QR polling interval (3s) sem limite de tentativas
setInterval(pollQr, 3000) roda indefinidamente. Se o usuario esquecer a janela aberta, fica fazendo requisicoes a cada 3s para sempre.
Correcao proposta: Adicionar contador maximo (~200 tentativas = ~10 min).
Risco da correcao: Baixo.

#155 [MEDIO] templates/dashboard.html:1867 — closeModal pode receber undefined
Chamada com onclick="closeModal(event)" no overlay, mas tambem referenciada sem argumento. Se e for undefined, e.target lanca TypeError.
Correcao proposta: Adicionar guard if(!e) return;
Risco da correcao: Baixo.

#156 [MEDIO] templates/dashboard.html:1078-1097 — innerHTML com dados de leads sem sanitizacao XSS
renderLeadsList() insere l.nome_fantasia, l.email, l.cnpj diretamente no HTML via template literals sem escape. XSS stored possivel se lead inserido manualmente.
Correcao proposta: Criar funcao esc(str) que faz replace de &, <, ".
Risco da correcao: Baixo.

#157 [MEDIO] templates/config.html:462-493 — previewCfgHtml injeta HTML do usuario em iframe sem sandbox
A funcao pega o valor do textarea email_html_template e escreve via doc.write em iframe SEM atributo sandbox.
Correcao proposta: Adicionar iframe.sandbox = 'allow-same-origin' (sem allow-scripts).
Risco da correcao: Baixo.

#158 [MEDIO] templates/config.html:496-554 — saveConfig exibe alert() com mensagem de erro bruta em producao
O catch usa alert('JS Exception: ' + e.message). Pode expor detalhes internos.
Correcao proposta: Substituir por showToast('Erro ao salvar. Tente novamente.', false).
Risco da correcao: Baixo.

#159 [MEDIO] templates/dashboard.html:1054-1065 — loadWA() carrega todos os leads na memoria do cliente
Com o default de 50 do backend e ok, mas a intencao do codigo (paginacao client-side) sugere que deveria receber todos.
Correcao proposta: Implementar paginacao server-side real.
Risco da correcao: Medio.

#160 [MEDIO] templates/admin.html:295-525 — Painel admin carrega TODOS os usuarios sem paginacao
loadUsers() e loadPayments() carregam tudo de uma vez.
Correcao proposta: Adicionar paginacao server-side.
Risco da correcao: Medio.

#161 [BAIXO] templates/dashboard.html:2004 — toggleConsole usa event implicito (deprecated)
A variavel global event e deprecated e nao funciona em Firefox com strict mode.
Correcao proposta: Receber event como parametro.
Risco da correcao: Baixo.

#162 [BAIXO] templates/dashboard.html:2912,2934 — event.target.closest('button') usa event global implicito
Funcoes enriquecerTodos() e requalificarTodos() acessam event.target sem receber event como parametro.
Correcao proposta: Passar event explicito via onclick.
Risco da correcao: Baixo.

#163 [BAIXO] templates/agendar.html:79 — Font Awesome carregado duas vezes
Link stylesheet aparece na linha 11 (head) e novamente na linha 79 (body).
Correcao proposta: Remover a segunda inclusao.
Risco da correcao: Nenhum.

#164 [BAIXO] templates/landing.html:151-155 — CSS tokens.css e components.css carregados duas vezes
Tags link stylesheet duplicadas.
Correcao proposta: Remover as duplicatas.
Risco da correcao: Nenhum.

#165 [BAIXO] templates/config.html:298 — BOT pode ser string vazia gerando URLs invalidas
Se user.schema_name for vazio, URLs de fetch ficam /api//config.
Correcao proposta: Redirecionar para configuracao se BOT vazio.
Risco da correcao: Baixo.

## Secao 10: Performance

#166 [CRITICO] app.py:271-282 — Sem connection pooling; nova conexao TCP a cada request
_conn() cria conexao nova via psycopg2.connect() a cada chamada. Overhead de ~20-50ms por conexao, exaustao de slots do PostgreSQL.
Correcao proposta: Usar psycopg2.pool.ThreadedConnectionPool. Configurar min=2, max=10.
Risco da correcao: Medio — requer refatoracao do padrao _conn()/conn.close().

#167 [ALTO] app.py:6618-6637 — N+1 query no admin_api_stats: itera todos schemas para contar leads
Com 100 usuarios = 201 queries.
Correcao proposta: Query unica com UNION ALL dinamico ou tabela de resumo materializada.
Risco da correcao: Medio.

#168 [ALTO] app.py:6655-6683 — N+1 query no admin_api_users_list: conta leads por usuario em loop
Mesma N+1 do #167, mas pior porque retorna todos os usuarios sem paginacao.
Correcao proposta: UNION ALL ou join lateral. Adicionar paginacao.
Risco da correcao: Medio.

#169 [ALTO] app.py:5237-5271 — _find_schema_for_track_token itera TODOS os schemas
Para N usuarios, sao N+1 conexoes e N queries. Chamada no endpoint de tracking (pixel/click), que pode ter alto trafego.
Correcao proposta: Tabela global email_tracks(token, schema, lead_id).
Risco da correcao: Medio — requer migracao.

#170 [ALTO] app.py:5391-5426 — Webhook de bounce/spam itera TODOS os schemas
Mesmo padrao de #169. Webhooks podem chegar em rajada.
Correcao proposta: Tabela global de mapeamento email -> schema.
Risco da correcao: Medio.

#171 [ALTO] app.py:3900-3909 — Loop sincrono de envio de emails no request handler
api_send_emails() envia emails um a um dentro de loop for, incluindo chamadas HTTP ao Resend e queries por lead. Com 50+ leads, timeout possivel.
Correcao proposta: Mover envio para fila de background. Retornar imediatamente com status "em progresso".
Risco da correcao: Alto — requer infraestrutura de fila.

#172 [MEDIO] app.py:2786-2789 — subprocess.Popen no request handler
Popen retorna imediatamente, mas processos filhos consomem CPU/RAM no mesmo container. Com gunicorn single-worker, o worker fica ocupado.
Correcao proposta: Documentar limitacao. Para escalar, mudar para sistema de filas.
Risco da correcao: Baixo.

#173 [MEDIO] app.py:523 — SELECT * FROM users no get_current_user (chamado em toda request)
Traz todas as colunas incluindo password_hash quando apenas id, schema_name, plano sao necessarios.
Correcao proposta: Listar colunas explicitamente.
Risco da correcao: Baixo.

#174 [MEDIO] app.py — Sem cache em nenhuma rota (exceto pSEO)
Rotas quentes como get_current_user(), /api/{bot}/stats, /api/{bot}/config sem cache.
Correcao proposta: Usar cachetools.TTLCache para get_current_user() (TTL=60s) e stats (TTL=30s).
Risco da correcao: Baixo — cuidado com invalidacao.

#175 [MEDIO] templates/dashboard.html — ~3300 linhas de CSS+JS inline monolitico
~120KB+ de HTML nao-cacheavel a cada visita.
Correcao proposta: Extrair JS para /static/dashboard.js e CSS para /static/dashboard.css.
Risco da correcao: Baixo — refatoracao mecanica.

#176 [MEDIO] templates/*.html — Google Fonts carregado via render-blocking link
Bloqueia renderizacao por ~100-300ms.
Correcao proposta: Usar link rel="preload" ... as="style" onload="this.rel='stylesheet'".
Risco da correcao: Baixo.

#177 [BAIXO] app.py:872 — SELECT * FROM bot_config quando apenas campos especificos sao necessarios
Se a tabela crescer, transfere dados desnecessarios.
Correcao proposta: Listar campos explicitamente.
Risco da correcao: Baixo.

#178 [BAIXO] Procfile:1 — Gunicorn com workers=1 e timeout=120
Um unico worker significa que requests longos bloqueiam TODAS as outras requests.
Correcao proposta: Aumentar workers para 2-4 e reduzir timeout para 30s.
Risco da correcao: Medio — com subprocess.Popen, multiplos workers podem causar problemas.

## Secao 11: Testes e Build

#179 [CRITICO] tests/test_basic.py — Cobertura quase nula; todos os testes pulam sem DATABASE_URL
3 testes que fazem pytest.skip() se DATABASE_URL nao esta configurado. <1% de cobertura.
Correcao proposta: Usar fixtures com mock do psycopg2. Adicionar testes para auth, CSRF, rate limiting, CRUD, validacao.
Risco da correcao: Nenhum.

#180 [CRITICO] — Modulos criticos sem nenhum teste
Nenhum teste para: autenticacao, CRUD de leads, envio de emails, pagamentos, admin panel, pSEO, scripts de ingestao, validacao de input.
Correcao proposta: Priorizar testes para (1) auth, (2) CRUD leads, (3) pagamentos, (4) emails.
Risco da correcao: Nenhum.

#181 [ALTO] Dockerfile — Imagem Playwright inclui Xvfb+VNC+nginx desnecessarios para web app
Imagem de ~2GB com superficie de ataque desnecessaria.
Correcao proposta: Separar em dois containers: web app com Python slim, worker com Playwright.
Risco da correcao: Alto — requer refatoracao de deploy.

#182 [ALTO] start.sh vs Procfile — Inconsistencia de entrypoint
start.sh usa gunicorn+nginx, Procfile usa gunicorn direto. Railway pode usar um ou outro.
Correcao proposta: Documentar qual entrypoint e usado em cada ambiente.
Risco da correcao: Baixo.

#183 [MEDIO] start.sh:5-6 — Xvfb inicia sem verificacao de sucesso
Xvfb :99 ... & seguido de sleep 1 — pode nao ser suficiente em ambientes lentos.
Correcao proposta: Adicionar verificacao com kill -0 $XVFB_PID.
Risco da correcao: Baixo.

#184 [MEDIO] — Sem CI/CD configurado
Nao ha .github/workflows/. Testes nunca rodam automaticamente.
Correcao proposta: Criar .github/workflows/test.yml minimo.
Risco da correcao: Nenhum.

#185 [BAIXO] tests/test_basic.py:8 — sys.path hack para import (fragil)
sys.path.insert(0, ...) e um hack fragil.
Correcao proposta: Criar pyproject.toml com install editavel.
Risco da correcao: Baixo.

---

# BLOCO A — ROTAS x CHAMADAS (Secao 1) + CONTRATOS (Secao 2) + DB vs CODIGO (Secao 3)

## Secao 1: Rotas x Chamadas de API

#1 [CRITICO] templates/index.html:687 — Rota fantasma /api/{bot}/linkedin
O template legacy index.html chama fetch(`/api/${bot}/linkedin`) para carregar leads do LinkedIn. Essa rota NAO EXISTE em app.py. Retorna 404 silenciosamente. A funcao loadLI() nunca mostra dados.
Correcao proposta: Remover a chamada loadLI() ou remover index.html (legado).
Risco da correcao: Nenhum.

#2 [ALTO] templates/index.html:845 — Canal 'li' invalido no start/stop
botFetch(bot, 'li', 'start') envia canal='li'. O backend (app.py:2774) so aceita ('busca', 'linkedin', 'wa'). Retorna 400.
Correcao proposta: Trocar 'li' por 'linkedin'.
Risco da correcao: Baixo.

#3 [ALTO] templates/index.html:868 — Campo 'li' vs 'linkedin' no status
Frontend le d.li mas backend retorna 'linkedin'. Badge de status nunca mostra "ativo".
Correcao proposta: Trocar d.li por d.linkedin.
Risco da correcao: Nenhum.

#4 [ALTO] templates/index.html:804-818 — Campos de stats inexistentes
Frontend le d.li_total, d.li_conexoes, d.li_demos. Backend retorna linkedin_total (nao li_total) e NAO retorna li_conexoes nem li_demos. KPIs sempre 0/undefined.
Correcao proposta: Renomear no frontend para alinhar com backend.
Risco da correcao: Baixo.

#5 [ALTO] templates/index.html:744 — Pipeline espera array, backend retorna objeto
renderPipe() faz data[st].filter(...) tratando cada estagio como array. Backend retorna {leads:[], total:N, page:N, pages:N}. Pipeline do index.html sempre vazio.
Correcao proposta: Trocar (data[st]||[]) por ((data[st]||{}).leads||[]).
Risco da correcao: Nenhum.

#6 [ALTO] templates/dashboard.html:2102,2278,2349 — Query param 'limite' ignorado pelo backend
Frontend envia ?limite=9999 mas backend le per_page (default 50). Sempre retorna apenas 50 leads embora o frontend espere todos. Afeta email em massa (envia para 50 em vez de todos).
Correcao proposta: No frontend trocar limite=N por per_page=N.
Risco da correcao: Baixo — per_page limitado a 200 no backend.

#7 [MEDIO] app.py:2647-6000 — Parametro <bot> na URL ignorado em todas as rotas
Todas as rotas /api/<bot>/... aceitam 'bot' na URL mas _get_schema() resolve pela sessao. O valor de 'bot' e descartado. /api/xyz/leads retorna os mesmos dados que /api/emp_1/leads.
Correcao proposta: Validar que bot == _get_schema() e retornar 403 se diferir.
Risco da correcao: Alto — requer atualizar todas as chamadas no frontend.

#8-#11 [BAIXO] Rotas backend nunca chamadas pelo frontend
/api/<bot>/clear-all, /api/<bot>/sequencia/<seq_id>/enroll, /api/<bot>/sequencia/<seq_id>/leads, /admin/users (legada). Existem no backend sem uso no frontend.

#12 [MEDIO] app.py:4687-4762 — Versionamento de API misto (/api/v1/* vs /api/<bot>/*)
3 rotas em /api/v1/ (token) e ~60 em /api/<bot>/ (sessao) com contratos diferentes.
Correcao proposta: Documentar as duas APIs como "interna" e "publica".
Risco da correcao: Nenhum.

#13 [BAIXO] templates/config-Notebook_Anders.html — Copia desatualizada de dev
Nao e servido por nenhuma rota.
Correcao proposta: Deletar.
Risco da correcao: Nenhum.

#14 [BAIXO] app.py:162 vs 284 — _init_public_schema_safe() vs _init_public_schema() duplicadas
Duas funcoes criam as mesmas tabelas users e api_tokens.
Correcao proposta: Unificar em uma unica funcao.
Risco da correcao: Baixo.

## Secao 2: Contratos de Dados

#15 [CRITICO] templates/config.html:506-521 vs app.py:4072-4203 — Save config APAGA credenciais
O payload de saveConfig() envia 15 campos. O backend TAMBEM le do request.json campos que o frontend NAO envia (linkedin_email, resend_api_key, smtp_host, smtp_password, serper_api_key etc.), recebendo-os como '' e fazendo UPDATE para NULL. Credenciais SMTP, Resend, Serper previamente salvas sao APAGADAS a cada save.
Correcao proposta: Ler o config atual antes do UPDATE e preservar campos nao enviados (merge).
Risco da correcao: Medio.

#16 [ALTO] templates/config.html — Campos de agendamento nunca enviados
horario_inicio, horario_fim, duracao_reuniao, dias_semana existem no bot_config mas NAO tem inputs no config.html. Nao ha como o usuario altera-los pela UI.
Correcao proposta: Adicionar campos de configuracao de agenda no config.html.
Risco da correcao: Baixo.

#17 [MEDIO] app.py:4060-4065 vs config.html — LinkedIn config retornado mas nao exibido
GET retorna linkedin_email e linkedin_cargos, mas o frontend nao os exibe.
Correcao proposta: Exibir campos LinkedIn na UI OU remover do schema se descontinuado.
Risco da correcao: Baixo.

#18-#19 [BAIXO] Contratos de add-lead e update-lead alinhados com ressalvas
Email e CNPJ nao validados (formato). Campos alinhados.

#20 [ALTO] templates/index.html:796-818 — Campos de stats nao alinhados (index.html legado)
Backend retorna linkedin_total, index.html le li_total, li_conexoes, li_demos (inexistentes).
Correcao proposta: Corrigir index.html ou descontinua-lo.
Risco da correcao: Nenhum.

#21-#25 [BAIXO/MEDIO] Outros desalinhamentos menores
#22 — Nomes de campo inconsistentes entre endpoints (cor_header vs email_cor_header).
#23 — Parametro vestigial 'limite' na assinatura de get_leads().
#24 — Query param 'bot' ignorado no pipeline.

## Secao 3: Banco de Dados x Codigo

#26-#28 [MEDIO] Colunas mortas: empresas.funcionarios, empresas.telefone2, empresas.demo_agendado
Nunca referenciadas em app.py.
Correcao proposta: Remover do CREATE TABLE.

#29-#33 [BAIXO] Colunas e tabelas vestigiais
logs.detalhes, contatos.telefone/whatsapp/email, tabela execucao (seed-only), tabela interacoes (DELETE-only em app.py), tabela leads_linkedin (COUNT-only).

#35 [CRITICO] app.py:5250 — Falta indice em empresas.email_track_token
_find_lead_by_email_token() itera TODOS os schemas e faz SELECT sem indice. Full table scan. Chamada em CADA abertura de email (pixel) e CADA clique.
Correcao proposta: CREATE INDEX + tabela de lookup centralizada.
Risco da correcao: Medio.

#36 [CRITICO] app.py:5843 — Falta indice em empresas.agenda_token
Mesma situacao: _find_lead_by_token() itera TODOS os schemas.
Correcao proposta: CREATE INDEX + lookup centralizado.
Risco da correcao: Medio.

#37 [ALTO] app.py:2669 — Falta indice em empresas.status
Campo aparece em WHERE de pipeline (6 queries/request), stats, email campaigns, bulk update, webhook bounce.
Correcao proposta: CREATE INDEX idx_emp_status ON empresas(status).

#38 [ALTO] app.py:760-768 — Falta indice composto em contatos(empresa_id, decisor)
Subquery correlacionada por lead sem indice. Com 200 leads e 3 contatos cada: 600 scans.
Correcao proposta: CREATE INDEX idx_contatos_empresa_decisor ON contatos(empresa_id, decisor).

#39-#43 [MEDIO/BAIXO] Indices ausentes adicionais
empresas.encontrado_em, empresas.score, empresas.email, sequencia_leads(status, proximo_envio), agenda.data_inicio.

#44-#45 [MEDIO] Foreign keys sem ON DELETE CASCADE
contatos.empresa_id e interacoes.empresa_id/contato_id sem CASCADE. Apagamento manual e fragil.
Correcao proposta: Adicionar ON DELETE CASCADE.

#46 [MEDIO] app.py:2676-2678 — Subquery de decisor assume nome e cargo existem
Concatenacao retorna NULL se nome ou cargo for NULL.
Correcao proposta: COALESCE(ct.nome, '') || ' - ' || COALESCE(ct.cargo, '').

Resumo Bloco A: 4 CRITICO, 8 ALTO, ~15 MEDIO, ~23 BAIXO = 50 achados.

---

# BLOCO E — SEO TECNICO (Secao 12) + URLS E LINKS (Secao 13)

## Secao 12: SEO Tecnico

#200 [MEDIO] templates/register.html:10-11 — GA ID hardcoded em vez de {{ ga_id }}
O template usa G-NGSNSF3SPM diretamente no HTML. A rota cadastro() nao passa ga_id.
Correcao proposta: Usar {{ ga_id }} e passar no render_template.

#201 [MEDIO] templates/login.html — GA ausente na pagina de login
Nenhum script GA4/gtag. Etapa critica do funil sem tracking.
Correcao proposta: Adicionar snippet GA com {{ ga_id }}.

#202-#205 [MEDIO] login.html, register.html, termos.html, privacidade.html — Falta OG tags
Paginas indexaveis sem Open Graph tags. Compartilhamentos sem preview rico.
Correcao proposta: Adicionar bloco completo de OG tags.

#206-#209 [BAIXO] termos.html, privacidade.html, blog.html, empresas_hub.html — Falta JSON-LD
Paginas sem structured data (BreadcrumbList, WebPage).
Correcao proposta: Adicionar JSON-LD.

#210 [ALTO] app.py:1955-1976 — Sitemap faltando /empresas, /empresas/sobre-os-dados e /empresas/{cnae_slug}
A funcao _static_sitemap_urls() NAO inclui o hub principal de pSEO, a pagina sobre-os-dados, nem as paginas de CNAE por estado.
Correcao proposta: Adicionar as URLs faltantes.
Risco da correcao: Baixo.

#211 [BAIXO] app.py:1961 — Sitemap inclui /login (noindex) desnecessariamente
URL noindex no sitemap e contraditorio.
Correcao proposta: Remover /login do sitemap.

#212 [MEDIO] app.py — Sem strict_slashes=False — trailing slash causa 308 redirect
Flask gera redirect 308 com trailing slash. Gasta request adicional.
Correcao proposta: Adicionar app.url_map.strict_slashes = False.

#213-#214 [MEDIO] Templates sem preconnect para fonts.gstatic.com
Google Fonts recomenda preconnect para ambos googleapis.com e gstatic.com. Varios templates faltando.
Correcao proposta: Adicionar preconnect nos templates.

#215 [MEDIO] GA script no head antes do CSS em alguns templates
Pode atrasar renderizacao do conteudo visivel.
Correcao proposta: Mover snippet GA para antes de </body>.

#216 [ALTO] landing.html:73-77 — JSON-LD aggregateRating fabricado
"ratingValue": "4.8", "reviewCount": "127" sem reviews reais verificaveis. Google pode penalizar.
Correcao proposta: Remover aggregateRating ate ter reviews reais.
Risco da correcao: Baixo.

#217-#220 [BAIXO] Titulos e meta descriptions sem acentos
privacidade.html, termos.html, 404.html com textos sem acentuacao portuguesa.
Correcao proposta: Corrigir acentuacao.

#221 [MEDIO] blog.html, precos.html, segmento.html — twitter:card sem twitter:title
Tem twitter:card mas faltam twitter:title e twitter:description.
Correcao proposta: Adicionar tags completas.

#222 [MEDIO] empresas_sobre.html — Falta og:image
Tem og:title/description/url mas falta og:image.
Correcao proposta: Adicionar og:image.

## Secao 13: URLs e Links

#223 [ALTO] config.html:254-255 — Links externos sem rel="noopener"
Links com target="_blank" sem noopener. Risco de tabnapping.
Correcao proposta: Adicionar rel="noopener" em todos os links com target="_blank".
Risco da correcao: Baixo.

#224-#225 [MEDIO] landing.html, trial_expirado.html — Links externos sem nofollow
Links para sites proprios/WhatsApp sem nofollow. Decisao de negocio.
Correcao proposta: Adicionar nofollow se nao estrategico.

#226 [MEDIO] empresas_hub.html:116 — Links via /empresas/busca geram redirect chain 302
Cadeia de redirect para crawlers. Seria mais eficiente linkar diretamente a pagina final.
Correcao proposta: Calcular URL final no backend.

#230 [MEDIO] blog_post.html:184-187 — Links hardcoded para /empresas/* podem estar quebrados
Links estaticos para slugs CNAE especificos nao verificados dinamicamente.
Correcao proposta: Verificar slugs existem em CNAE_B2B ou gerar dinamicamente.

#233 [MEDIO] empresas_cidade.html — Falta link rel="prev"/"next" no head
Links de paginacao no body mas faltam tags no head.
Correcao proposta: Adicionar link rel="prev/next" no head.

#234 [MEDIO] empresas_cidade.html — Canonical em paginas paginadas
Paginas 2+ tem canonical apontando para pagina 1. Porem, paginas >1 ja sao noindex — implementacao consistente e correta.

#235-#236 [BAIXO] robots.txt — Falta bloquear /trial-expirado, /pagamento/*, /t/*
Paginas internas sem valor SEO nao bloqueadas.
Correcao proposta: Adicionar Disallow.

Resumo Bloco E: 0 CRITICO, 3 ALTO, ~13 MEDIO, ~11 BAIXO = 27 achados.

---

# BLOCO F — TEXTOS (Secao 14) + ACESSIBILIDADE (Secao 15) + UX (Secao 16) + LGPD (Secao 17) + OBSERVABILIDADE (Secao 18)

## Secao 14: Textos e Idioma

#250 [ALTO] templates/privacidade.html:6 — Titulo sem acentos
<title>Politica de Privacidade sem acentos. Mesmo problema no h1, meta description e skip-link.
Correcao proposta: Acentuar todas as ocorrencias.

#251 [ALTO] templates/privacidade.html:61-109 — Pagina inteira sem acentos
Mais de 30 palavras afetadas: "Ultima atualizacao", "Criacao", "Personalizacao", "Seguranca", "Execucao", "Cobranca", "Retencao", "sessao", "Voce", "configuracoes", "Alteracoes".
Correcao proposta: Corrigir acentuacao em toda a pagina.

#252 [ALTO] templates/termos.html:43-95 — Pagina inteira sem acentos
Mesma situacao: "Aceitacao", "Servico", "Descricao", "prospeccao", "inteligencia", "seguranca", "responsavel", "nao garante", "Alteracoes".
Correcao proposta: Corrigir acentuacao sistematica.

#253 [MEDIO] templates/404.html:6,31-36 — Pagina 404 sem acentos
"Pagina nao encontrada", "voce", "gratis".
Correcao proposta: Acentuar.

#254 [MEDIO] templates/blog.html:101,108,125-127 — Textos sem acento
"Estrategias de prospecao", "prospecao", "gratis", "automacao".
Correcao proposta: Corrigir.

#255 [MEDIO] templates/blog_post.html:145 — "Criar conta gratis" sem acento no CTA do nav
Correcao proposta: Acentuar.

#256 [MEDIO] templates/landing.html:384 — Skip-link com caracteres corrompidos UTF-8
"Pular para conte��o" — bytes quebrados.
Correcao proposta: Reescrever com encoding correto.

#257 [BAIXO] templates/landing.html:631 — Texto truncado
"A IA entende quem s seus compradores ideais." Falta "sao".
Correcao proposta: "quem sao seus compradores ideais".

#258 [BAIXO] templates/admin.html:488 — Texto em JS sem acentos
"usuario", "Voce", "sera" sem acentos.
Correcao proposta: Acentuar.

## Secao 15: Acessibilidade (a11y)

#259 [MEDIO] Nenhum label usa atributo for associado ao id do input
Afeta login.html, register.html, config.html. Leitores de tela nao associam label ao input.
Correcao proposta: Adicionar id em cada input e for correspondente em cada label.

#260 [MEDIO] templates/dashboard.html:3140 — Imagem QR code sem alt
Imagem gerada dinamicamente em JS nao possui atributo alt.
Correcao proposta: Adicionar alt="QR Code WhatsApp".

#261 [MEDIO] Botoes interativos sem aria-label
Icones de redes sociais no footer, botao fechar do exit-popup (apenas &times;), botoes de navegacao.
Correcao proposta: Adicionar aria-label descritivo.

#262 [MEDIO] templates/index.html:611,615 — Modal sem gerenciamento de foco
Falta role="dialog", aria-modal="true", gerenciamento de foco com JS.
Correcao proposta: Adicionar atributos ARIA e gerenciar foco.

#263 [BAIXO] templates/dashboard.html:849 — "Acao" sem acento em cabecalho de tabela
Correcao proposta: Corrigir para "Acao".

#264 [BAIXO] Skip-link ausente em 5 templates
segmento.html, empresas_hub.html, empresas_cnae.html, empresas_cidade.html, trial_expirado.html nao possuem skip-link.
Correcao proposta: Adicionar skip-link.

## Secao 16: UX e Navegacao

#266 [MEDIO] Navegacao inconsistente entre paginas
Cada pagina publica tem nav diferente. Nao ha componente nav reutilizado.
Correcao proposta: Extrair navbar para partial (_nav.html).
Risco da correcao: Medio.

#267 [MEDIO] Mobile: links escondidos sem menu hamburger
Em mobile, tudo exceto o CTA e escondido (display:none). Nao existe menu hamburger.
Correcao proposta: Implementar menu hamburger mobile.
Risco da correcao: Medio.

#270 [BAIXO] login.html, register.html — Sem validacao client-side alem de HTML5
Nao ha feedback visual inline antes do submit.
Correcao proposta: Adicionar validacao JS com mensagens inline.

## Secao 17: LGPD

#271 [CRITICO] Nenhum cookie consent banner — GA4 carrega sem consentimento
Google Analytics carregado INCONDICIONALMENTE em todas as paginas publicas. GA4 seta cookies (_ga, _gid) antes de qualquer consentimento. Viola LGPD (Art. 7, I) e diretiva ePrivacy.
Correcao proposta: Implementar cookie consent banner que bloqueia GA4 ate consentimento.
Risco da correcao: Medio.

#272 [ALTO] templates/privacidade.html — Politica de privacidade incompleta para LGPD
Falta: razao social/CNPJ do controlador (Art. 23), nome do DPO (Art. 41), transferencia internacional (Art. 33), tabela de retencao detalhada (Art. 9), revisao de decisoes automatizadas (Art. 20).
Correcao proposta: Completar a politica com todas as informacoes exigidas.

#273 [ALTO] app.py — Sem mecanismo de exclusao/exportacao de dados do usuario
Nao existe endpoint de delete account nem data export. A pagina de privacidade promete esses direitos (Art. 18) mas nao ha implementacao.
Correcao proposta: Implementar /api/minha-conta/excluir e /api/minha-conta/exportar.
Risco da correcao: Medio.

#274 [MEDIO] app.py — Sem rastreamento de consentimento
Texto "Ao criar uma conta voce concorda..." sem checkbox de aceite explicito. Nenhum campo accepted_terms_at no banco.
Correcao proposta: Adicionar checkbox obrigatorio e salvar timestamp.

#275 [MEDIO] register.html:10-11 — GA4 hardcoded em vez de variavel
Inconsistencia que dificulta centralizar controle de consentimento.
Correcao proposta: Usar {{ ga_id }} em todas as paginas.

## Secao 18: Observabilidade

#276 [ALTO] app.py:34 — Logging minimal e inconsistente
Logger Python declarado mas so usado em ~12 lugares. Maioria dos erros usa print('[ERR]...') (25+ ocorrencias). Sem configuracao de nivel, formato, ou handler.
Correcao proposta: Configurar logging.basicConfig. Substituir todos os print() por logger. Considerar python-json-logger.

#277 [ALTO] app.py:5173-5175 — Health check extremamente simplista
/health retorna apenas {'status': 'ok', 'version': '2.1'} sem checar PostgreSQL, memoria, ou processos.
Correcao proposta: Expandir para verificar conexao DB (SELECT 1) e uptime.

#278 [ALTO] app.py — Sem error tracking (Sentry ou similar)
Erros 500 logados localmente, sem notificacao externa. Erros silenciosos passam despercebidos.
Correcao proposta: Integrar sentry-sdk[flask].

#279 [MEDIO] app.py:143-147 — Error handler 500 renderiza 404.html
Mostra "Pagina nao encontrada" quando houve erro interno.
Correcao proposta: Criar template 500.html.

#280 [MEDIO] app.py — Sem metricas de aplicacao
Nenhum Prometheus, StatsD, Datadog. Sem contagem de requests, latencia, taxa de erro.
Correcao proposta: Integrar prometheus-flask-instrumentator.

#281 [MEDIO] app.py — Sem alertas configurados
Nenhuma integracao PagerDuty, OpsGenie, ou alertas do Railway.
Correcao proposta: Configurar alertas no Sentry quando integrado.

Resumo Bloco F: 1 CRITICO, 7 ALTO, ~14 MEDIO, ~7 BAIXO = 29 achados.

---

# BLOCO G — PAGAMENTOS (Secao 19) + PLANOS E TRIAL (Secao 20)

## Secao 19: Pagamentos (Mercado Pago)

#300 [CRITICO] app.py:6274-6311 — Cartao de credito transita pelo servidor — violacao PCI-DSS
/api/pagamento/cartao recebe card_number, cvv, expiration diretamente no JSON body. Dados em texto claro na memoria do processo Flask. Tokenizacao deveria ser feita no frontend via MercadoPago.js.
Correcao proposta: Frontend usa SDK JS do MP para gerar token. Backend recebe apenas card_token.
Risco da correcao: Medio.

#301 [ALTO] app.py:6162-6165 — Webhook nao e idempotente — pagamentos duplicados
Tabela pagamentos sem UNIQUE em mp_payment_id. INSERT sem verificacao de existencia. Cada reenvio do MP cria linha duplicada e reinicia contagem de 30 dias.
Correcao proposta: UNIQUE(mp_payment_id) + INSERT ON CONFLICT DO UPDATE.
Risco da correcao: Baixo.

#302 [ALTO] app.py:6207 — Idempotency key inclui timestamp — nao previne duplicatas
pix_{user_id}_{plano_id}_{int(time.time())} gera chave diferente a cada request. Clique duplo = duas cobrancas. Mesmo problema em cartao e boleto.
Correcao proposta: Remover timestamp da idempotency key.
Risco da correcao: Baixo.

#303 [ALTO] app.py:6188-6258, 6410-6481 — PIX e boleto nunca ativam plano diretamente
Endpoints PIX e boleto inserem em pagamentos mas NAO atualizam users.plano/plano_expira quando status == 'approved'. Ativacao so via webhook. PIX aprovado na hora nao ativa plano ate webhook chegar.
Correcao proposta: Se status == 'approved', executar UPDATE users SET plano.
Risco da correcao: Baixo.

#304 [ALTO] app.py:6172, 6370 — Pagamento avulso sem recorrencia, planos pagos nunca expiram
Cada pagamento seta plano_expira = NOW() + 30 days. Sem assinatura recorrente. _check_lead_limit so verifica expiracao para plano == 'trial'. Usuario pro com plano_expira no passado mantem acesso ilimitado para sempre.
Correcao proposta: Verificar plano_expira para TODOS os planos, ou implementar assinatura recorrente.
Risco da correcao: Medio.

#305 [MEDIO] app.py:6099-6185 — Webhook aceita qualquer payment_id sem validar pertinencia ao user
Sem verificacao extra de que o pagamento pertence ao usuario (email do pagador != email do user).
Correcao proposta: Verificar pay['payer']['email'] == email do user.

#306 [MEDIO] app.py:6155-6181 — Webhook abre conexao separada em vez de usar _conn()
Cria psycopg2.connect(DATABASE_URL) direto. Pode causar leak e inconsistencia.
Correcao proposta: Usar _conn() consistentemente.

#307 [MEDIO] app.py:6182-6184 — Excecao no webhook retorna 200
Se excecao ocorrer, retorna ok=True. MP nao retenta. Pagamento nunca registrado.
Correcao proposta: Retornar HTTP 500 no except.

#308 [MEDIO] app.py:6224-6240, 6354-6375 — Falha ao registrar pagamento nao impede resposta de sucesso
Se INSERT INTO pagamentos falhar, resposta ok=True ainda retorna. Pagamento criado no MP mas nao registrado localmente.
Correcao proposta: Logar com nivel CRITICAL. Considerar fila de retry.

#309 [MEDIO] — Nao ha endpoint de reembolso/estorno
Nenhuma rota de refund. Processo inteiramente manual via painel do MP.
Correcao proposta: Implementar /admin/api/refund/<payment_id>.

#310 [BAIXO] app.py:6009-6020 — Plano 'starter' definido mas nunca selecionavel
Defaults sao todos 'pro'. Verificar se frontend oferece opcao starter.
Correcao proposta: Verificar templates/JS.

## Secao 20: Planos e Trial

#311 [CRITICO] app.py:607-613 — Planos pagos (starter/pro) nunca expiram na pratica
_check_lead_limit so verifica expiracao quando plano == 'trial'. Usuarios pro com plano_expira no passado tem acesso ilimitado para sempre. api_meu_plano calcula 'ativo' mas e puramente informacional.
Correcao proposta: Verificar plano_expira para TODOS os planos em _check_lead_limit.
Risco da correcao: Medio.

#312 [ALTO] app.py:1030-1034 — Trial sem mecanismo de conversao automatica
Nao ha cron que mude status apos trial expirar. Plano continua 'trial' indefinidamente. _check_lead_limit bloqueia novas insercoes mas usuario ainda pode VER leads e usar dashboard.
Correcao proposta: Criar cron que seta ativo=FALSE ou status 'trial_expired'.

#313 [ALTO] app.py:583-633 — Verificacao de trial expirado nao e feita em todas as rotas
_check_lead_limit so chamada em add-lead e /api/v1/leads POST. Todas as outras rotas (enriquecer, email, sequencias, exportar CSV, etc.) NAO verificam trial expirado. Dashboard redireciona para /trial-expirado mas todas as APIs permanecem acessiveis.
Correcao proposta: Criar decorator @plan_active_required em todas as rotas que geram valor.
Risco da correcao: Medio.

#314 [ALTO] app.py:612 — Comparacao de datetime sem timezone pode falhar
datetime.now() (sem timezone) vs PostgreSQL NOW() (com timezone). Se servidor Python e banco estiverem em timezones diferentes, trial pode expirar 3 horas antes/depois.
Correcao proposta: Usar datetime.now(timezone.utc) e TIMESTAMPTZ.

#315 [MEDIO] app.py:178 — plano_expira pode ser NULL para usuarios antigos
ALTER TABLE ADD COLUMN com default NULL. Trial com plano_expira NULL nunca expira.
Correcao proposta: Migration para setar plano_expira = criado_em + 14 days WHERE NULL.

#316 [MEDIO] app.py:6707-6727 — Admin muda plano sem atualizar plano_expira
UPDATE users SET plano = %s sem setar plano_expira. Admin pro pode ter expiracao do trial antigo.
Correcao proposta: Setar plano_expira ao mudar plano via admin.

#317 [MEDIO] app.py:536-540 — Plano 'enterprise' sem fluxo de compra
Definido em PLAN_LEAD_LIMITS e PLAN_FEATURES mas nao em MP_PLANOS. Sem self-service.
Correcao proposta: Documentar como via admin/sales ou adicionar preco.

#318 [MEDIO] app.py:536-541 — Limite de leads nao verificado em busca automatica
_check_lead_limit chamada apenas em add-lead manual. Busca automatica pode inserir sem verificacao.
Correcao proposta: Verificar todas as rotas que fazem INSERT INTO empresas.

#319 [MEDIO] app.py:1026-1028 — Registro permite enumerar emails cadastrados
"Email ja cadastrado" permite enumerar emails. Sem rate-limit no registro.
Correcao proposta: Mensagem generica + rate-limit agressivo.

#320 [BAIXO] app.py:6484-6497 — Pagina de resultado do pagamento nao verifica status real
/pagamento/sucesso acessivel sem ter pago. Apenas informativa mas pode confundir.
Correcao proposta: Verificar pagamento real antes de exibir.

#321 [BAIXO] app.py:6897-6909 — Token do cron via query param (duplica #80)
Token na URL aparece em logs.
Correcao proposta: Aceitar apenas via header.

#322 [BAIXO] app.py:2569-2587 — /trial-expirado acessivel sem trial expirado
Redireciona para dashboard se nao expirado, mas renderiza stats quando expirado.

Resumo Bloco G: 2 CRITICO, 7 ALTO, 10 MEDIO, 4 BAIXO = 23 achados.

---

# BLOCO H — REVISAO FINAL (Secao 21)

## Achados duplicados entre blocos (dedup)

| Achado original | Duplicata | Descricao |
|-----------------|-----------|-----------|
| #68 (B) | #101 (C) | IndexNow key hardcoded |
| #69 (B) | #300 (G) | Dados de cartao no servidor (PCI-DSS) |
| #81 (B) | #103 (C) | Emails hardcoded para plano pro |
| #80 (B) | #321 (G) | Cron token via query string |
| #124 (C) | #14 (A) | Schema duplicado _init_public_schema |
| #125 (C) | #50 (A) | bot_config duplicado |
| #304 (G) | #311 (G) | Planos pagos nunca expiram |
| #200 (E) | #275 (F) | GA hardcoded em register.html |

Apos dedup: ~222 achados unicos.

## Verificacao de consistencia

- Todos os achados CRITICO e ALTO possuem file:line verificado
- Achados de index.html (#1-#5, #20) referem-se ao template legado; se descontinuado, podem ser rebaixados
- Achados de LGPD (#271-#275) sao inegociaveis independente de estagio
- Achados de PCI-DSS (#69/#300) sao inegociaveis — corrigir ANTES de qualquer deploy

## Ordem de correcao recomendada

**Fase 2A — Piso de seguranca (ANTES de expor):**
1. PCI-DSS: tokenizacao client-side do cartao (#69/#300)
2. LGPD: cookie consent banner (#271)
3. LGPD: completar politica de privacidade (#272)
4. Config apaga credenciais: merge de campos (#15)
5. Indices criticos: email_track_token, agenda_token (#35/#36)
6. Connection pooling (#166)
7. SECRET_KEY obrigatoria (#71)

**Fase 2B — Integridade funcional:**
8. Planos pagos: verificar expiracao para todos (#311/#304)
9. Trial: bloquear APIs alem de add-lead (#313)
10. Webhook idempotente (#301)
11. PIX/boleto: ativar plano no response (#303)
12. Connection leaks: context manager (#54-#57, #134)
13. Error handling consistente (#132/#133)

**Fase 2C — Qualidade e UX:**
14. Acentuacao em paginas legais (#251/#252)
15. Logging estruturado (#276/#130)
16. Health check completo (#277)
17. Error tracking — Sentry (#278)
18. Testes minimos (#179/#180)
19. CI/CD basico (#184)
20. Navbar consistente (#266), mobile menu (#267)

---

> **FASE 1 CONCLUIDA. Nenhum codigo foi alterado.**
> Aguardando autorizacao explicita para iniciar FASE 2 (correcoes).
