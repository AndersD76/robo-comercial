# Outbound: prospecção direta do ICP

**Alvo:** dono ou sócio de PME B2B (2 a 50 funcionários) que vende sozinho ou com 1 a 5 vendedores, gerente comercial ou representante comercial autônomo. Comece pelo Sul (RS, SC, PR). Setores: indústria (metalurgia, embalagens, confecção, automação), distribuidoras e atacado, serviços B2B (prevenção de incêndio, segurança do trabalho, certificação, contabilidade, TI, agências) e representações.

**Regra de ouro:** cada toque entrega algo útil e grátis (uma das ferramentas). Ninguém recebe "quer conhecer nosso sistema?" no primeiro contato.

**UTM:** e-mail usa `utm_source=email&utm_medium=outbound`, e WhatsApp usa `utm_source=whatsapp&utm_medium=outbound`. O `utm_campaign` muda a cada toque, pra você saber qual mensagem gerou clique.

---

## Variáveis de personalização

| Variável | O que é | Onde achar |
|---|---|---|
| `{nome}` | Primeiro nome do decisor | Site da empresa, LinkedIn, quadro de sócios do CNPJ |
| `{empresa}` | Nome fantasia | Site e fachada |
| `{cidade}` | Cidade da empresa (ou a cidade-alvo dela) | Site e CNPJ |
| `{o_que_vende}` | O que a empresa dele vende, em poucas palavras | Site da empresa |
| `{segmento_cliente}` | Pra quem ELE vende (ex.: construtoras, transportadoras, indústrias metalúrgicas) | Site da empresa ("clientes", "segmentos atendidos") |
| `{qtd_empresas}` | Quantas `{segmento_cliente}` ativas existem em `{cidade}` | **Rode a ferramenta de lista de empresas antes de escrever** e copie o número que ela mostrar. Nunca estime nem arredonde pra cima. |
| `{fonte_contato}` | Onde você achou o contato | Ex.: "o site da {empresa}", "o LinkedIn", "os dados públicos do CNPJ da {empresa}" |
| `{seu_nome}` | Seu nome | |
| `{seu_whatsapp}` | Seu número comercial | |

Sem `{segmento_cliente}` e `{qtd_empresas}` preenchidos de verdade, não mande. É essa personalização que separa a mensagem de spam.

---

## Calendário (sequência combinada)

| Dia | Canal | Toque | Ferramenta oferecida |
|---|---|---|---|
| 0 | E-mail | E-mail 1 | Lista de empresas (com o número dele) |
| 2 | WhatsApp | WhatsApp 1 | Lista de empresas |
| 4 | E-mail | E-mail 2 | Calculadora de leads |
| 7 | WhatsApp | WhatsApp 2 | Calculadora de leads |
| 11 | E-mail | E-mail 3 (encerramento) | Gerador de mensagem + conta grátis |
| 14 | WhatsApp | WhatsApp 3 (encerramento) | Gerador de mensagem |

**Regras de parada:**
- Respondeu, com sim ou com não? **Sai da sequência na hora** e segue a conversa manualmente.
- Pediu pra sair, ou perguntou "como você conseguiu meu contato"? Responda (modelo no fim), **remova e anote numa lista de "não contatar"**. Essa pessoa nunca mais entra numa sequência.
- No máximo 6 toques por pessoa. Depois do encerramento, não volte por pelo menos 90 dias.
- Só usar um canal? Rode só a coluna de e-mail (dias 0, 4 e 11) ou só a de WhatsApp (dias 0, 4 e 10).
- WhatsApp só em **número comercial da empresa**, publicado no site ou no cadastro. Nada de celular pessoal achado em lista comprada.

---

## Sequência de E-MAIL (3 toques)

### E-mail 1 (dia 0): o número do mercado dele
**Assunto (escolha um):**
- `{qtd_empresas} {segmento_cliente} em {cidade}`
- `lista de {segmento_cliente} em {cidade}`

