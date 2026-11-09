# Brief — "consultar sócios de empresa pelo CNPJ"

**Status:** brief, não publicado. **Depende de decisão de dados.**

- **Consultas-alvo:** "consultar sócios pelo cnpj", "quem são os sócios de uma empresa", "como descobrir o dono de uma empresa pelo cnpj".
- **Intenção:** informacional + transacional, volume alto e disputa alta (Cora, Contabilizei, bancos, Casa dos Dados, CNPJ.biz). Só vale como **ferramenta**, não como mais um artigo.
- **Ângulo:** ferramenta grátis: digita o CNPJ, vê o quadro de sócios (nome e qualificação, como a Receita publica) e um botão "achar o contato do decisor" que leva ao produto.
- **Formato:** `/ferramentas/socios-pelo-cnpj`, com resultado em URL própria só para empresas (nunca indexar páginas por pessoa física).

## Decisão necessária (TODO-VALIDAR)
- Os 8,6 mi registros de sócios estão só no índice local do PC (`C:\cnpj\indice.sqlite`), não no Postgres. A ferramenta exige subir a tabela de sócios para o banco de produção: custo de armazenamento e de memória no Neon.
- LGPD: o QSA é dado público da Receita, mas nome de pessoa física exige cuidado — não criar páginas indexáveis por nome de sócio, só consulta pelo CNPJ, com canal de remoção (já existe em `/empresas/sobre-os-dados`).

## Estrutura (se aprovado)
- H1: Consultar sócios de uma empresa pelo CNPJ (grátis)
- Ferramenta no topo; resultado: razão social, situação, sócios (nome e qualificação), data de entrada.
- H2: O que a Receita divulga e o que não divulga (CPF mascarado)
- H2: Como falar com o sócio que decide a compra (link para o post do decisor)
- H2: Perguntas frequentes

## Links internos
- Pilar `/blog/como-encontrar-o-decisor-da-empresa`, `/empresas/sobre-os-dados`, `/ferramentas`.

## CTA
"Encontrar o telefone e o e-mail do decisor" → `/cadastro?utm_source=ferramentas&utm_campaign=socios`.
