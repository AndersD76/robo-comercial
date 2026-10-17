# Tráfego — o que foi feito e o que você faz agora

## Diagnóstico (o mínimo)
O site já tinha ~8.300 páginas de empresas com dados da Receita, mas quase não recebia visita. Três travas:
1. **Servidor em fila.** Um processo síncrono atendia uma requisição por vez, e a cada 15 min um visitante esperava a contagem de 6,7 milhões de CNPJs (~9 s). A home foi medida em **18,9 s**, e o Google rebaixa site lento e rastreia menos.
2. **Sinais ruins para o Google.** O `lastmod` dizia "hoje" em tudo, o `/login` estava no sitemap apesar de ser `noindex`, post inexistente redirecionava em vez de dar 404, e o domínio `*.up.railway.app` servia conteúdo duplicado.
3. **Nada que puxasse visita além das listas.** Não havia ferramenta, guia de problema/solução, comparativo nem distribuição.

## O que foi implementado (commits)
| Commit | O quê |
|---|---|
| `ed0aa99` seo: destravar indexação | gunicorn com 8 threads; contagens em visões materializadas, recarregadas em segundo plano; `lastmod` real; `/login` fora do sitemap; 404 de verdade; 301 do `*.railway.app` e do domínio sem www para o www; IndexNow automático a cada deploy (só URLs novas ou alteradas); `contexto.md` |
| `61e4519` seo: páginas de estado e de cidade | `/empresas/<segmento>/estado/<uf>` (666) e `/empresas/cidade/<cidade-uf>` (1.135), com dados reais; página do segmento passa a ser nacional; 4 links quebrados corrigidos em todos os posts |
| `dfa9264` feat: ferramentas gratuitas | `/ferramentas/lista-de-empresas`, `/ferramentas/gerador-de-mensagem-de-prospeccao` (IA), `/ferramentas/calculadora-de-leads` e o hub; nomes oficiais (IBGE) das cidades e "em Santa Catarina"/"na Bahia" |
| `967f06a` conteudo: 12 guias | um guia por busca do ICP, cada um terminando numa ferramenta e no cadastro |
| `f667324` conteudo: comparativos | `/alternativas` + Econodata, Speedio, Leads2b e Apollo, com fonte e data |
| `b1bd849` seo: linkagem interna | landing, preços, blog e segmentos linkam as páginas novas; saem os números sem fonte da landing |
| `42fb0ae` docs: kit de distribuição | `distribuicao/` — LinkedIn, diretórios, WhatsApp, outbound e Shorts |
| `1f81376` + `0490690` medição | tabelas `pageviews` e `cta_cliques` e a rota `/admin/trafego` |

**Antes x depois (URLs no sitemap):**

| | Antes | Depois |
|---|---|---|
| Páginas fixas, blog, segmentos, ferramentas, comparativos | 33 (com `/login`) | 53 |
| Páginas de empresas (segmento, estado, cidade, segmento × cidade) | 8.287 | 10.086 |
| **Total** | **~8.320** | **~10.140** |

**Páginas indexáveis novas: 1.822** — 666 de estado, 1.135 de cidade, 12 guias, 4 de ferramentas e 5 de comparativos.

## ✅ Checklist — só VOCÊ pode fazer (em ordem)

**Dia 1 (≈1 h 30)**
1. [ ] **Colocar no ar** (5 min). Os commits estão no `master` local; o push dispara o deploy no Railway. Depois do deploy, confira `https://www.turbovenda.com.br/ferramentas`.
2. [ ] **Domínio sem www** (30–40 min + propagação). `https://turbovenda.com.br` não resolve no DNS. O app já redireciona para o www, falta o DNS:
   - No Railway: serviço `robo-comercial` → Settings → Networking → **Custom Domain** → adicionar `turbovenda.com.br`. Ele mostra o destino do CNAME.
   - No DNS do domínio: apontar a raiz (`@`) para esse destino. O Registro.br não aceita CNAME na raiz; se o DNS estiver lá, passe o DNS para o Cloudflare (grátis), que faz o "CNAME flattening", e crie `@` → destino do Railway como "DNS only".
3. [ ] **Google Search Console** (20 min) — https://search.google.com/search-console
   - Reenvie o sitemap `https://www.turbovenda.com.br/sitemap.xml`.
   - Em "Inspeção de URL", peça indexação destas 10 (o limite é de ~10 por dia): `/`, `/ferramentas`, `/ferramentas/lista-de-empresas`, `/ferramentas/gerador-de-mensagem-de-prospeccao`, `/ferramentas/calculadora-de-leads`, `/alternativas/econodata`, `/empresas/cidade/porto-alegre-rs`, `/empresas/cidade/curitiba-pr`, `/blog/lista-de-empresas-por-cidade`, `/blog/mensagem-de-prospeccao-whatsapp`.