> Oi, {nome}, tudo bem?
>
> Vi no site que a {empresa} vende {o_que_vende} para {segmento_cliente}. Fiquei curioso e fiz uma contagem nos dados abertos da Receita Federal: hoje são {qtd_empresas} {segmento_cliente} ativas em {cidade}.
>
> Se quiser ver o perfil dessas empresas e fazer a mesma conta para outras cidades da sua região, a ferramenta é grátis e não pede login:
> https://www.turbovenda.com.br/ferramentas/lista-de-empresas?utm_source=email&utm_medium=outbound&utm_campaign=seq-email-1
>
> Ela mostra a quantidade, o porte, há quanto tempo estão abertas, os bairros com mais empresas e 10 exemplos.
>
> Abraço,
> {seu_nome}
> AndersTech, Passo Fundo/RS
>
> ---
> Encontrei seu contato em {fonte_contato}. Se não quiser receber mais e-mails meus, responda "sair" que eu tiro seu endereço da minha lista na hora.

### E-mail 2 (dia 4): a conta da meta
**Assunto (escolha um):**
- `quantos contatos por dia pra bater a meta?`
- `{nome}, a conta da meta da {empresa}`

> {nome}, uma pergunta rápida sobre a meta comercial da {empresa}: vocês sabem quantas empresas precisam ser contatadas por dia pra chegar nela?
>
> A conta é simples, mas pouca gente faz. Com números redondos de exemplo: se o ticket médio é R$ 5.000 e a meta é R$ 50.000 de venda nova no mês, são 10 vendas. Fechando 1 a cada 5 propostas, são 50 propostas. E a conta vai descendo por reuniões e conversas até virar leads abordados por dia.
>
> Fiz uma calculadora grátis que faz essa conta com os números de vocês:
> https://www.turbovenda.com.br/ferramentas/calculadora-de-leads?utm_source=email&utm_medium=outbound&utm_campaign=seq-email-2
>
> Se o resultado assustar, me responde. Tenho umas ideias de como montar a lista pra chegar nesse volume.
>
> {seu_nome}
>
> ---
> Encontrei seu contato em {fonte_contato}. Se não quiser receber mais e-mails meus, responda "sair" que eu tiro seu endereço da lista na hora.

### E-mail 3 (dia 11): encerramento
**Assunto (escolha um):**
- `última mensagem sobre {segmento_cliente} em {cidade}`
- `fecho por aqui, {nome}`

> {nome}, esta é a última mensagem que te mando sobre isso. Não quero lotar sua caixa.
>
> Deixo mais uma ferramenta grátis: um gerador em que a IA escreve a primeira mensagem de prospecção (WhatsApp ou e-mail) pra você ajustar e mandar pros seus {segmento_cliente}:
> https://www.turbovenda.com.br/ferramentas/gerador-de-mensagem-de-prospeccao?utm_source=email&utm_medium=outbound&utm_campaign=seq-email-3
>
> Se em algum momento quiser testar o sistema completo, com a base de empresas, a IA escrevendo as mensagens e um CRM em Kanban no mesmo lugar, tem plano grátis com 50 leads e sem cartão:
> https://www.turbovenda.com.br/cadastro?utm_source=email&utm_medium=outbound&utm_campaign=seq-email-3
>
> Se não for o momento, sem problema. Obrigado pela atenção.
>
> {seu_nome}
>
> ---
> Encontrei seu contato em {fonte_contato}. Se não quiser receber mais e-mails meus, responda "sair" que eu tiro seu endereço da lista.

---

## Sequência de WHATSAPP (3 toques, mais curtos)

### WhatsApp 1 (dia 2): o número do mercado dele
> Oi, {nome}! Aqui é o {seu_nome}, da AndersTech (Passo Fundo/RS). Te mandei um e-mail esses dias: fiz uma contagem nos dados da Receita e existem {qtd_empresas} {segmento_cliente} ativas em {cidade}. Se quiser ver o perfil delas, a ferramenta é grátis e sem login:
> https://www.turbovenda.com.br/ferramentas/lista-de-empresas?utm_source=whatsapp&utm_medium=outbound&utm_campaign=seq-wa-1
> Se não fizer sentido pra você, é só me avisar que eu não mando mais mensagem.

*Se o WhatsApp for o primeiro contato (sem e-mail antes), tire a frase "Te mandei um e-mail esses dias".*

