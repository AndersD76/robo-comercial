# Brief — "empresas abertas recentemente em [cidade]"

**Status:** brief, não publicado. Revisar antes de produzir.

- **Consulta-alvo:** "empresas abertas recentemente em [cidade]", "novas empresas em [cidade] [ano]", "empresas abertas em [mês] [cidade]".
- **Intenção:** transacional/local. Quem busca quer vender para empresas novas (contabilidade, uniformes, internet, móveis de escritório, seguros).
- **Ângulo diferenciado (dado próprio):** a base da Receita tem a data de abertura de cada CNPJ. Ninguém no topo mostra "abertas nos últimos 90 dias" por cidade **e** por segmento, com contagem e evolução mês a mês.
- **Formato:** página programática `/empresas/cidade/<cidade>/abertas-recentemente` (ou seção nova no hub da cidade), com limiar: só indexa com ≥ 15 aberturas no período.

## Estrutura
- H1: Empresas abertas recentemente em {cidade} - {UF}
- Resposta direta (40–60 palavras): quantas empresas abriram nos últimos 90 dias, os 3 segmentos que mais abriram e a data da base.
- H2: Aberturas por mês (tabela + gráfico de barras, 12 meses)
- H2: Segmentos que mais abriram empresas (tabela com link para `/empresas/<cnae>/<cidade>`)
- H2: Bairros com mais aberturas
- H2: Como abordar uma empresa recém-aberta (3 parágrafos + link para o gerador de mensagem)
- H2: Perguntas frequentes

## Perguntas a responder
- Quantas empresas abriram em {cidade} este ano?
- Quais setores mais abrem empresas em {cidade}?
- Como conseguir o contato de uma empresa recém-aberta?
- A lista é atualizada com que frequência?

## Dados necessários
- `data_abertura` por CNPJ: já existe em `empresas_publicas`.
- **TODO-VALIDAR:** a base de produção é de ~jul/2026 (abertura mais recente: 14/06/2026). Sem atualizar para a base de out/2026, "recentemente" fica 5 meses atrasado. **Pré-requisito: atualizar a base do Postgres.**

## Links internos
- Do hub da cidade e de cada `/empresas/<cnae>/<cidade>` para esta página; desta para os segmentos e para `/ferramentas/lista-de-empresas`.

## CTA
"Receba toda semana as empresas novas do seu segmento na sua cidade" → `/cadastro?utm_source=pseo&utm_campaign=abertas-recentemente`.
