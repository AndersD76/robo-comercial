# Pesquisa SERP — TurboVenda (08/11/2026)

## Como esta pesquisa foi feita (leia antes)

- **Ferramenta:** busca web do agente (WebSearch). O índice fica nos EUA e **não é o Google Brasil**. A "posição" abaixo é a ordem em que a ferramenta devolveu os resultados, não o ranking real do Google.br.
- **Dois índices diferentes:** o modo "standard" e o modo "extended" devolveram resultados bem diferentes. O "extended" parece mais novo e mais brasileiro. Usei "standard" em todas as 20 consultas e repeti em "extended" em 13: em 7 porque o resultado veio fraco ou fora do Brasil (1, 2, 4, 5, 10, 17, 18) e em 6 para ver se a TurboVenda aparecia num índice mais novo (3, 9, 11, 14, 16, 20). Quando os dois existem, mostro os dois lado a lado.
- **"As pessoas também perguntam" (PAA):** a ferramenta **não mostra** esse bloco nem as buscas relacionadas. Em cada consulta listo 2–3 perguntas **inferidas** a partir dos títulos dos resultados, marcadas como "(inferido)".
- **Volume relativo:** **estimativa minha**, baseada em quantos e quais sites disputam a consulta. **Não é dado medido.** Nenhum número de volume foi inventado.
- **Presença da TurboVenda:** além das 20 consultas, busquei `site:turbovenda.com.br` e `turbovenda prospecção` no modo standard: **nenhuma página do domínio apareceu** (indício de que esse índice não tem o site).
- **O que a TurboVenda já tem no código** (conferido só lendo `app.py`, `conteudo_guias.py` e `conteudo_alternativas.py`; **não verifiquei se está no ar nem indexado**): `/ferramentas/lista-de-empresas`, `/ferramentas/gerador-de-mensagem-de-prospeccao`, `/ferramentas/calculadora-de-leads`, `/empresas/<cnae>/<cidade>`, `/empresas/cidade/<cidade>`, `/empresas/<cnae>/estado/<uf>`, `/alternativas/{econodata,speedio,leads2b,apollo}` e guias em `/blog/` (lista-de-empresas-por-cidade, base-de-dados-de-empresas-cnpj, mailing-de-empresas, mensagem-de-prospeccao-whatsapp, como-fazer-prospeccao-ativa, quantos-leads-preciso-para-bater-a-meta, como-montar-lista-de-prospeccao, como-conseguir-clientes-representante-comercial, como-vender-para-industrias, follow-up-de-vendas, o-que-e-cnae-prospeccao, como-encontrar-o-decisor-da-empresa).

Legenda de formato: **ferramenta/consulta**, **lista/diretório**, **guia/blog**, **comparativo**, **página de produto**, **vídeo**, **fórum**, além de **notícia**, **PDF/acadêmico** e **outro** quando nada encaixa.

---

## 1. lista de empresas por cidade

| Pos | Standard | Formato | Extended | Formato |
|---|---|---|---|---|
| 1 | empresaqui.com.br (FAQ) | guia/blog | empresaqui.com.br/listas-de-empresas | lista/diretório |
| 2 | companexia.com (Reino Unido) | lista/diretório | pesquisaempresas.com.br/blog | guia/blog |
| 3 | companexia.com (Reino Unido) | lista/diretório | disparoemassa.com.br/blog | guia/blog |
| 4 | companexia.com (Reino Unido) | lista/diretório | cnpjdata.com.br/lista-de-empresas | página de produto |
| 5 | companexia.com (Reino Unido) | lista/diretório | **turbovenda.com.br/ferramentas/lista-de-empresas** | ferramenta/consulta |
| 6 | companexia.com (EUA) | lista/diretório | listasdeempresa.com | página de produto |
| 7 | companexia.com (EUA) | lista/diretório | leadjet.com.br/lista-de-empresas-por-cidade | lista/diretório |
| 8 | companexia.com (Reino Unido) | lista/diretório | infoempresas.com.pt | lista/diretório |
| 9 | companexia.com (Irlanda) | lista/diretório | cnpj.biz/blog | guia/blog |

(Standard depois: baguete.com.br [notícia], aonca.com.br, einforma.co [Colômbia, diretório], vocepergunta.com [fórum].)

| Campo | Valor |
|---|---|
| Formato dominante | lista/diretório + ferramenta de contagem/download |
| Intenção | transacional (comercial) com recorte local |
| PAA | (inferido) Como achar lista de empresas de uma cidade de graça? · Quantas empresas tem na minha cidade? · Como baixar lista de empresas com telefone? |
| TurboVenda | **Sim — posição 5 no extended** (ferramenta). Não aparece no standard. |
| Concorrentes conhecidos | nenhum (EmpresAqui, LeadJet, CNPJ.biz, CNPJData são os rivais reais) |
| Página necessária | Ferramenta que já existe + hub por cidade com contagem por segmento e amostra grátis; ganhar indexação no Google.br |
| Volume (estimado) | alta |
| Dificuldade | média — vendedores de dados disputam, mas a TurboVenda já entra no top 5 de um índice |

## 2. lista de empresas por cnae

