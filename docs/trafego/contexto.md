# Contexto de tráfego — TurboVenda

## O que o app faz (5 linhas)
1. SaaS de prospecção B2B: o cliente descreve o que vende e a IA (Claude) gera os termos de busca de quem compra.
2. Um robô encontra empresas (buscadores + base de 6,7 milhões de CNPJs ativos da Receita) e coleta telefone, e-mail, site e decisor.
3. Tudo cai num CRM com Kanban (Novo → Contactado → Respondeu → Qualificado → Demo → Convertido).
4. A IA escreve a abordagem de e-mail e WhatsApp; há envio em massa, sequências e agendamento.
5. Planos: Grátis (50 leads, sem cartão), Starter R$ 97/mês, Pro R$ 297/mês — pagamento avulso por 30 dias (Mercado Pago).

## ICP concreto
- **Cargo:** dono/sócio de PME B2B que vende sozinho ou com 1–5 vendedores; gerente comercial; representante comercial autônomo.
- **Setor:** quem vende para outras empresas — indústria (metalurgia, embalagens, confecção, automação), distribuidoras e atacado, serviços B2B (prevenção de incêndio, segurança do trabalho, certificação, contabilidade, TI/software, agências), representações.
- **Porte:** 2 a 50 funcionários, sem time de pré-vendas (SDR) nem verba para base de dados cara.
- **Região:** Sul primeiro (RS, SC, PR — onde a base da Receita e os cadastros atuais estão mais fortes: Porto Alegre, Curitiba, Florianópolis, Passo Fundo); depois Brasil.
- **Dor principal:** não tem lista de clientes potenciais. Perde horas garimpando empresa no Google e CNPJ por CNPJ, o vendedor fica sem lead e a prospecção para.
- **Ação de conversão:** criar conta grátis com 50 leads, sem cartão — `/cadastro`.

## 20 buscas reais do ICP (pt-BR, linguagem do cliente)
1. lista de empresas por cidade
2. lista de empresas por cnae
3. empresas em [cidade] (ex.: empresas em Passo Fundo) — coberto pelas páginas `/empresas/cidade/*`
4. [segmento] em [cidade] (ex.: metalúrgicas em Caxias do Sul) — coberto por `/empresas/*/*`
5. como conseguir lista de clientes b2b
6. como prospectar clientes b2b
7. como encontrar clientes para minha empresa
8. onde conseguir contato de empresas
9. base de dados de empresas cnpj
10. mailing de empresas grátis
11. mensagem de prospecção whatsapp pronta
12. modelo de e-mail de prospecção b2b
13. como fazer prospecção ativa
14. quantos leads preciso para bater a meta de vendas
15. como montar uma lista de prospecção
16. ferramenta de prospecção b2b
17. alternativa ao econodata / econodata vale a pena
18. como conseguir clientes sendo representante comercial
19. como vender para indústrias
20. follow-up de vendas: quantas vezes insistir

## Ativos que já existiam antes desta rodada
- ~8.300 páginas `/empresas/{segmento}/{cidade}` com dados reais da Receita, 19 posts no blog, 6 páginas `/para/{segmento}`, sitemap, robots, llms.txt, chave IndexNow.
- Base `empresas_publicas`: 6.739.551 CNPJs ativos, 5.572 cidades, 1.314 CNAEs, 27 UFs (mais forte em PR, RS, SC e SP).

## Gargalos encontrados (o mínimo pra agir)
- Servidor com 1 processo síncrono: uma requisição pesada (agregação de 6,7 mi de linhas a cada 15 min, feita dentro da requisição do visitante) segurava todas as outras — home medida em 18,9 s.
- `https://turbovenda.com.br` (sem www) não resolve no DNS.
- `lastmod` = "hoje" em quase todo o sitemap (o Google passa a ignorar), `/login` no sitemap, post inexistente redireciona em vez de dar 404.
- Domínio `*.up.railway.app` servindo o mesmo conteúdo (duplicado).
- Ping de sitemap do Google (desativado pelo Google em 2023) e IndexNow só manual.