4. [ ] **Bing Webmaster Tools** (10 min) — https://www.bing.com/webmasters → "Importar do Google Search Console". O IndexNow já avisa o Bing sozinho a cada deploy.
5. [ ] **Página da empresa no LinkedIn** (15 min) — é a base dos posts de `distribuicao/linkedin.md`.

**Semana 1 (≈2 h no total)**
6. [ ] **Os 5 diretórios ⭐** de `distribuicao/diretorios.md` (LinkedIn, Google Business Profile — só se a AndersTech atende presencialmente —, B2B Stack, G2 e o portal da indústria da FIERGS). As descrições curta e longa já estão prontas. ~15 min cada.
7. [ ] **Conferir as variáveis no Railway** (5 min): `ANTHROPIC_API_KEY` (já existe; é o que faz o gerador usar IA) e, se quiser outro teto diário de uso da IA no gerador público, `GERADOR_LIMITE_DIA` (padrão: 300 por dia).
8. [ ] **Pedir indexação de mais 10 URLs por dia** no Search Console, durante uma semana — páginas de cidade e de estado das regiões onde você mais vende.

## 📅 Rotina diária de 30 min (4 semanas)

| Dia | O que fazer (30 min) |
|---|---|
| **Segunda** | Escolher os 3 posts da semana em `linkedin.md` (5 min) · publicar o 1º, com o link no primeiro comentário (10 min) · cadastrar 1 diretório de `diretorios.md` (15 min) |
| **Terça** | 10 mensagens de prospecção de `outbound.md` (e-mail ou WhatsApp), sempre com o link da ferramenta grátis (20 min) · responder comentários do post (10 min) |
| **Quarta** | Publicar o 2º post (10 min) · 1 mensagem num grupo de WhatsApp diferente, de `whatsapp-grupos.md`, pedindo antes ao admin (10 min) · responder quem comentou ou respondeu (10 min) |
| **Quinta** | Mais 10 mensagens de outbound — os follow-ups da sequência entram aqui (20 min) · 1 diretório (10 min) |
| **Sexta** | Publicar o 3º post (10 min) · abrir `/admin/trafego` e anotar entradas, origens e cliques da semana (10 min) · da semana 2 em diante: gravar 1 Short de `youtube-shorts.md` (10 min de gravação; edite no fim de semana se precisar) |

**Foco de cada semana**
- **Semana 1:** destravar (checklist acima) e posts 1–3. Meta: as primeiras visitas com `utm_source=linkedin` aparecendo no `/admin/trafego`.
- **Semana 2:** posts 4–6, os 5 diretórios ⭐ concluídos e o 1º Short. Olhe quais páginas de cidade recebem entrada pelo Google.
- **Semana 3:** posts 7–9 e mais 5 diretórios. Dobre o outbound no segmento que mais clicou na ferramenta (aparece em "Campanhas" e "Cliques em CTA").
- **Semana 4:** posts 10–12, mais 2 Shorts. Compare as 4 semanas: qual canal trouxe cadastro? Para o mês seguinte, fique com os 2 melhores e corte o resto.

## Onde ver a visita
- **`/admin/trafego`** (entre por `/admin` com a `ADMIN_KEY`): entradas, páginas vistas, cliques em CTA e robôs por dia; páginas mais vistas; origem (UTM ou site de referência); campanhas; cliques por página. Dá para trocar entre 7, 30 e 90 dias.
- **GA4** (`G-NGSNSF3SPM`) — só carrega com o consentimento de cookies, por isso conta menos que o `/admin/trafego`.
- **Search Console** — impressões e cliques no Google (os primeiros números das páginas novas levam de 1 a 4 semanas).

## Pendências mapeadas (não bloqueiam, mas rendem)
- **Posts antigos com número sem fonte.** Alguns dos 18 posts anteriores citam estatísticas sem referência ("35% de abertura", "80% dos leads B2B", "62% menor"). Vale revisar ou tirar — os 12 guias novos não têm isso.
- **Bairros sem acento** ("Sao Cristovao") nas listas: é como a Receita grava. As cidades já foram corrigidas com o IBGE.
- **Consent Mode v2 e Microsoft Clarity** não estão instalados (o relatório de out/2026 já apontava).
- **Dados da Receita:** ao rodar uma nova ingestão (`scripts/cnpj_ingest.py`), o script já atualiza as visões materializadas no final; o app relê em até 6 h (ou no próximo deploy).
- **Escopo das páginas de empresas:** usam 50 CNAEs B2B (`pseo_data.py`). A base tem 1.314 CNAEs; incluir mais segmentos multiplica as páginas, mas exige o nome de cada CNAE.