| Pos | Standard | Formato | Extended | Formato |
|---|---|---|---|---|
| 1 | empresaqui.com.br/blog (categoria CNAE) | guia/blog | apify.com/rowfinch (Brazil CNPJ leads) | ferramenta/consulta |
| 2 | empresaqui.com.br/blog (30 CNAEs) | guia/blog | empresaqui.com.br | página de produto |
| 3 | empresaqui.com.br/blog | guia/blog | exittus.com.br/blog | guia/blog |
| 4 | static.poder360.com.br (PDF) | lista/diretório | salario.com.br/empresas | lista/diretório |
| 5 | ine.es (Espanha) | outro (estatística) | pcontrol.com.br/tabela-cnae | lista (de códigos) |
| 6 | einforma.com (Espanha, 5x) | lista/diretório | leadcnpj.com.br/empresas-por-cnae | página de produto |
| 7 | pontotel.com.br/cnae | guia/blog | triceleads.com/lista-de-empresas-por-cnae | página de produto |
| 8 | jornalcontabil.com.br | guia/blog | leadjet.com.br/empresas-por-cnae | ferramenta/consulta |
| 9 | apify.com/brasildados (2x), socialhub.pro/blog, fiscal.io | ferramenta / guia | cnpj.biz/lista-de-empresas | página de produto |

| Campo | Valor |
|---|---|
| Formato dominante | página de produto / ferramenta de filtro por CNAE |
| Intenção | transacional |
| PAA | (inferido) Como filtrar empresas por CNAE de graça? · Onde ver a tabela CNAE completa? · Como baixar empresas por CNAE e cidade? |
| TurboVenda | Não (tem `/empresas/<cnae>` e `/empresas/<cnae>/<cidade>` no código) |
| Concorrentes conhecidos | nenhum (EmpresAqui, LeadJet, LeadCNPJ, Triceleads, CNPJ.biz, Apify) |
| Página necessária | Página programática por CNAE com contagem por UF/cidade, amostra grátis e botão "baixar lista" |
| Volume (estimado) | média |
| Dificuldade | média — muitos vendedores pequenos entram, nenhum domina sozinho |

## 3. empresas em passo fundo

| Pos | Standard | Formato | Extended | Formato |
|---|---|---|---|---|
| 1 | empresaqui.com.br/listas-de-empresas/RS/PASSO_FUNDO/vera_cruz | lista/diretório | empresaqui.com.br/listas-de-empresas/RS/PASSO_FUNDO | lista/diretório |
| 2 | jornaldocomercio.com | notícia | empresaqui.com.br (…/centro) | lista/diretório |
| 3 | directd.com.br/cnpj/estado/rs/passo-fundo | lista/diretório | empresaqui.com.br (…/sao_cristovao) | lista/diretório |
| 4 | baguete.com.br | notícia | en.wikipedia.org (clube) | outro |
| 5 | econodata.com.br/empresas/rs-passo-fundo | lista/diretório | en.wikipedia.org (aeroporto) | outro |
| 6 | cps.fgv.br (PDF) | PDF/acadêmico | econodata.com.br/empresas/rs-passo-fundo/grande | lista/diretório |
| 7 | applocal.com.br | lista/diretório | econodata.com.br/maiores-empresas/… | lista/diretório (ranking) |
| 8 | econodata.com.br/…/construcao-de-edificios | lista/diretório | econodata.com.br/maiores-empresas/… | lista/diretório (ranking) |

| Campo | Valor |
|---|---|
| Formato dominante | lista/diretório programático (cidade, bairro, porte) |
| Intenção | local (com parte navegacional; a consulta também pode ser de quem procura emprego) |
| PAA | (inferido) Quais as maiores empresas de Passo Fundo? · Quantas empresas tem em Passo Fundo? · Quais indústrias tem em Passo Fundo? |
| TurboVenda | Não (tem `/empresas/cidade/<cidade>` no código) |
| Concorrentes conhecidos | **Econodata** (3 posições no extended) |
| Página necessária | Página da cidade com dados próprios: total de ativas, top segmentos, maiores por porte, bairros e lista grátis |
| Volume (estimado) | média |
| Dificuldade | média — dominado por EmpresAqui e Econodata, mas é cauda longa e cada cidade é uma disputa nova |

## 4. metalúrgicas em caxias do sul

| Pos | Standard | Formato | Extended | Formato |
|---|---|---|---|---|
| 1 | vermelho.org.br (sindicato) | notícia | starofservice.com.br (metalurgia Caxias) | lista/diretório |
| 2 | vermelho.org.br | notícia | en.wikipedia.org (clube) | outro |
| 3 | vermelho.org.br | notícia | en.wikipedia.org (diocese) | outro |
| 4 | vermelho.org.br | notícia | ryvametalurgica.com.br | site de empresa |
| 5 | vermelho.org.br | notícia | en.wikipedia.org (cidade) | outro |
| 6 | vermelho.org.br | notícia | en.wikipedia.org (museu) | outro |
| 7 | radiocaxias.com.br | notícia | en.wikipedia.org (RBS TV) | outro |
| 8 | eventos.udesc.br | PDF/acadêmico | flmetalurgica.com.br | site de empresa |
| 9 | **empresaqui.com.br/empresas/metalurgia/rs/caxias-do-sul** | lista/diretório | — | — |

(No standard também aparecem autodata.com.br [notícia], dunsguide.com e village.do [perfis de empresa].)

| Campo | Valor |
|---|---|
| Formato dominante | notícia (sindicato) — sem página que responda à busca |
| Intenção | local |
| PAA | (inferido) Quais as maiores metalúrgicas de Caxias do Sul? · Quantas metalúrgicas tem em Caxias? · Metalúrgicas em Caxias com telefone? |
| TurboVenda | Não (tem `/empresas/<cnae>/<cidade>` no código) |
| Concorrentes conhecidos | nenhum (só EmpresAqui, com uma página fraca que mostra "24" empresas) |
| Página necessária | Página programática "metalurgia + Caxias do Sul" com contagem real pela base da Receita, maiores empresas e lista grátis |
| Volume (estimado) | baixa |
| Dificuldade | **baixa** — resultados fracos e fora do assunto; só a EmpresAqui tem página dedicada |

