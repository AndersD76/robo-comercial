# Rascunho — página "Sobre o TurboVenda" (`/sobre`)

**Status:** rascunho para revisão. Não publicar com os campos TODO-VALIDAR em aberto.

## O que é
O TurboVenda é um software de prospecção B2B feito no Brasil. Ele encontra empresas para você vender — a partir da base pública de CNPJs da Receita Federal e de buscadores —, completa telefone, e-mail, CNPJ e o nome do sócio que decide a compra, e ajuda a fazer a primeira abordagem por WhatsApp e e-mail com textos escritos por IA.

## Para quem
Donos e gerentes comerciais de pequenas e médias empresas que vendem para outras empresas e não têm equipe de pré-vendas: indústrias, distribuidoras, prestadores de serviço B2B e representantes comerciais.

## De onde vêm os dados
- Cadastro de empresas: dados abertos do CNPJ publicados pela Receita Federal (fonte e data na página `/empresas/sobre-os-dados`).
- Contatos de empresas: sites e páginas públicas das próprias empresas.
- Não vendemos listas de pessoas físicas nem dados de CPF.

## Quem está por trás
- AndersTech (ANDERS CONSULTORIA EM GESTAO EMPRESARIAL LTDA), CNPJ 42.073.416/0001-80 — conferido na base da Receita de out/2026.
- Passo Fundo/RS (sem endereço completo, salvo se o dono quiser publicar).
- **TODO-VALIDAR:** fundador(es) com nome, cargo e uma linha de experiência real (ex.: anos em vendas B2B ou em software).
- Contato: suporte@turbovenda.com.br

## Perfis oficiais
- **TODO-VALIDAR:** LinkedIn da empresa, Instagram, YouTube. Os mesmos links vão para o `sameAs` do JSON-LD (variável `MARCA_PERFIS`).

## Ao publicar
- Rota `/sobre`, link no rodapé público, `Organization` com `@id` igual ao da home, `BreadcrumbList`.