### WhatsApp 2 (dia 7): a conta da meta
> {nome}, uma pergunta rápida: vocês sabem quantos contatos por dia precisam fazer pra bater a meta do mês? Tem uma calculadora grátis que faz a conta a partir da meta:
> https://www.turbovenda.com.br/ferramentas/calculadora-de-leads?utm_source=whatsapp&utm_medium=outbound&utm_campaign=seq-wa-2
> (Se preferir que eu não chame mais, é só falar.)

### WhatsApp 3 (dia 14): encerramento
> {nome}, última mensagem, prometo. Se um dia travar na primeira mensagem pra um cliente novo, a IA escreve pra você aqui, de graça:
> https://www.turbovenda.com.br/ferramentas/gerador-de-mensagem-de-prospeccao?utm_source=whatsapp&utm_medium=outbound&utm_campaign=seq-wa-3
> E se quiser testar o sistema, tem plano grátis com 50 leads e sem cartão. Sucesso aí!

---

## Respostas prontas

**"Como você conseguiu meu contato?"**
> Encontrei em {fonte_contato}. Se preferir, apago agora e não te chamo mais. É só confirmar.

**"Sair" / "não tenho interesse"**
> Combinado, {nome}. Já tirei seu contato da minha lista. Obrigado pela resposta e sucesso!
*(E tire mesmo. Anote na lista de "não contatar" no mesmo dia.)*

**"Interessante, como funciona o sistema?"**
> A IA escreve os termos de busca pra achar quem compra o que você vende, em cima de uma base de 6.739.551 CNPJs ativos da Receita. Ela também escreve as mensagens de e-mail e WhatsApp, e os leads ficam num CRM em Kanban. Dá pra testar no plano grátis, com 50 leads e sem cartão:
> https://www.turbovenda.com.br/cadastro?utm_source=email&utm_medium=outbound&utm_campaign=seq-resposta
*(No WhatsApp, troque `utm_source=email` por `utm_source=whatsapp` no link.)*

**"Quanto custa?"**
> Tem plano grátis com 50 leads e sem cartão. Os pagos são o Starter, a R$ 97/mês, e o Pro, a R$ 297/mês.

**"Já uso o Econodata / Speedio / Leads2B / Apollo"**
> Faz sentido. Se um dia quiser comparar, deixei as diferenças lado a lado aqui: (mande só o link do concorrente que ele citou)
> - https://www.turbovenda.com.br/alternativas/econodata?utm_source=email&utm_medium=outbound&utm_campaign=seq-resposta
> - https://www.turbovenda.com.br/alternativas/speedio?utm_source=email&utm_medium=outbound&utm_campaign=seq-resposta
> - https://www.turbovenda.com.br/alternativas/leads2b?utm_source=email&utm_medium=outbound&utm_campaign=seq-resposta
> - https://www.turbovenda.com.br/alternativas/apollo?utm_source=email&utm_medium=outbound&utm_campaign=seq-resposta
*(No WhatsApp, troque `utm_source=email` por `utm_source=whatsapp`.)*

---

## Cuidados (LGPD e entregabilidade)

- **Sempre se identifique** (nome e empresa), **diga onde achou o contato** e **ofereça a saída** em toda mensagem. A linha de saída já está nos modelos, então não a apague.
- **Pedido de saída é atendido no mesmo dia**, e a pessoa vai pra lista de "não contatar", que você consulta antes de toda nova sequência.
- **Prefira contatos corporativos** (e-mail e WhatsApp comercial da empresa) e decisores em contexto profissional. Não use listas compradas de origem desconhecida.
- Para a base legal (normalmente o legítimo interesse, no B2B), confirme com quem cuida do jurídico da AndersTech e guarde o registro de onde veio cada contato.
- **E-mail:** mande de uma caixa sua, com nome de gente, no domínio da empresa, e não do domínio principal se for disparar volume (use um subdomínio ou domínio secundário aquecido). Comece com 20 a 30 e-mails por dia e vá subindo. Sem imagens, sem anexo e com no máximo 2 links por e-mail.
- **WhatsApp:** nada de disparo em massa. Mande uma mensagem por vez, personalizada. Se a pessoa não responder ao toque 3, acabou.