## 5. como conseguir lista de clientes b2b

| Pos | Standard (só sites em inglês) | Formato | Extended | Formato |
|---|---|---|---|---|
| 1 | kaspr.io/blog | guia/blog | blog.mercos.com | guia/blog |
| 2 | fiverr.com (serviço) | outro (freelancer) | accountbasedmarketing.com.br | guia/blog |
| 3 | b2brocket.ai | guia/blog | ventasdealtooctanaje.com (ES) | guia/blog |
| 4 | b2brocket.ai | guia/blog | exactsales.com.br/lista-de-clientes | guia/blog |
| 5 | g2.com (discussão) | fórum | esperanda.com (ES) | guia/blog |
| 6 | scottsdirectories.com | guia/blog | paulvillalobos.com (ES) | guia/blog |
| 7 | callboxinc.com | guia/blog | leadcanvas.app (ES) | guia/blog |
| 8 | scottsdirectories.com (amp) | guia/blog | en.wikipedia.org | outro |

| Campo | Valor |
|---|---|
| Formato dominante | guia/blog |
| Intenção | informacional (com interesse comercial) |
| PAA | (inferido) Onde comprar lista de clientes B2B? · É legal comprar lista de contatos (LGPD)? · Como montar lista de leads de graça? |
| TurboVenda | Não (tem o guia `como-montar-lista-de-prospeccao`) |
| Concorrentes conhecidos | nenhum |
| Página necessária | Guia em português, prático, "de onde tirar a lista" (Receita, Google Maps, indicação, ferramenta) com chamada para a ferramenta grátis |
| Volume (estimado) | baixa |
| Dificuldade | **baixa** — resultados bagunçados, quase sem guia brasileiro forte |

## 6. como prospectar clientes b2b

| Pos | Domínio | Formato |
|---|---|---|
| 1 | zenvia.com/blog | guia/blog |
| 2 | agendor.com.br/blog | guia/blog |
| 3 | agendor.com.br/blog | guia/blog |
| 4 | ideianoar.com.br | guia/blog |
| 5 | empresaqui.com.br/blog | guia/blog |
| 6 | agendor.com.br/blog | guia/blog |
| 7 | empresaqui.com.br/blog | guia/blog |
| 8 | empresaqui.com.br (e-book) | guia (material rico) |

(Depois: lagrowthmachine.com/pt, youtubesummary.com [vídeo resumido], startupi.com.br, zoho.com/blog.)

| Campo | Valor |
|---|---|
| Formato dominante | guia/blog |
| Intenção | informacional |
| PAA | (inferido) Quais os tipos de prospecção B2B? · Qual o melhor canal para prospectar B2B? · Como achar o decisor? |
| TurboVenda | Não |
| Concorrentes conhecidos | nenhum (Agendor e EmpresAqui ocupam 6 das 8 primeiras posições) |
| Página necessária | Guia definitivo de PME (indústria, distribuidor, representante) com passo a passo, modelos e calculadora embutida |
| Volume (estimado) | alta |
| Dificuldade | **alta** — dominado por Agendor, EmpresAqui e Zenvia, com muitos artigos cada |

## 7. como encontrar clientes para minha empresa

| Pos | Domínio | Formato |
|---|---|---|
| 1 | meetgeek.ai/pt-br/blog | guia/blog |
| 2 | clickup.com/pt-BR/blog | guia/blog |
| 3 | appbrasil.org.br | guia/blog (artigo) |
| 4 | brand24.com/blog/pt | guia/blog |
| 5 | agendor.com.br/blog | guia/blog |
| 6 | agendor.com.br/blog | guia/blog |
| 7 | jornalcontabil.com.br | guia/blog |
| 8 | invoicexpress.com (PT-PT) | guia/blog |

(Depois: lagrowthmachine, waalaxy, empresaqui, actana, santander.com.br, zoho, contaazul.com.)

| Campo | Valor |
|---|---|
| Formato dominante | guia/blog |
| Intenção | informacional (ampla, pega B2C também) |
| PAA | (inferido) Como atrair clientes sem gastar? · Onde encontrar clientes em potencial? · Como conseguir clientes pelo Instagram? |
| TurboVenda | Não |
| Concorrentes conhecidos | nenhum |
| Página necessária | Guia focado em "empresa que vende para empresa" — muito genérico para a TurboVenda brigar agora |
| Volume (estimado) | alta |
| Dificuldade | **alta** — grandes marcas (ClickUp, Santander, Conta Azul) e assunto que não é só B2B |

## 8. onde conseguir contato de empresas

| Pos | Domínio | Formato |
|---|---|---|
| 1 | empresaqui.com.br/blog | guia/blog |
| 2 | apify.com/brasildados | ferramenta/consulta |
| 3 | digitei.com (lista de SAC) | lista/diretório |
| 4 | empresaqui.com.br/blog | guia/blog |
| 5 | workana.com (pedido de freelancer) | outro |
| 6 | cigam.com.br/wiki | outro (manual de ERP) |
| 7 | forbes.es (contatos de empresas na Espanha) | lista/diretório |
| 8 | salt-django.crmcloud.infor.com | outro |

(Depois: zoominfo.com, digitei.com 2x, reclameaqui.com.br/compare, hotmart.com [lista de 14 milhões de contatos à venda].)

