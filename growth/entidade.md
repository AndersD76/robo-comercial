# Entidade TurboVenda — texto canônico

Use **exatamente** estes textos em todo lugar onde a marca aparece: site, JSON-LD, LinkedIn, Instagram, Google Business Profile (se fizer sentido), B2B Stack, GetApp, Capterra, SaaSHub, Product Hunt, diretórios setoriais. Buscadores e assistentes de IA juntam as menções de uma marca pela consistência de nome, descrição, logo e links; variações confundem a entidade.

## Dados fixos

| Campo | Valor |
|---|---|
| Nome | TurboVenda (sempre assim: uma palavra, T e V maiúsculos) |
| Site | https://www.turbovenda.com.br |
| Logo | https://www.turbovenda.com.br/static/icon-512.png (quadrado, 512 × 512) |
| Imagem de capa | https://www.turbovenda.com.br/static/og-image.png |
| E-mail | suporte@turbovenda.com.br |
| Categoria | Software de prospecção B2B / geração de leads B2B |
| País e idioma | Brasil, português |
| Planos | Grátis (50 leads, sem cartão, 14 dias), Starter R$ 97/mês, Pro R$ 297/mês |
| Razão social e CNPJ | **TODO-VALIDAR** |
| Cidade/UF (endereço comercial) | **TODO-VALIDAR** |
| Fundador(es) | **TODO-VALIDAR** |
| Perfis oficiais | **TODO-VALIDAR** (LinkedIn da empresa, Instagram, YouTube) — os mesmos vão em `MARCA_PERFIS` no Railway |

## Uma linha (até 120 caracteres)

> TurboVenda encontra empresas para você vender e faz a primeira abordagem por WhatsApp e e-mail com IA.

## Um parágrafo (até 600 caracteres)

> O TurboVenda é um software brasileiro de prospecção B2B. Ele encontra empresas para você vender a partir da base pública de CNPJs da Receita Federal e de buscadores, completa telefone, e-mail, CNPJ e o nome do sócio que decide a compra, e escreve com IA a primeira mensagem de WhatsApp ou e-mail. Os leads ficam num CRM com funil. É feito para donos e gerentes comerciais de pequenas e médias empresas que vendem para outras empresas e não têm equipe de pré-vendas. Dá para testar grátis com 50 leads, sem cartão.

## Uma página

**O problema.** Quem vende para outras empresas perde horas montando lista de clientes: pesquisa no Google, abre site por site, procura CNPJ e telefone, e ainda não sabe com quem falar. Sem lista, a prospecção para.

**O que o TurboVenda faz.**
1. **Encontra as empresas.** Você descreve o que vende e para quem; a IA define os termos de busca e o robô procura em buscadores e na base de CNPJs ativos da Receita Federal, por segmento (CNAE), estado e cidade.
2. **Completa os dados.** Para cada empresa: telefone, e-mail, site, CNPJ, razão social e, quando a Receita publica, o nome do sócio-administrador — a pessoa que decide.
3. **Escreve a abordagem.** A IA escreve a primeira mensagem de WhatsApp ou e-mail com base no que você vende e no perfil da empresa.
4. **Organiza o funil.** Os leads entram num CRM com etapas (novo, contactado, respondeu, qualificado, reunião, convertido).

**Para quem é.** Indústrias, distribuidoras, prestadores de serviço B2B e representantes comerciais com 2 a 50 funcionários, principalmente no Sul do Brasil, que vendem sem equipe de pré-vendas.

**De onde vêm os dados.** Cadastro de empresas: dados abertos do CNPJ publicados pela Receita Federal. Contatos: páginas públicas das próprias empresas. Não trabalha com listas de pessoas físicas nem com CPF.

**Ferramentas grátis, sem login.** Lista de empresas por cidade e segmento; gerador de mensagem de prospecção com IA; calculadora de quantos leads são necessários para bater a meta. Em https://www.turbovenda.com.br/ferramentas.

**Preço.** Grátis com 50 leads (sem cartão, 14 dias); Starter R$ 97/mês (até 500 leads); Pro R$ 297/mês (leads ilimitados, sequências e WhatsApp). Pagamento por PIX, cartão ou boleto.

## Onde já está aplicado
- JSON-LD `Organization` da home (`@id` https://www.turbovenda.com.br/#organizacao): nome, logo, descrição, contato. CNPJ e perfis entram quando `MARCA_CNPJ` e `MARCA_PERFIS` forem configurados.
- `/llms.txt` e `/llms-full.txt`.