| Campo | Valor |
|---|---|
| Formato dominante | misto (guia/blog + listas de telefone de SAC) |
| Intenção | ambígua: informacional (parte quer o SAC de grandes marcas, parte quer prospectar) |
| PAA | (inferido) Como encontrar o telefone de uma empresa pelo CNPJ? · Como achar o e-mail de uma empresa? · Onde conseguir contatos para prospecção? |
| TurboVenda | Não |
| Concorrentes conhecidos | nenhum |
| Página necessária | Guia "como achar telefone, e-mail e WhatsApp de empresas para prospectar" + busca grátis por nome/CNPJ |
| Volume (estimado) | média |
| Dificuldade | **baixa** — resultados misturados, nenhuma página dedicada forte |

## 9. base de dados de empresas cnpj

| Pos | Standard | Formato | Extended | Formato |
|---|---|---|---|---|
| 1 | empresaqui.com.br/blog | guia/blog | blog.curso-r.com (2019) | guia/blog (tutorial) |
| 2 | workana.com | outro | github.com/rictom/rede-cnpj | ferramenta (código aberto) |
| 3 | glama.ai (MCP CNPJ) | ferramenta (código) | dadosabertos.social | fórum |
| 4 | rdrr.io (pacote R) | ferramenta (código) | cnpjbase.com.br | página de produto |
| 5 | datasebrae.com.br (PDF) | PDF/acadêmico | growmap.com.br/base-cnpj | página de produto |
| 6 | directd.com.br/cnpj | página de produto (API) | cnpjdata.com.br/dados-cnpj | página de produto |
| 7 | idealsoftwares.com.br | outro | tamz.ai/base-de-dados-empresas | página de produto |
| 8 | docs.cnpj.ws | página de produto (API) | basecnpj.com.br | página de produto |
| 9 | apify.com (2x), tabnews, toexceed | ferramenta / guia | **econodata.com.br/consulta-empresa** | ferramenta/consulta |

| Campo | Valor |
|---|---|
| Formato dominante | página de produto (venda de base) + recurso técnico (dados abertos) |
| Intenção | transacional, com um grupo técnico (desenvolvedores) |
| PAA | (inferido) Como baixar a base de CNPJ da Receita? · Base de CNPJ grátis existe? · Qual a base de empresas mais atualizada? |
| TurboVenda | Não (tem o guia `base-de-dados-de-empresas-cnpj`) |
| Concorrentes conhecidos | **Econodata** (extended, pos 9) |
| Página necessária | Página "base de empresas CNPJ" com números da base própria (6,7 mi ativas), data de atualização, filtros e amostra grátis |
| Volume (estimado) | média |
| Dificuldade | média — muitos vendedores de base e projetos técnicos, nenhum dominante |

## 10. mailing de empresas grátis

| Pos | Standard | Formato | Extended | Formato |
|---|---|---|---|---|
| 1 | infoautonomos.com (ES) | guia/blog | lanzadigital.com (ES) | guia/blog |
| 2 | sourceforge.net | página de produto | cyberclick.es (ES) | comparativo |
| 3 | bbcdigital.com.au | página de produto | infoautonomos.com (ES) | guia/blog |
| 4 | letterstream.com | página de produto | brevo.com/es | página de produto |
| 5 | smartcompany.com.au | outro | brevo.com/es/blog | comparativo |
| 6 | pitneyboweshelpdesk | outro | brevo.com/pt/blog | comparativo |
| 7 | iompost.com | página de produto | mailrelay.com (glossário) | guia/blog |
| 8 | erp.puri.sm | outro | en.wikipedia.org (Mailrelay) | outro |

| Campo | Valor |
|---|---|
| Formato dominante | comparativo de ferramentas de **e-mail marketing** (busca entendida errado: no Brasil "mailing" costuma ser lista de contatos) |
| Intenção | transacional (quem busca quer uma lista grátis) — os resultados respondem a outra coisa |
| PAA | (inferido) Onde baixar mailing de empresas grátis? · Mailing de empresas com e-mail e telefone? · É permitido usar mailing comprado? |
| TurboVenda | Não (tem o guia `mailing-de-empresas`) |
| Concorrentes conhecidos | nenhum |
| Página necessária | Página "mailing de empresas grátis" com 50 leads sem cartão, explicando LGPD e opt-out |
| Volume (estimado) | média |
| Dificuldade | **baixa** neste índice — nenhum resultado brasileiro atende à busca (no Google.br pode ser diferente) |

## 11. mensagem de prospecção whatsapp pronta

| Pos | Standard | Formato | Extended | Formato |
|---|---|---|---|---|
| 1 | conteudo.stone.com.br (prompts) | guia/blog | crmpiperun.com/blog | guia/blog (modelos) |
| 2 | empresaqui.com.br/blog | guia/blog | conteudo.stone.com.br | guia/blog |
| 3 | agendor.com.br/blog | guia/blog | bagy.com.br/blog | guia/blog (modelos) |
| 4 | agendor.com.br/blog | guia/blog | agendor.com.br/blog | guia/blog |
| 5 | viniensina.com.br/ferramentas/gerador… | ferramenta/consulta | zenvia.com/blog | guia/blog (15 modelos) |
| 6 | viniensina.com.br | ferramenta/consulta | ecommercenapratica.com | guia/blog (modelos) |
| 7 | viniensina.com.br (30 prompts) | guia/blog | gluocrm.com.br | guia/blog |
| 8 | agendor.com.br/blog | guia/blog | blog.cubosuite.com.br | guia/blog (10 modelos) |

(Standard depois: ecommercenapratica, exactsales, segs.com.br, **leads2b.com (e-book PDF)**, waalaxy, socialhub.pro. Extended depois: zappycontabil, leadjet.com.br.)

| Campo | Valor |
|---|---|
| Formato dominante | guia/blog do tipo "X modelos prontos" + geradores com IA |
| Intenção | informacional (quer o texto pronto para copiar) |
| PAA | (inferido) Como abordar um cliente no WhatsApp pela primeira vez? · Qual a melhor mensagem de prospecção? · Como fazer follow-up no WhatsApp sem ser chato? |
| TurboVenda | Não (tem `/ferramentas/gerador-de-mensagem-de-prospeccao` e o guia `mensagem-de-prospeccao-whatsapp`) |
| Concorrentes conhecidos | **Leads2b** (e-book em PDF) |
| Página necessária | Página com 20–30 modelos B2B por segmento (indústria, distribuidor, representante) + gerador grátis na mesma página |
| Volume (estimado) | alta |
| Dificuldade | média — muitos blogs, mas um gerador simples (ViniEnsina) já ranqueia |

## 12. modelo de e-mail de prospecção b2b

| Pos | Domínio | Formato |
|---|---|---|
| 1 | blog.waalaxy.com/pt | guia/blog (+25 modelos) |
| 2 | reply.io/br | guia/blog (com dados) |
| 3 | agendor.com.br/blog | guia/blog |
| 4 | snov.io/blog/br | guia/blog (modelos) |
| 5 | agendor.com.br/blog | guia/blog |
| 6 | snov.io/blog | guia/blog |
| 7 | activecampaign.com/br/blog | guia/blog |
| 8 | zeliq.com/fr (francês) | guia/blog |

(Depois: agendor 2x, snov.io, lagrowthmachine, iubenda.)

| Campo | Valor |
|---|---|
| Formato dominante | guia/blog do tipo "modelos para copiar" |
| Intenção | informacional |
| PAA | (inferido) Como escrever um cold e-mail B2B? · Qual o melhor assunto para e-mail de prospecção? · Quantos follow-ups mandar? |
| TurboVenda | Não (não achei guia de e-mail no código; o gerador pode cobrir) |
| Concorrentes conhecidos | nenhum |
| Página necessária | Página de modelos de e-mail B2B para PME brasileira + gerador de e-mail com IA |
| Volume (estimado) | média |
| Dificuldade | média — ferramentas estrangeiras traduzidas (Waalaxy, Reply, Snov) e a Agendor |

## 13. como fazer prospecção ativa

| Pos | Domínio | Formato |
|---|---|---|
| 1 | rdstation.com/blog | guia/blog (8 passos) |
| 2 | empresaqui.com.br/blog | guia/blog |
| 3 | empresaqui.com.br/blog | guia/blog |
| 4 | neilpatel.com/br | guia/blog |
| 5 | agilize.com.br/blog | guia/blog |
| 6 | agilize.com.br/blog | guia/blog |
| 7 | agilize.com.br/blog | guia/blog |
| 8 | contabilidade.com/blog | guia/blog |

(Depois: agendor, hostgator, blog.inter.co, assertivasolucoes, exactsales 2x, kaizen, sendpulse.)

| Campo | Valor |
|---|---|
| Formato dominante | guia/blog |
| Intenção | informacional |
| PAA | (inferido) Qual a diferença entre prospecção ativa e passiva? · Quais as técnicas de prospecção ativa? · Prospecção ativa por telefone ou WhatsApp? |
| TurboVenda | Não (tem o guia `como-fazer-prospeccao-ativa`) |
| Concorrentes conhecidos | nenhum |
| Página necessária | Guia com rotina diária pronta (quantas ligações/mensagens) + modelos + link para a calculadora |
| Volume (estimado) | alta |
| Dificuldade | **alta** — RD Station, Neil Patel, Inter, HostGator e EmpresAqui |

## 14. quantos leads preciso para bater a meta

| Pos | Standard | Formato | Extended | Formato |
|---|---|---|---|---|
| 1 | agendor.com.br/blog | guia/blog | receitaprevisivel.com/blog (título igual à busca) | guia/blog |
| 2 | agendor.com.br/blog | guia/blog | poli.digital | guia/blog |
| 3 | blog.autoforce.com | guia/blog | vendas.mkt4sales.com | guia/blog |
| 4 | startupi.com.br | guia/blog | disparoemassa.com.br/blog | guia/blog |
| 5 | hotmart.com (curso) | página de produto | elevon.com.br | guia/blog |
| 6 | trafius.com.br (calculadora de funil) | ferramenta/consulta | noblinddz.com.br/blog | guia/blog |
| 7 | adweek.com (EN) | guia/blog | entrandonodigital.com/calculador-de-leads | ferramenta/consulta |
| 8 | exactsales.com.br | guia/blog | remessaonline.com.br/blog | guia/blog |

| Campo | Valor |
|---|---|
| Formato dominante | guia/blog com fórmula; calculadoras aparecem |
| Intenção | informacional (com uso de ferramenta) |
| PAA | (inferido) Como calcular a meta de leads? · Qual a taxa de conversão boa em B2B? · Quantas ligações por dia para bater a meta? |
| TurboVenda | Não (tem `/ferramentas/calculadora-de-leads` e o guia `quantos-leads-preciso-para-bater-a-meta`) |
| Concorrentes conhecidos | nenhum |
| Página necessária | Calculadora no topo + explicação da conta de trás para frente + exemplos por ticket |
| Volume (estimado) | baixa |
| Dificuldade | **baixa** — resultados espalhados, sites pequenos ranqueiam |

## 15. como montar uma lista de prospecção

| Pos | Domínio | Formato |
|---|---|---|
| 1 | thunderbit.com/pt/blog | guia/blog |
| 2 | agendor.com.br/blog | guia/blog |
| 3 | agendor.com.br/blog | guia/blog |
| 4 | thunderbit.com/pt/blog | guia/blog |
| 5 | empresaqui.com.br/blog | guia/blog |
| 6 | experian.com (EN) | guia/blog |
| 7 | agendor.com.br/blog | guia/blog |
| 8 | agendor.com.br/blog | guia/blog |

(Depois: quickmail.com [EN], expressanalytics.com [EN], agendor 2x.)

| Campo | Valor |
|---|---|
| Formato dominante | guia/blog |
| Intenção | informacional |
| PAA | (inferido) Quais campos uma lista de prospecção deve ter? · Onde encontrar empresas para prospectar? · Planilha de prospecção pronta? |
| TurboVenda | Não (tem o guia `como-montar-lista-de-prospeccao`) |
| Concorrentes conhecidos | nenhum |
| Página necessária | Guia + planilha modelo para baixar + "monte sua lista grátis agora" (50 leads) |
| Volume (estimado) | média |
| Dificuldade | média — Agendor ocupa 4 das 8, mas há sites estrangeiros traduzidos ocupando o resto |

## 16. ferramenta de prospecção b2b

| Pos | Standard | Formato | Extended | Formato |
|---|---|---|---|---|
| 1 | empresaqui.com.br/blog (grátis) | comparativo | agendor.com.br/blog | comparativo |
| 2 | snov.io/blog (23 ferramentas) | comparativo | zendesk.com.br/blog (12) | comparativo |
| 3 | empresaqui.com.br/blog (7 melhores) | comparativo | dnadevendas.com.br/blog (9) | comparativo |
| 4 | herospark.com/blog | comparativo | snov.io/blog | comparativo |
| 5 | empresaqui.com.br/blog | comparativo | cortex-intelligence.com/blog | guia/blog |
| 6 | snov.io/blog/br | comparativo | flowlu.com/blog | comparativo |
| 7 | blog.waalaxy.com/pt | comparativo | cognism.com (via Google Tradutor) | comparativo |
| 8 | herospark.com/blog | comparativo | blog.datlo.com | comparativo |

(Standard depois: salesdorado, empresaqui 3x, agendor, **b2bstack.com.br/product/leads2b** [perfil com avaliações], lagrowthmachine, lessie.ai, skipcall.io, folk.app. Extended depois: prospectei.app.br.)

| Campo | Valor |
|---|---|
| Formato dominante | comparativo ("as X melhores ferramentas") |
| Intenção | comparativa (perto da compra) |
| PAA | (inferido) Qual a melhor ferramenta de prospecção B2B? · Existe ferramenta de prospecção grátis? · Apollo funciona no Brasil? |
| TurboVenda | Não |
| Concorrentes conhecidos | **Leads2b** (B2B Stack); **Apollo** citado no texto de listas (extended) |
| Página necessária | Comparativo honesto "melhores ferramentas de prospecção B2B no Brasil" com preço e base de dados BR + perfis no B2B Stack/GetApp |
| Volume (estimado) | média |
| Dificuldade | **alta** — EmpresAqui ocupa várias posições, mais Snov, Zendesk e Agendor |

## 17. alternativa econodata

| Pos | Standard | Formato | Extended | Formato |
|---|---|---|---|---|
| 1 | b2bstack.com.br/compare (Energia Plus) | comparativo | tamz.ai/alternativas/econodata | comparativo |
| 2 | saashub.com | comparativo (agregador) | farejaleads.com/alternativas/econodata | comparativo |
| 3 | itbrief.co.uk | outro (fora do assunto) | leadjet.com.br/alternativa-econodata | comparativo |
| 4 | en.wikipedia.org (alternative data) | outro | dadospremium.com/vs/econodata | comparativo |
| 5 | b2bstack.com.br/compare (Metrica) | comparativo | socialhub.pro/alternativa-econodata | comparativo |
| 6 | getlatka.com | comparativo (agregador) | similarweb.com (concorrentes) | ferramenta/consulta |
| 7 | substack (fora do assunto) | outro | en.wikipedia.org | outro |
| 8 | getapp.com (alternatives) | comparativo (agregador) | getapp.za.com | comparativo (agregador) |

| Campo | Valor |
|---|---|
| Formato dominante | comparativo ("alternativa à Econodata" feito por concorrentes) |
| Intenção | comparativa / fim do funil |
| PAA | (inferido) Quanto custa a Econodata? · Econodata vale a pena? · Qual a alternativa mais barata à Econodata? |
| TurboVenda | Não (tem `/alternativas/econodata` no código) |
| Concorrentes conhecidos | **Econodata** (assunto); **Speedio** (citado na página da TAMZ); **Apollo** (citado nas listas do GetApp) |
| Página necessária | A página `/alternativas/econodata` que já existe: tabela de preço lado a lado (R$97 / R$297 vs "sob consulta"), plano grátis, dados para conferir |
| Volume (estimado) | baixa |
| Dificuldade | média — 5 concorrentes pequenos já têm página própria, mas nenhum domínio forte |

## 18. como conseguir clientes sendo representante comercial

| Pos | Standard | Formato | Extended | Formato |
|---|---|---|---|---|
| 1 | chubb.com/co-es (ES) | guia/blog | br.indeed.com (conselho de carreira) | guia/blog |
| 2 | agendor.com.br/blog | guia/blog | srna.co/blog | guia/blog |
| 3 | bolsamania.com (ES) | guia/blog | blog.mercos.com (guia do representante) | guia/blog |
| 4 | tray.com.br/escola | guia/blog | tactus.com.br | guia/blog |
| 5 | blog.waalaxy.com/pt | guia/blog | blog.mercos.com (7 dicas) | guia/blog |
| 6 | sage.com/es-es (ES) | guia/blog | iev.com.br | guia/blog |
| 7 | tray.com.br/escola | guia/blog | berryconsult.com | guia/blog |
| 8 | querobolsa.com.br | guia/blog (carreira) | representamais.com.br | guia/blog |

(Standard depois: agendor, workable, meucompressor [PDF], gestiopolis, findthatlead, empresaqui, lagrowthmachine.)

| Campo | Valor |
|---|---|
| Formato dominante | guia/blog — mas sobre **carreira** ("como ser representante"), não sobre conseguir clientes |
| Intenção | informacional |
| PAA | (inferido) Como o representante comercial encontra clientes? · Como conseguir representadas? · Como montar carteira de clientes do zero? |
| TurboVenda | Não (tem o guia `como-conseguir-clientes-representante-comercial`) |
| Concorrentes conhecidos | nenhum (Mercos é o único focado em representante) |
| Página necessária | Guia "carteira do zero para representante": lista por CNAE e região, rota de visitas, WhatsApp, com exemplos do Sul |
| Volume (estimado) | baixa |
| Dificuldade | **baixa** — os resultados falam de carreira, quase ninguém responde à pergunta de verdade |

## 19. consultar sócios de empresa pelo cnpj

| Pos | Domínio | Formato |
|---|---|---|
| 1 | cora.com.br/blog/ferramentas | ferramenta/consulta + guia |
| 2 | contabilizei.com.br | guia/blog |
| 3 | jornalcontabil.com.br | guia/blog |
| 4 | nfe.io/blog | guia/blog |
| 5 | contabilidade.com/blog | guia/blog |
| 6 | nfe.io/blog | guia/blog |
| 7 | cora.com.br/blog | guia/blog |
| 8 | blog.assertivasolucoes.com.br | guia/blog |

(Depois: empresaqui, triviumcontabil.com.br [consulta CNPJ grátis] 2x, apify, serpro.gov.br, monitorcnpj.com.br 2x, cidesp.com.br.)

| Campo | Valor |
|---|---|
| Formato dominante | guia/blog (bancos digitais e contabilidades), com ferramentas de consulta |
| Intenção | informacional + transacional (quer a resposta na hora) |
| PAA | (inferido) Como ver o QSA de uma empresa? · Dá para ver o CPF do sócio? · Como descobrir o dono de um CNPJ? |
| TurboVenda | Não (o guia mais próximo é `como-encontrar-o-decisor-da-empresa`) |
| Concorrentes conhecidos | nenhum |
| Página necessária | Ferramenta grátis "consultar sócios pelo CNPJ" (QSA + decisor + telefone) — ferramenta, não artigo |
| Volume (estimado) | alta |
| Dificuldade | **alta** — Cora, Contabilizei, NFe.io e contabilidade.com, além de sites de consulta de CNPJ |

## 20. software de prospecção de clientes whatsapp

| Pos | Standard | Formato | Extended | Formato |
|---|---|---|---|---|
| 1 | empresaqui.com.br/blog | guia/blog | sleekflow.io/pt-br/blog | guia/blog |
| 2 | olhardigital.com.br | comparativo | prospectox.com.br | página de produto |
| 3 | sleekflow.io/pt-br/blog | guia/blog | prospecta-zap-web.com.br | página de produto |
| 4 | agendor.com.br/blog | guia/blog | atlasencontra.com | página de produto |
| 5 | extensionauditor.com (Prospecta CRM) | outro | prospectamax.com.br (gerador) | ferramenta/consulta |
| 6 | agendor.com.br/blog | guia/blog | prospectool.com | página de produto |
| 7 | breakcold.com/pt-br/blog | comparativo | prospectar.io | página de produto |
| 8 | agendor.com.br/blog | guia/blog | prospector.vendendosites.com.br | página de produto |

(Standard depois: exactsales, agendor, workana 2x, joinsecret.com [lista], viniensina. Extended depois: disparoemassa.com.br/blog.)

| Campo | Valor |
|---|---|
| Formato dominante | página de produto (extended) / guia (standard) |
| Intenção | transacional |
| PAA | (inferido) Qual o melhor CRM com WhatsApp? · Disparo em massa no WhatsApp bloqueia o número? · Precisa da API oficial para prospectar? |
| TurboVenda | Não |
| Concorrentes conhecidos | nenhum (concorrentes pequenos de nicho WhatsApp) |
| Página necessária | Página de produto "prospecção B2B pelo WhatsApp": base de empresas + mensagem com IA + CRM, com comparação de risco de bloqueio |
| Volume (estimado) | média |
| Dificuldade | média — muitas páginas de produto pequenas, nenhuma marca forte |

---

## Perguntas no formato de assistente de IA (aproximação pela busca web)

**Aviso:** não dá para consultar ChatGPT, Perplexity ou Gemini daqui. O que segue é uma **aproximação**: os sites que a busca web devolve para a pergunta escrita como se fala com um assistente, e os que a própria ferramenta citou na resposta resumida. Assistentes que buscam na web tendem a citar fontes desse tipo, mas não há garantia de que citem as mesmas.

| Pergunta | Sites nos resultados | Citados na resposta resumida | TurboVenda | Concorrentes |
|---|---|---|---|---|
| qual a melhor ferramenta de prospecção b2b no brasil? | salesforge.ai/pt, empresaqui.com.br (5x), snov.io, agendor.com.br (2x), b2bstack.com.br (Leadeasy, Leads2b, Prospec), lessie.ai (2x), getapp.com.br, capterra.com.br, skipcall.io | EmpresAqui, Snov.io, Ramper, Voila Norbert, Apollo, Clay, Cognism, Lessie, Bitrix24 | Não | Leads2b (B2B Stack), Apollo |
| como conseguir lista de empresas por cnae grátis? | senhorcontabil, empresaqui (3x), jornalcontabil, poder360 (PDF), apify, pontotel, einforma, contaja, fiscal.io, monitorcnpj | MonitorCNPJ, Apify, Contajá, Fiscal.io, brasildados, IBGE | Não | nenhum |
| quais as alternativas ao econodata? | b2bstack.com.br (2x comparativos), saashub, semrush (concorrentes), capterra, getapp, getlatka, baguete | cnpj.biz (via Semrush), Webcenso (via B2B Stack), Enlyft, ContactOut, CUFinder | Não | Econodata (assunto) |
| como achar o dono de uma empresa pelo cnpj | toexceed, contabilidadezen, serasa, contaja, contabilidade.com, empresaqui (2x), serpro, cidesp, companyhero, jornalcontabil, omie, apify | Casa dos Dados, CNPJ Biz, Jucesp, EmpresAqui | Não | nenhum |
| como montar lista de prospecção b2b | empresaqui (4x), flowhunt.io, growbots (2x), sopro.io (2x), lagrowthmachine, anymailfinder, salesintel, ebq, prospeo | EmpresAqui, FlowHunt, LaGrowthMachine, Growbots | Não | nenhum |

O que se repete nas fontes desse tipo de resposta: **agregadores de avaliação e comparação** (B2B Stack, GetApp, Capterra, SaaSHub, Latka, Semrush), **EmpresAqui** e **sites de consulta de CNPJ** (CNPJ.biz, Casa dos Dados, MonitorCNPJ). Na busca standard, a TurboVenda não aparece em nenhuma delas e não tem perfil visível nesses agregadores.

---

## Padrões

1. **A TurboVenda quase não aparece:** só em 1 das 20 consultas ("lista de empresas por cidade", posição 5, só no índice extended, pela `/ferramentas/lista-de-empresas`). A busca `site:turbovenda.com.br` no standard não trouxe nenhuma página. O código já tem página para uns 13 dos 20 temas, então **o gargalo é indexação e autoridade, não falta de conteúdo**.
2. **EmpresAqui é o rival de SEO de verdade:** aparece em 15 das 20 consultas, muitas vezes em várias posições, e é a fonte mais citada nas perguntas tipo IA. A Agendor aparece em 10, sempre com guia. Entre os concorrentes conhecidos, a Econodata só aparece em 3 (Passo Fundo, base CNPJ, alternativa) e a Leads2b em 2. Speedio e Apollo só aparecem citados dentro de textos de outros sites.
3. **O formato que ganha depende da intenção:** guia/blog ganha nas buscas de "como fazer" (5, 6, 7, 12, 13, 15, 18). Diretório programático ganha nas locais (3, 4) e em lista por cidade (1). Página de produto ou ferramenta ganha em CNAE, base CNPJ e WhatsApp (2, 9, 20). Comparativo ganha em "ferramenta" e "alternativa" (16, 17).
4. **Desafiantes baratos já fazem o jogo que a TurboVenda quer fazer:** LeadJet, SocialHub, Disparo em Massa, TAMZ, Dados Premium, FarejaLeads e CNPJ.biz aparecem com páginas de "lista por cidade/CNAE" e de "alternativa à Econodata". São eles os concorrentes diretos no Google, mais do que Speedio ou Apollo.
5. **Vitórias rápidas (dificuldade baixa e a página já existe no código):** metalúrgicas em Caxias do Sul (só notícia de sindicato e uma página fraca da EmpresAqui), quantos leads preciso (só sites pequenos, e calculadora ajuda), representante comercial (os resultados falam de carreira, não de clientes), mailing de empresas grátis (a busca é lida como e-mail marketing), lista de clientes B2B e contato de empresas (resultados bagunçados).
6. **Ferramentas interativas ranqueiam em buscas de modelo:** geradores (ViniEnsina, ProspectaMax) e calculadoras (Trafius, Entrando no Digital) aparecem no top 8. Isso apoia o gerador de mensagem e a calculadora de leads como iscas de SEO e de link, desde que fiquem no topo da página com texto embaixo.
7. **As páginas locais e por CNAE são o maior mercado de cauda longa:** EmpresAqui e Econodata têm páginas de cidade, bairro, porte e "maiores empresas" (Passo Fundo). As `/empresas/cidade/` e `/empresas/<cnae>/<cidade>` da TurboVenda precisam de dados únicos (contagem real, top segmentos, maiores empresas, amostra grátis) e de links internos, começando pelo Sul.
8. **Evitar por enquanto (dificuldade alta):** como prospectar clientes B2B, prospecção ativa, encontrar clientes e consultar sócios. Essas são dominadas por RD Station, Neil Patel, Agendor, Cora, Contabilizei e bancos. "Consultar sócios" só vale com uma **ferramenta grátis de QSA + decisor**, não com mais um artigo.
9. **Entrar nas respostas de IA é barato:** as fontes que se repetem são agregadores (B2B Stack, GetApp, Capterra, SaaSHub). Criar perfil da TurboVenda nesses sites, com avaliações, é a forma mais curta de começar a ser citada nesse tipo de resposta.
10. **Ressalva de método:** a ferramenta usa um índice dos EUA, e os modos standard e extended mostraram resultados bem diferentes. Antes de decidir prioridades, vale confirmar no Google.br (Search Console da TurboVenda e uma busca anônima) as 5 vitórias rápidas e a consulta onde a TurboVenda já aparece.
