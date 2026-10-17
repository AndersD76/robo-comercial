# -*- coding: utf-8 -*-
"""
Guias de SEO do blog do TurboVenda (pt-BR).

GUIAS segue exatamente o formato de BLOG_POSTS em app.py:
slug, titulo, desc, keywords, data, tempo, conteudo (HTML sem <h1>;
o template blog_post.html renderiza o <h1> a partir de 'titulo').
"""

GUIAS = [
    {
        'slug': 'lista-de-empresas-por-cidade',
        'titulo': 'Lista de Empresas por Cidade e por CNAE: Como Montar a Sua',
        'desc': 'Como montar uma lista de empresas por cidade e por CNAE com dados públicos da Receita: de onde vêm os dados, quais filtros usar e os erros mais comuns.',
        'keywords': 'lista de empresas por cidade, lista de empresas por cnae, empresas por cidade, lista de empresas cnpj, empresas por segmento',
        'data': '2026-10-17',
        'tempo': '6 min',
        'conteudo': """
<p>Quem vende para outras empresas cedo ou tarde faz a mesma pergunta: <strong>quais empresas do meu segmento existem na minha cidade e nas cidades vizinhas?</strong> Sem essa resposta, a prospecção vira garimpo no Google, um CNPJ de cada vez. Este guia mostra como montar uma lista de empresas por cidade e por CNAE, de onde vêm os dados, quais filtros usar e o que fazer com a lista depois de pronta.</p>

<h2>O que uma lista de empresas por cidade precisa ter</h2>
<p>Uma lista útil para prospecção tem duas camadas de informação. A primeira é cadastral e diz <em>quem</em> é a empresa:</p>
<ul>
<li><strong>Razão social e nome fantasia:</strong> o nome jurídico e o nome que aparece na fachada (e no Google).</li>
<li><strong>CNPJ e situação cadastral:</strong> só interessa quem está ativo.</li>
<li><strong>CNAE principal e secundários:</strong> a atividade econômica declarada, o filtro mais objetivo que existe.</li>
<li><strong>Porte:</strong> microempresa, empresa de pequeno porte ou demais.</li>
<li><strong>Endereço, bairro e município:</strong> essenciais para rota de visita e para quem atende só uma região.</li>
<li><strong>Data de abertura:</strong> separa a empresa nova, que está montando estrutura, da empresa consolidada.</li>
</ul>
<p>A segunda camada é de contato e diz <em>como falar</em> com a empresa: telefone, WhatsApp, e-mail, site e o nome de quem decide. É a camada que mais dá trabalho e a que envelhece mais rápido.</p>

<h2>De onde vêm os dados</h2>
<h3>Dados abertos do CNPJ (Receita Federal)</h3>
<p>A Receita Federal publica o cadastro de CNPJ como dado aberto. É a fonte mais completa para a camada cadastral: todo CNPJ do país, com CNAE, porte, endereço e situação. O problema é que os arquivos são grandes e brutos, e os telefones e e-mails ali foram informados no cadastro da empresa, muitas vezes na abertura. É comum estarem desatualizados ou serem do escritório de contabilidade.</p>
<h3>Buscadores e mapas</h3>
<p>Buscar "metalúrgica em Caxias do Sul" no Google Maps traz empresas com telefone, site e avaliações. Funciona bem para segmentos com fachada e atendimento ao público, mas deixa de fora muita indústria e muito prestador de serviço B2B que não cuida da presença online.</p>
<h3>Entidades e eventos</h3>
<p>Associações comerciais e industriais, sindicatos patronais e federações das indústrias (como FIERGS, FIESC e FIEP) às vezes publicam a lista de associados. Catálogos de expositores de feiras regionais também ajudam. São listas menores, mas de empresas ativas e com alguém do outro lado.</p>

<h2>Passo a passo: lista por cidade e por CNAE</h2>
<ol>
<li><strong>Escreva quem compra de você.</strong> Não "empresas em geral", e sim tipos de empresa. Um fabricante de embalagens plásticas de Joinville, por exemplo, vende para indústrias de alimentos, de cosméticos e de produtos de limpeza.</li>
<li><strong>Traduza cada tipo em CNAEs.</strong> "Indústria de alimentos" vira vários códigos: laticínios, panificação industrial, abate de aves e assim por diante. Se o assunto é novo para você, leia <a href="/blog/o-que-e-cnae-prospeccao">o que é CNAE e como usar na prospecção</a>.</li>
<li><strong>Defina as cidades pelo seu raio real de atendimento.</strong> Uma distribuidora de Passo Fundo que entrega em 24 horas talvez atenda Carazinho, Marau e Erechim, mas não Pelotas. Uma software house de Florianópolis que vende remoto pode olhar o Brasil inteiro.</li>
<li><strong>Filtre só empresas ativas</strong> e, se fizer sentido, pelo porte. Quem vende um sistema caro provavelmente não quer microempresas; quem oferece contabilidade para negócios pequenos quer exatamente elas.</li>
<li><strong>Enriqueça com contato.</strong> Para cada empresa, procure telefone atualizado, site, e-mail comercial e o decisor.</li>
<li><strong>Priorize.</strong> Separe as empresas em A, B e C (encaixe perfeito, bom, duvidoso) e comece pelas A.</li>
</ol>

<h2>Exemplo prático: fornecedor industrial na Serra Gaúcha</h2>
<p>Imagine uma empresa de Caxias do Sul que faz manutenção de máquinas e vende ferramentas de corte. Os compradores naturais são usinagens (CNAE 2539-0/01), fabricantes de estruturas metálicas (2511-0/00) e fabricantes de máquinas para uso industrial (2869-1/00). As cidades: Caxias do Sul, Farroupilha, Bento Gonçalves, Flores da Cunha e Garibaldi. Com três códigos e cinco municípios, a lista sai em minutos numa ferramenta que já tem a base da Receita organizada. No braço, seriam dias pesquisando CNPJ por CNPJ.</p>
<p>Para ter uma ideia de volume antes de começar, veja quantas empresas há em cada segmento numa cidade: a página de <a href="/empresas/cidade/passo-fundo-rs">empresas em Passo Fundo</a> mostra todos os segmentos de uma cidade, e a de <a href="/empresas/construtoras/curitiba-pr">construtoras em Curitiba</a> mostra um segmento só. O índice completo está em <a href="/empresas">empresas por segmento e cidade</a>.</p>

<h2>Erros comuns ao montar a lista</h2>
<ul>
<li><strong>Confiar só no CNAE principal.</strong> Há empresas que declaram uma atividade principal e faturam com uma secundária: uma metalúrgica pode estar cadastrada como comércio, por exemplo. Inclua os CNAEs secundários quando a ferramenta permitir.</li>
<li><strong>Lista grande demais.</strong> Dez mil empresas que você nunca vai conseguir abordar valem menos que trezentas bem escolhidas. Trabalhe em lotes.</li>
<li><strong>Não tirar quem já é cliente.</strong> Poucas coisas queimam mais a imagem do que oferecer "conheça nossa empresa" para quem compra de você há anos.</li>
<li><strong>Esquecer que dado envelhece.</strong> Empresa fecha, muda de endereço, troca de sócio. Uma lista de seis meses atrás já precisa de revisão.</li>
<li><strong>Disparar para todo mundo de uma vez.</strong> Ter a lista não é autorização para spam. Aborde de forma individual, diga quem você é e respeite quem pedir para não receber mais contato.</li>
</ul>
<p>Com a lista pronta, o trabalho seguinte é enriquecer, limpar e priorizar. Detalhamos cada etapa em <a href="/blog/como-montar-lista-de-prospeccao">como montar uma lista de prospecção</a>.</p>

<h2>Lista por cidade com o TurboVenda</h2>
<p>A base do TurboVenda tem 6.739.551 CNPJs ativos dos dados abertos da Receita Federal, em 5.572 cidades dos 27 estados. Você descreve o que vende, a IA (Claude) gera os termos de busca, e o robô coleta telefone, e-mail, site e decisor de fontes públicas. Os leads entram direto num CRM Kanban, prontos para a primeira abordagem.</p>

<p><strong>Próximo passo:</strong> descubra quantas empresas do seu segmento existem na sua cidade, e qual o perfil delas, com a <a href="/ferramentas/lista-de-empresas">ferramenta gratuita de lista de empresas</a>, sem login. Quando quiser os contatos, é só <a href="/cadastro?utm_source=blog&utm_medium=organic&utm_campaign=lista-de-empresas-por-cidade">criar conta grátis com 50 leads</a>, sem cartão de crédito.</p>
"""
    },
    {
        'slug': 'base-de-dados-de-empresas-cnpj',
        'titulo': 'Base de Dados de Empresas CNPJ: O Que a Receita Divulga e Como Usar na Prospecção',
        'desc': 'Entenda a base de dados aberta de CNPJ da Receita Federal: quais campos ela tem, o que falta, como usar para prospectar empresas e os cuidados com a LGPD.',
        'keywords': 'base de dados de empresas cnpj, dados abertos cnpj, base cnpj receita federal, cadastro de empresas, quadro de sócios',
        'data': '2026-10-17',
        'tempo': '7 min',
        'conteudo': """
<p>Todo CNPJ do Brasil está numa base pública. A Receita Federal divulga o cadastro de pessoas jurídicas como <strong>dado aberto</strong>: qualquer pessoa pode baixar, sem pagar e sem pedir autorização. Para quem vende B2B, é a fonte mais completa que existe para saber quais empresas existem, o que fazem, onde ficam e quem são os sócios. Mas a base tem limites, e usá-la direto exige trabalho técnico. Este guia explica o que tem nela, o que falta e como transformar isso em lista de prospecção.</p>

<h2>O que são os dados abertos do CNPJ</h2>
<p>A Receita publica periodicamente um conjunto de arquivos compactados com o Cadastro Nacional da Pessoa Jurídica. Entram todos os CNPJs, inclusive os baixados, suspensos e inaptos. Os arquivos somam vários gigabytes, vêm em texto separado por ponto e vírgula e são divididos em partes. Não dá para abrir no Excel e sair usando: é preciso importar num banco de dados e cruzar as tabelas pelo CNPJ.</p>

<h2>Quais arquivos e campos existem</h2>
<table>
<thead><tr><th>Arquivo</th><th>Campos principais</th><th>Uso na prospecção</th></tr></thead>
<tbody>
<tr><td>Empresas</td><td>CNPJ básico (as 8 primeiras posições do CNPJ), razão social, natureza jurídica, capital social, porte</td><td>Saber se é Ltda, S.A. ou empresário individual; filtrar por porte</td></tr>
<tr><td>Estabelecimentos</td><td>CNPJ completo, matriz ou filial, nome fantasia, situação cadastral, data de início da atividade, CNAE principal e secundários, endereço, município, UF, telefones, e-mail</td><td>Filtrar por atividade, cidade e situação; montar rota; primeiro contato</td></tr>
<tr><td>Sócios</td><td>Nome do sócio, qualificação (sócio-administrador, administrador etc.), data de entrada na sociedade, faixa etária; CPF parcialmente mascarado</td><td>Identificar quem decide em empresas pequenas</td></tr>
<tr><td>Simples</td><td>Opção pelo Simples Nacional e pelo MEI, com datas</td><td>Separar MEI de empresa com estrutura</td></tr>
<tr><td>Tabelas auxiliares</td><td>Descrição de CNAEs, municípios, naturezas jurídicas e qualificações de sócio</td><td>Traduzir códigos em texto</td></tr>
</tbody>
</table>
<p>O porte segue a classificação da Receita: microempresa, empresa de pequeno porte (EPP) e "demais", que junta médias e grandes. A situação cadastral distingue ativa, suspensa, inapta, baixada e nula. Para prospecção, quase sempre interessa apenas a ativa.</p>

<h2>O que a base não tem</h2>
<ul>
<li><strong>Faturamento e número de funcionários.</strong> O capital social às vezes é usado como pista, mas é o valor declarado no contrato social e pode não ter relação com o tamanho real do negócio.</li>
<li><strong>Contato atualizado.</strong> Telefone e e-mail são os informados no cadastro. É comum que sejam do contador que fez o registro ou de um número que já mudou.</li>
<li><strong>Site, redes sociais e WhatsApp.</strong> Precisam vir de outras fontes públicas.</li>
<li><strong>Cargo de quem compra.</strong> O quadro de sócios mostra donos e administradores, não o gerente de compras ou de manutenção.</li>
</ul>

<h2>Como usar a base para prospectar</h2>
<h3>1. Filtre pelo que define seu cliente</h3>
<p>A combinação mais usada é <strong>situação ativa + CNAE + município + porte</strong>. Um escritório de contabilidade de Porto Alegre que atende empresas de tecnologia filtraria os CNAEs de software (como 6201-5/01, desenvolvimento de software sob encomenda) na capital e na região metropolitana, com porte micro e EPP. Se o CNAE ainda é novidade, veja <a href="/blog/o-que-e-cnae-prospeccao">o que é CNAE e como usar na prospecção</a>.</p>
<h3>2. Use a data de abertura como gatilho</h3>
<p>Empresas abertas há poucos meses estão montando tudo: contador, sistema, uniforme, seguro, site. Para quem vende esse tipo de serviço, uma lista de empresas novas na região é uma lista de gente com necessidade real e, muitas vezes, sem fornecedor definido.</p>
<h3>3. Decida entre matriz e filial</h3>
<p>Uma rede com cinco unidades aparece cinco vezes, uma por estabelecimento. Se a compra é centralizada, aborde a matriz. Se cada unidade compra sozinha (manutenção predial, por exemplo), cada filial é um lead.</p>
<h3>4. Use os sócios para chegar no decisor</h3>
<p>Em empresas de 2 a 50 funcionários, o sócio-administrador costuma ser quem decide ou quem assina. O nome que aparece no quadro de sócios serve para pedir a pessoa certa na ligação e para conferir o perfil no LinkedIn. O processo completo está em <a href="/blog/como-encontrar-o-decisor-da-empresa">como encontrar o decisor da empresa</a>.</p>
<h3>5. Enriqueça e limpe antes de abordar</h3>
<p>Com a lista filtrada, busque telefone, site e e-mail atualizados, tire duplicados e quem já é cliente. Só então comece os contatos.</p>

<h2>Baixar e tratar sozinho ou usar uma ferramenta?</h2>
<p>Se você tem alguém técnico e tempo, baixar a base direto é possível: os arquivos são públicos. O custo está no trabalho: importar, cruzar tabelas, refazer tudo a cada nova publicação e depois buscar os contatos fora da base. Para uma PME que quer apenas uma lista de clientes potenciais, costuma fazer mais sentido usar algo pronto. O TurboVenda, por exemplo, já tem 6.739.551 CNPJs ativos da Receita organizados em 5.572 cidades dos 27 estados, e complementa com telefone, e-mail, site e decisor coletados de fontes públicas. Dá para ver o volume de empresas por segmento e cidade em <a href="/empresas">empresas por segmento e cidade</a>.</p>

<h2>E a LGPD?</h2>
<p>Os dados de CNPJ são públicos, mas isso não libera qualquer uso. Dados de pessoa jurídica, em si, não são dados pessoais. Já o nome dos sócios e, no caso de MEI e empresário individual, a própria razão social (que costuma ser o nome da pessoa) são dados pessoais e estão sob a LGPD.</p>
<p>A prospecção B2B com dados públicos de empresas geralmente se apoia no <strong>legítimo interesse</strong> (art. 7º, IX, da LGPD), desde que o contato tenha relação com a atividade da empresa e respeite as expectativas de quem recebe. Na prática:</p>
<ul>
<li>aborde a empresa sobre algo que faz sentido para o negócio dela;</li>
<li>diga quem você é e de onde veio o contato, se perguntarem;</li>
<li>ofereça uma forma simples de não receber mais mensagens e respeite o pedido;</li>
<li>não dispare mensagens em massa sem critério e não guarde dados que não vai usar.</li>
</ul>
<p>Isto é orientação geral, não parecer jurídico. Se o seu caso tiver particularidades, converse com um advogado especializado em proteção de dados. E se a dúvida é sobre comprar listas prontas, leia antes o guia sobre <a href="/blog/mailing-de-empresas">mailing de empresas</a>.</p>

<p><strong>Próximo passo:</strong> veja quantas empresas ativas do seu segmento existem em qualquer cidade, com porte e perfil, na <a href="/ferramentas/lista-de-empresas">ferramenta gratuita de lista de empresas</a>. Para receber os contatos e o decisor de cada uma, é só <a href="/cadastro?utm_source=blog&utm_medium=organic&utm_campaign=base-de-dados-de-empresas-cnpj">criar conta grátis com 50 leads</a>, sem cartão.</p>
"""
    },
    {
        'slug': 'mailing-de-empresas',
        'titulo': 'Mailing de Empresas Grátis: Onde Conseguir, Riscos e a Alternativa Legal',
        'desc': 'Onde conseguir mailing de empresas grátis, por que comprar lista pronta é arriscado e como montar sua própria base B2B a partir de dados públicos.',
        'keywords': 'mailing de empresas, mailing de empresas grátis, comprar mailing, lista de e-mails de empresas, base de contatos b2b',
        'data': '2026-10-17',
        'tempo': '6 min',
        'conteudo': """
<p>"Mailing de empresas grátis" é uma das buscas mais comuns de quem precisa vender e está sem lista. A ideia é simples: um arquivo com centenas de empresas, telefone e e-mail, pronto para disparar. Na prática, o mailing pronto costuma trazer mais problema do que cliente. Este guia mostra onde conseguir dados de empresas sem pagar, quais os riscos de comprar listas e qual é a alternativa que funciona sem atropelar a lei.</p>

<h2>O que é um mailing de empresas</h2>
<p>Mailing é uma lista de contatos usada para envio de mensagens: antes eram cartas, hoje são e-mail e WhatsApp. No B2B, um mailing traz no mínimo o nome da empresa e um canal de contato. Os bons trazem também segmento, cidade, porte e o nome de quem decide. A diferença entre um mailing que gera reunião e um que só gera descadastro está nesses detalhes.</p>

<h2>Onde conseguir dados de empresas de graça</h2>
<h3>Dados abertos da Receita Federal</h3>
<p>O cadastro de CNPJ é público e gratuito. Traz razão social, CNAE, porte, endereço e, às vezes, telefone e e-mail. O ponto fraco é justamente o contato: foi informado no cadastro, muitas vezes na abertura da empresa, e pode ser do contador ou estar desatualizado. Os campos estão explicados no guia da <a href="/blog/base-de-dados-de-empresas-cnpj">base de dados de empresas CNPJ</a>.</p>
<h3>Sites das próprias empresas</h3>
<p>A página de contato do site é a fonte mais confiável de telefone e e-mail comercial. Leva tempo visitar um por um, mas o dado é atual e foi publicado pela empresa justamente para receber contato.</p>
<h3>Google Maps e buscadores</h3>
<p>Buscar "transportadora em Chapecó" ou "confecção em Brusque" traz nome, telefone, site e horário de funcionamento. Funciona bem para segmentos com presença local.</p>
<h3>Associações, federações e feiras</h3>
<p>Associações comerciais, sindicatos patronais e federações das indústrias às vezes publicam a lista de associados. Feiras regionais divulgam catálogos de expositores. São listas menores, mas de empresas ativas.</p>
<h3>LinkedIn</h3>
<p>Não é um mailing, mas é onde você confirma quem trabalha na empresa e em qual cargo.</p>

<h2>Os riscos de comprar lista pronta</h2>
<p>Não faltam ofertas de mailing com dezenas de milhares de empresas por preço baixo. Antes de comprar, considere:</p>
<ul>
<li><strong>Origem desconhecida.</strong> Você não sabe como os dados foram coletados nem se havia base legal para isso. Ao usar a lista, você passa a tratar esses dados e responde pelo uso que faz deles.</li>
<li><strong>Dados velhos.</strong> Listas revendidas há anos trazem e-mails que não existem mais e telefones de empresas fechadas.</li>
<li><strong>Reputação do seu domínio.</strong> Disparar para muitos e-mails inválidos, ou para endereços que nunca ouviram falar de você, aumenta a chance de suas mensagens irem para o spam, inclusive as que você manda para clientes atuais.</li>
<li><strong>Bloqueio no WhatsApp.</strong> Mensagem em massa para quem não te conhece gera denúncias, e números denunciados podem ser restringidos ou banidos.</li>
<li><strong>Lista sem foco.</strong> O mailing genérico mistura padaria, indústria e consultório. Você gasta tempo e reputação falando com quem nunca compraria.</li>
<li><strong>Prospects saturados.</strong> Se a mesma lista foi vendida para seus concorrentes, essas empresas recebem abordagens parecidas toda semana.</li>
</ul>
<h3>Se mesmo assim for comprar, pergunte</h3>
<ol>
<li>De onde vieram os dados e qual foi a base legal da coleta?</li>
<li>Quando foi a última atualização?</li>
<li>Os contatos são da empresa (comerciais) ou pessoais?</li>
<li>Há reposição de contatos inválidos?</li>
<li>Posso testar uma amostra antes de pagar?</li>
</ol>

<h2>A alternativa legal: montar sua própria base</h2>
<p>O que costuma funcionar melhor para PMEs B2B é construir a própria lista, pequena e focada, a partir de dados públicos e com uma finalidade clara. O processo:</p>
<ol>
<li><strong>Defina o cliente ideal:</strong> segmento, porte e região. Exemplo: uma empresa de segurança do trabalho de Chapecó que atende frigoríficos, transportadoras e indústrias de alimentos no oeste catarinense.</li>
<li><strong>Filtre os CNPJs ativos</strong> desses segmentos nas cidades certas, usando o CNAE.</li>
<li><strong>Enriqueça cada empresa</strong> com telefone, site, e-mail comercial e decisor, de fontes públicas.</li>
<li><strong>Aborde de forma individual</strong>, explicando por que está entrando em contato com aquela empresa.</li>
<li><strong>Ofereça saída.</strong> Uma frase como "se não fizer sentido, me avise que não envio mais" resolve, e o pedido precisa ser respeitado.</li>
<li><strong>Mantenha uma lista de quem pediu para sair</strong> e cruze com ela antes de cada nova rodada.</li>
</ol>
<p>Esse caminho costuma se apoiar no legítimo interesse previsto na LGPD para contatos B2B relevantes, desde que haja opção de saída e nada de spam. Não substitui a orientação de um advogado em casos específicos, mas é muito diferente de disparar para uma lista comprada sem saber a origem. O passo a passo detalhado está em <a href="/blog/como-montar-lista-de-prospeccao">como montar uma lista de prospecção</a>, e modelos de primeiro e-mail em <a href="/blog/email-marketing-b2b-templates">templates de e-mail B2B</a>.</p>

<h2>Quanto custa fazer isso</h2>
<p>Feito à mão, custa tempo: horas por semana pesquisando empresa por empresa. Com uma ferramenta, o trabalho repetitivo diminui muito. O TurboVenda parte de uma base de 6.739.551 CNPJs ativos da Receita em 5.572 cidades; a IA (Claude) gera os termos de busca a partir do que você vende, e o robô coleta telefone, e-mail, site e decisor de fontes públicas. O plano grátis tem 50 leads, sem cartão; o Starter custa R$ 97/mês e o Pro, R$ 297/mês.</p>

<p><strong>Comece pelo tamanho do mercado:</strong> a <a href="/ferramentas/lista-de-empresas">ferramenta gratuita de lista de empresas</a> mostra quantas empresas do seu segmento existem em cada cidade, sem login. Para montar o seu próprio mailing, com contatos e decisor, é só <a href="/cadastro?utm_source=blog&utm_medium=organic&utm_campaign=mailing-de-empresas">criar conta grátis com 50 leads</a>.</p>
"""
    },
    {
        'slug': 'mensagem-de-prospeccao-whatsapp',
        'titulo': 'Mensagem de Prospecção no WhatsApp: 12 Modelos Prontos para B2B',
        'desc': '12 modelos de mensagem de prospecção no WhatsApp prontos para copiar: primeiro contato, indicação, pós-feira, representante, follow-up e encerramento.',
        'keywords': 'mensagem de prospecção whatsapp, mensagem de prospecção pronta, modelo de mensagem whatsapp vendas, abordagem whatsapp b2b, script de prospecção',
        'data': '2026-10-17',
        'tempo': '7 min',
        'conteudo': """
<p>A primeira mensagem no WhatsApp decide se a conversa começa ou se o contato te bloqueia. No B2B, quem recebe é dono de empresa, comprador ou gerente: gente ocupada, sem tempo para texto longo nem para "bom dia, tudo bem?" sem assunto. Abaixo estão 12 modelos prontos, separados por situação, e as regras que fazem eles funcionarem.</p>

<h2>Antes de copiar: 6 regras</h2>
<ul>
<li><strong>Diga quem você é e por que está escrevendo</strong> logo na primeira mensagem.</li>
<li><strong>Uma mensagem curta, uma pergunta.</strong> Se a pessoa precisar rolar a tela, você já perdeu.</li>
<li><strong>Personalize com algo real:</strong> a cidade, o segmento, um produto que a empresa fabrica.</li>
<li><strong>Não mande áudio</strong> para quem ainda não conversou com você, nem link logo de cara.</li>
<li><strong>Horário comercial.</strong> Prospecção às 22h passa a impressão errada.</li>
<li><strong>Ofereça saída.</strong> Uma linha como "se não for com você, me avisa" é educação e reduz denúncias. Quem pedir para parar não recebe mais nada.</li>
</ul>
<p>Troque o que está entre colchetes. As cidades e segmentos dos exemplos servem só para mostrar o tom.</p>

<h2>Primeiro contato</h2>
<h3>1. Dono de pequena indústria (contato frio)</h3>
<blockquote>Oi, [Nome], aqui é o [Seu nome], da [Sua empresa], de Joinville. A gente fabrica embalagens plásticas para indústria de alimentos aqui de SC. Vi que a [Empresa] produz [produto] e queria entender: hoje vocês compram embalagem de fora do estado ou de fornecedor local? Se não for com você, me indica quem cuida disso?</blockquote>

<h3>2. Número geral da empresa (quem atende não decide)</h3>
<blockquote>Bom dia! Sou o [Seu nome], da [Sua empresa]. Trabalho com [o que você faz, em poucas palavras] para [segmento]. Quem aí cuida de [compras / manutenção / financeiro]? Queria mandar uma mensagem curta direto para a pessoa certa, sem tomar o tempo de vocês.</blockquote>

<h3>3. Indicação</h3>
<blockquote>Oi, [Nome], tudo bem? O [Nome de quem indicou], da [Empresa dele], comentou que vocês estão [revendo fornecedores de X / aumentando a produção] e sugeriu que eu falasse contigo. Sou o [Seu nome], da [Sua empresa]. Tem 15 minutos nesta semana para eu entender o cenário de vocês?</blockquote>

<h3>4. Empresa recém-aberta</h3>
<blockquote>Oi, [Nome]! Vi que a [Empresa] começou as atividades há pouco tempo em [Cidade], parabéns pelo início. Sou o [Seu nome], da [Sua empresa], e ajudamos empresas novas de [segmento] com [contabilidade / sistema de gestão / uniformes]. Vocês já têm isso resolvido ou ainda estão montando?</blockquote>

<h3>5. Empresa em expansão</h3>
<blockquote>Oi, [Nome]. Vi que a [Empresa] [abriu uma filial em X / está contratando para a produção]. Quando a operação cresce, [a dor ligada ao que você vende, ex.: o controle da manutenção das máquinas costuma apertar]. A gente resolve isso para [segmento] na região. Faz sentido conversar?</blockquote>

<h2>Representante comercial</h2>
<h3>6. Apresentando uma linha nova</h3>
<blockquote>Oi, [Nome], aqui é o [Seu nome], representante da [Representada] na região de [Passo Fundo]. A [Representada] lançou [produto/linha] para [aplicação]. Posso te mandar a ficha técnica e a tabela? Se preferir, passo aí na próxima visita à cidade.</blockquote>

<h3>7. Agendando visita na rota</h3>
<blockquote>Oi, [Nome]! Vou estar em [Erechim] na [quinta-feira] visitando clientes da [Representada]. Consigo passar aí 20 minutos para mostrar [produto]. Fica melhor de manhã ou à tarde?</blockquote>

<h2>Eventos e retomadas</h2>
<h3>8. Depois de uma feira ou evento</h3>
<blockquote>Oi, [Nome], aqui é o [Seu nome], da [Sua empresa]. A gente conversou rapidamente no [estande / evento] sobre [assunto]. Como combinado, te mando [o catálogo / o contato do técnico]. Qual o melhor dia para uma conversa de 15 minutos?</blockquote>

<h3>9. Ex-cliente ou cliente inativo</h3>
<blockquote>Oi, [Nome], tudo certo? Aqui é o [Seu nome], da [Sua empresa]. Faz um tempo que a [Empresa] não compra com a gente e queria entender se ficou alguma coisa mal resolvida do nosso lado. Desde então mudamos [prazo de entrega / linha / atendimento]. Posso te mostrar?</blockquote>

<h2>Follow-up</h2>
<h3>10. Depois de um e-mail sem resposta</h3>
<blockquote>Oi, [Nome], te mandei um e-mail na [segunda] sobre [assunto em poucas palavras]. Sei que a caixa de entrada vive cheia, então resumo aqui: [benefício em uma frase]. Vale uma conversa rápida ou não é prioridade agora?</blockquote>

<h3>11. Depois de enviar proposta</h3>
<blockquote>Oi, [Nome]. Conseguiu olhar a proposta que mandei na [data]? Se ficou alguma dúvida sobre [prazo / condição / especificação], posso explicar por aqui ou numa ligação de 10 minutos.</blockquote>

<h3>12. Última mensagem (encerramento)</h3>
<blockquote>Oi, [Nome], não quero ficar insistindo. Imagino que [assunto] não seja prioridade agora, então vou parar por aqui. Se o cenário mudar, é só me chamar neste número. Obrigado pela atenção!</blockquote>

<h2>O que não fazer</h2>
<ul>
<li>Mandar o mesmo texto para centenas de números de uma vez. Além de não funcionar, é o caminho mais rápido para ter o número restringido.</li>
<li>Abrir com "Oi, tudo bem?" e esperar resposta para só depois dizer o assunto.</li>
<li>Colar um catálogo em PDF de 20 páginas na primeira mensagem.</li>
<li>Insistir depois de um "não tenho interesse". Agradeça e encerre.</li>
</ul>
<p>Mais sobre o canal em <a href="/blog/whatsapp-para-vendas-b2b">WhatsApp para vendas B2B</a>, e sobre quantas vezes voltar a falar com quem não respondeu em <a href="/blog/follow-up-de-vendas">follow-up de vendas</a>. Se a dificuldade é saber para quem mandar, veja <a href="/blog/como-encontrar-o-decisor-da-empresa">como encontrar o decisor da empresa</a>.</p>

<h2>Personalizar sem gastar a tarde</h2>
<p>Os modelos funcionam melhor quando cada mensagem cita algo específico da empresa. No TurboVenda, a IA (Claude) escreve a abordagem de WhatsApp e de e-mail para cada lead, e o contato fica registrado no CRM Kanban (Novo, Contactado, Respondeu, Qualificado, Demo, Convertido).</p>

<p><strong>Quer uma mensagem sob medida agora?</strong> O <a href="/ferramentas/gerador-de-mensagem-de-prospeccao">gerador de mensagem de prospecção</a> escreve com IA o primeiro contato por WhatsApp ou e-mail, de graça. Para ter também a lista de empresas com contato e decisor, é só <a href="/cadastro?utm_source=blog&utm_medium=organic&utm_campaign=mensagem-de-prospeccao-whatsapp">criar conta grátis com 50 leads</a>.</p>
"""
    },
    {
        'slug': 'como-fazer-prospeccao-ativa',
        'titulo': 'Como Fazer Prospecção Ativa: Passo a Passo e Rotina Diária',
        'desc': 'Aprenda a fazer prospecção ativa B2B: passo a passo do perfil de cliente ao follow-up, uma rotina diária para quem vende sozinho e os erros que travam.',
        'keywords': 'como fazer prospecção ativa, prospecção ativa, prospecção ativa b2b, rotina de prospecção, prospecção de clientes',
        'data': '2026-10-17',
        'tempo': '7 min',
        'conteudo': """
<p>Prospecção ativa é ir atrás do cliente em vez de esperar que ele apareça. Você escolhe as empresas, encontra quem decide e inicia a conversa por telefone, WhatsApp, e-mail ou visita. Para a PME B2B que depende de indicação e vê o faturamento oscilar de um mês para o outro, é a forma mais direta de ganhar previsibilidade. O difícil quase nunca é entender o conceito; é transformar em rotina. Este guia traz o passo a passo e uma rotina diária para quem vende sozinho ou com um time pequeno.</p>

<h2>Prospecção ativa x passiva</h2>
<p>Na prospecção passiva (ou inbound), o cliente chega até você por site, anúncio, indicação ou redes sociais. Na ativa (ou outbound), você decide com quem quer falar. As duas se complementam, mas a ativa tem uma vantagem clara para quem está começando ou quer crescer numa região: você não depende de o cliente já saber que você existe.</p>

<h2>Passo a passo</h2>
<h3>1. Defina com quem você quer falar</h3>
<p>Olhe para os seus melhores clientes e descubra o que eles têm em comum: segmento, porte, região, momento. Uma empresa de instalações elétricas industriais de Curitiba pode perceber que fecha mais com indústrias de médio porte da região metropolitana que estão ampliando o galpão. Esse é o perfil a perseguir.</p>
<h3>2. Monte a lista</h3>
<p>Transforme o perfil em filtros (CNAE, porte, cidade) e chegue a uma lista de empresas reais, com contato. O processo completo está em <a href="/blog/como-montar-lista-de-prospeccao">como montar uma lista de prospecção</a>.</p>
<h3>3. Encontre o decisor</h3>
<p>Em empresa pequena, é o dono. Em empresa média, é o gestor da área que sente o problema (manutenção, compras, financeiro) e o dono que assina. Tenha pelo menos um nome antes de ligar.</p>
<h3>4. Escolha os canais</h3>
<p>Telefone abre conversa mais rápido; WhatsApp facilita a resposta; e-mail serve para mandar algo que a pessoa vai querer ler com calma; visita funciona quando a região é próxima e o ticket justifica. Combinar canais costuma render mais do que insistir num só.</p>
<h3>5. Prepare a abordagem</h3>
<p>Uma frase sobre quem você é, uma sobre por que escolheu aquela empresa e uma pergunta. Nada de apresentação institucional. Se precisar de um ponto de partida, o <a href="/ferramentas/gerador-de-mensagem-de-prospeccao">gerador de mensagem de prospecção</a> escreve uma primeira versão com IA.</p>
<h3>6. Planeje o follow-up</h3>
<p>Pouca gente responde ao primeiro contato. Defina antes quantas tentativas vai fazer e em quais dias, para não depender da memória. Sugestões de cadência em <a href="/blog/follow-up-de-vendas">follow-up de vendas</a>.</p>
<h3>7. Registre tudo</h3>
<p>Cada lead precisa ter etapa e próxima ação com data. Sem isso, os retornos se perdem no meio das conversas do WhatsApp. Um <a href="/blog/pipeline-de-vendas-como-montar">pipeline de vendas</a> simples, em Kanban, resolve.</p>
<h3>8. Meça e ajuste toda semana</h3>
<p>Acompanhe quatro números: empresas abordadas, conversas iniciadas, reuniões marcadas e propostas enviadas. Se muita gente é abordada e pouca responde, o problema está na lista ou na mensagem. Se há conversa mas não há reunião, está na qualificação ou na oferta. Se há proposta mas não há venda, está no preço, no prazo ou em quem você está deixando de envolver na decisão.</p>

<h2>Rotina diária de prospecção ativa</h2>
<p>Uma sugestão para quem divide a prospecção com outras tarefas. Ajuste os horários à sua realidade; o importante é que os blocos estejam na agenda e sejam respeitados como uma reunião com cliente.</p>
<table>
<thead><tr><th>Horário</th><th>Atividade</th></tr></thead>
<tbody>
<tr><td>8h00 às 8h30</td><td>Separar os leads do dia e revisar os follow-ups agendados</td></tr>
<tr><td>8h30 às 10h30</td><td>Bloco de ligações e primeiras mensagens de WhatsApp, sem abrir o e-mail</td></tr>
<tr><td>10h30 às 11h30</td><td>Responder retornos e fazer os follow-ups do dia</td></tr>
<tr><td>14h00 às 15h00</td><td>E-mails personalizados para quem não atendeu de manhã</td></tr>
<tr><td>15h00 às 17h00</td><td>Reuniões, visitas e propostas</td></tr>
<tr><td>17h00 às 17h30</td><td>Atualizar o CRM e preparar a lista de amanhã</td></tr>
</tbody>
</table>
<p>Quem vende sozinho e também cuida da operação pode começar com um único bloco de uma hora e meia por dia, sempre no mesmo horário. Constância vale mais do que um dia inteiro de ligações uma vez por mês.</p>

<h2>Quantos contatos por dia?</h2>
<p>Depende da sua meta, do seu ticket médio e das suas taxas de conversão. A conta parte do faturamento desejado e volta, etapa por etapa, até o número de empresas a abordar por dia. O método está explicado em <a href="/blog/quantos-leads-preciso-para-bater-a-meta">quantos leads preciso para bater a meta</a>.</p>

<h2>Erros que travam a prospecção ativa</h2>
<ul>
<li><strong>Prospectar só quando a venda cai.</strong> O resultado de hoje vem da prospecção de semanas atrás. Parar quando o mês está bom prepara um mês ruim lá na frente.</li>
<li><strong>Gastar a manhã montando lista.</strong> Pesquisa e contato são tarefas diferentes; misturar as duas mata o bloco de ligações.</li>
<li><strong>Abordar todo mundo igual.</strong> Uma usinagem de Caxias do Sul e uma clínica odontológica de Londrina não têm o mesmo problema nem falam a mesma língua.</li>
<li><strong>Desistir no primeiro silêncio.</strong> Falta de resposta raramente é um "não".</li>
<li><strong>Não registrar o motivo da perda.</strong> É com ele que você ajusta o perfil de cliente e a oferta.</li>
</ul>

<h2>Onde o TurboVenda entra</h2>
<p>A parte que mais consome tempo da prospecção ativa é encontrar empresas e contatos. No TurboVenda, você descreve o que vende, a IA (Claude) gera os termos de busca, e o robô encontra empresas numa base de 6.739.551 CNPJs ativos da Receita, coletando telefone, e-mail, site e decisor de fontes públicas. A IA também escreve a abordagem de e-mail e WhatsApp, e os leads seguem no Kanban: Novo, Contactado, Respondeu, Qualificado, Demo e Convertido.</p>

<p><strong>Comece pela meta:</strong> a <a href="/ferramentas/calculadora-de-leads">calculadora de leads</a> mostra quantos contatos por dia você precisa para chegar ao faturamento que quer. Depois, é só <a href="/cadastro?utm_source=blog&utm_medium=organic&utm_campaign=como-fazer-prospeccao-ativa">criar conta grátis com 50 leads</a> e fazer o primeiro bloco de prospecção hoje mesmo.</p>
"""
    },
    {
        'slug': 'quantos-leads-preciso-para-bater-a-meta',
        'titulo': 'Quantos Leads Preciso para Bater a Meta? O Cálculo do Funil Reverso',
        'desc': 'Aprenda a calcular quantos leads você precisa para bater a meta de vendas com o funil reverso: fórmula, exemplo passo a passo e como achar as suas taxas.',
        'keywords': 'quantos leads preciso, funil reverso, meta de vendas, cálculo de leads, taxa de conversão de vendas',
        'data': '2026-10-17',
        'tempo': '6 min',
        'conteudo': """
<p>"Quantas empresas eu preciso abordar para fechar o mês?" A resposta não está num número mágico do mercado, e sim nos seus próprios dados. O método para chegar nela se chama <strong>funil reverso</strong>: você começa pela meta de faturamento e volta, etapa por etapa, até o número de empresas que precisa abordar por dia.</p>

<h2>O que é o funil reverso</h2>
<p>O funil de vendas normal vai de cima para baixo: muitos leads entram, poucos viram clientes. O funil reverso faz a conta ao contrário. Se você sabe quanto quer vender e qual é a taxa de conversão de cada etapa, descobre quantas oportunidades precisa ter em cada uma delas.</p>
<p>As etapas mudam de empresa para empresa, mas um funil B2B de PME costuma ter algo como:</p>
<ol>
<li><strong>Leads abordados:</strong> empresas que receberam um primeiro contato.</li>
<li><strong>Conversas:</strong> empresas que responderam e trocaram alguma ideia.</li>
<li><strong>Reuniões:</strong> conversas que viraram reunião ou visita de diagnóstico.</li>
<li><strong>Propostas:</strong> reuniões que viraram orçamento ou proposta formal.</li>
<li><strong>Vendas:</strong> propostas aceitas.</li>
</ol>

<h2>A fórmula</h2>
<ol>
<li><strong>Vendas necessárias</strong> = meta de faturamento ÷ ticket médio.</li>
<li><strong>Propostas</strong> = vendas ÷ taxa de proposta para venda.</li>
<li><strong>Reuniões</strong> = propostas ÷ taxa de reunião para proposta.</li>
<li><strong>Conversas</strong> = reuniões ÷ taxa de conversa para reunião.</li>
<li><strong>Leads abordados</strong> = conversas ÷ taxa de lead para conversa.</li>
<li><strong>Leads por dia</strong> = leads abordados ÷ dias úteis do mês.</li>
</ol>
<p>Arredonde sempre para cima: não existe meia reunião.</p>

<h2>Exemplo passo a passo (com números inventados)</h2>
<p><strong>Atenção: todos os números deste exemplo são fictícios</strong>, escolhidos só para mostrar a conta. Não são média de mercado nem referência para o seu negócio. Use as suas próprias taxas.</p>
<p>Imagine uma empresa de manutenção industrial de Joinville que quer <strong>R$ 50.000 por mês em vendas novas</strong>, com <strong>ticket médio de R$ 5.000</strong>. Suponha que, no histórico dela, 25% das propostas viram venda, 50% das reuniões viram proposta, 40% das conversas viram reunião e 25% dos leads abordados respondem.</p>
<table>
<thead><tr><th>Etapa</th><th>Conta</th><th>Resultado</th></tr></thead>
<tbody>
<tr><td>Vendas</td><td>R$ 50.000 ÷ R$ 5.000</td><td>10</td></tr>
<tr><td>Propostas</td><td>10 ÷ 25%</td><td>40</td></tr>
<tr><td>Reuniões</td><td>40 ÷ 50%</td><td>80</td></tr>
<tr><td>Conversas</td><td>80 ÷ 40%</td><td>200</td></tr>
<tr><td>Leads abordados no mês</td><td>200 ÷ 25%</td><td>800</td></tr>
<tr><td>Leads por dia (20 dias úteis)</td><td>800 ÷ 20</td><td>40</td></tr>
</tbody>
</table>
<p>Nesse exemplo, a empresa precisaria abordar 40 empresas novas por dia útil. Com dois vendedores, 20 por pessoa. É aqui que o funil reverso mostra o seu valor: ele transforma uma meta abstrata numa tarefa diária concreta e deixa claro se a meta é realista com a estrutura que você tem hoje.</p>

<h2>De onde tirar as suas taxas</h2>
<ul>
<li><strong>Do seu CRM.</strong> Conte, nos últimos três a seis meses, quantos leads passaram por cada etapa. É o dado mais confiável que você vai ter.</li>
<li><strong>Se você não tem histórico,</strong> comece com estimativas conservadoras, rode um mês registrando tudo e refaça a conta com os números reais.</li>
<li><strong>Cuidado com médias de mercado.</strong> As taxas variam com o segmento, o ticket, a região e a qualidade da lista. Um número de outro setor pode levar a um planejamento errado.</li>
</ul>

<h2>Não esqueça o ciclo de venda</h2>
<p>Se entre o primeiro contato e o fechamento passam uns dois meses no seu negócio, os leads que você aborda hoje viram faturamento só lá na frente. Por isso a prospecção não pode parar quando o mês está bom. Em mercados sazonais, como os fornecedores do agronegócio no norte do RS e no oeste do PR, vale começar a prospectar antes da época em que os clientes costumam fechar as compras.</p>

<h2>Como diminuir o número de leads necessários</h2>
<p>Se a conta deu um número impossível para a sua equipe, existem quatro alavancas:</p>
<ol>
<li><strong>Ticket médio.</strong> Pacotes, contratos anuais e produtos complementares reduzem o número de vendas necessárias.</li>
<li><strong>Qualidade da lista.</strong> Abordar só empresas com o perfil certo melhora a taxa de resposta. Veja <a href="/blog/como-montar-lista-de-prospeccao">como montar uma lista de prospecção</a>.</li>
<li><strong>Follow-up.</strong> Parte de quem não responde ao primeiro contato responde ao segundo ou ao terceiro. Uma cadência organizada melhora a passagem de lead para conversa; veja <a href="/blog/follow-up-de-vendas">follow-up de vendas</a>.</li>
<li><strong>Qualificação.</strong> Fazer menos reuniões, só com quem tem chance real de comprar, melhora a taxa de proposta para venda e libera tempo para prospectar.</li>
</ol>

<h2>Acompanhe toda semana</h2>
<p>O funil reverso não é uma conta para fazer uma vez por ano. Revise toda semana: quantos leads foram abordados, quantas conversas saíram, quantas reuniões foram marcadas. Se uma etapa ficou abaixo do previsto, você sabe onde mexer antes de o mês acabar. A rotina para manter esse ritmo está em <a href="/blog/como-fazer-prospeccao-ativa">como fazer prospecção ativa</a>, e um <a href="/blog/pipeline-de-vendas-como-montar">pipeline de vendas</a> em Kanban deixa esses números visíveis. No TurboVenda, por exemplo, as etapas são Novo, Contactado, Respondeu, Qualificado, Demo e Convertido, o que permite contar a passagem de uma para a outra.</p>

<p><strong>Faça a sua conta:</strong> a <a href="/ferramentas/calculadora-de-leads">calculadora de leads</a> faz essa conta a partir da sua meta de faturamento e mostra quantos leads e contatos por dia você precisa, de graça. Para ter esses leads com telefone, e-mail e decisor, é só <a href="/cadastro?utm_source=blog&utm_medium=organic&utm_campaign=quantos-leads-preciso-para-bater-a-meta">criar conta grátis com 50 leads</a>.</p>
"""
    },
    {
        'slug': 'como-montar-lista-de-prospeccao',
        'titulo': 'Como Montar uma Lista de Prospecção B2B: do ICP à Lista Limpa',
        'desc': 'Passo a passo para montar uma lista de prospecção B2B: defina o ICP, filtre por CNAE, porte e região, enriqueça os contatos e limpe a base antes de abordar.',
        'keywords': 'como montar lista de prospecção, lista de prospecção b2b, lista de clientes potenciais, icp, enriquecimento de leads',
        'data': '2026-10-17',
        'tempo': '7 min',
        'conteudo': """
<p>A maior parte das PMEs B2B não para de prospectar por falta de vontade. Para porque a lista acaba. O vendedor liga para os contatos que tinha, não sabe para quem ligar em seguida e volta a esperar indicação. Uma lista de prospecção bem montada resolve isso: é um estoque de empresas certas, com contato e decisor, pronto para ser trabalhado. Este guia percorre as quatro etapas: perfil de cliente, filtros, enriquecimento e limpeza.</p>

<h2>Etapa 1: defina o perfil de cliente ideal (ICP)</h2>
<p>O ICP (do inglês <em>ideal customer profile</em>) descreve a empresa com mais chance de comprar de você e de ficar satisfeita. O jeito mais rápido de chegar nele é olhar para trás:</p>
<ol>
<li>Liste seus 10 a 20 melhores clientes: os que pagam em dia, compram de novo e dão pouco trabalho.</li>
<li>Para cada um, anote segmento, porte, cidade, tempo de mercado e o motivo que levou à compra.</li>
<li>Procure o que se repete.</li>
</ol>
<p>Exemplo: uma empresa de prevenção contra incêndio de Porto Alegre que faz PPCI percebe que seus melhores clientes são indústrias e depósitos de médio porte da região metropolitana, quase sempre com prazo de regularização apertado. Isso vira o ICP: indústrias e armazéns, porte EPP ou maior, Porto Alegre e cidades vizinhas.</p>

<h2>Etapa 2: transforme o ICP em filtros</h2>
<p>Com o perfil definido, traduza cada característica em um filtro objetivo:</p>
<ul>
<li><strong>Segmento vira CNAE.</strong> É a classificação de atividade econômica de cada CNPJ. Considere o principal e, se possível, os secundários. Se o tema é novo, comece por <a href="/blog/o-que-e-cnae-prospeccao">o que é CNAE</a>.</li>
<li><strong>Porte.</strong> A Receita classifica em microempresa, empresa de pequeno porte e demais. Serve para tirar quem é pequeno ou grande demais para você.</li>
<li><strong>Região.</strong> Municípios ou um raio a partir da sua sede. Pense em logística e no custo de uma visita.</li>
<li><strong>Situação cadastral.</strong> Apenas empresas ativas.</li>
<li><strong>Data de abertura.</strong> Empresas novas para quem vende estrutura; empresas mais antigas para quem propõe troca de fornecedor.</li>
<li><strong>Matriz ou filial.</strong> Define se você aborda a sede ou cada unidade.</li>
</ul>
<p>Para ter noção do volume antes de começar, veja quantas empresas de um segmento existem numa cidade, por exemplo <a href="/empresas/construtoras/curitiba-pr">construtoras em Curitiba</a>. Se a lista der dezenas de milhares, aperte os filtros; se der poucas dezenas, abra mais cidades ou CNAEs. O passo a passo por município está em <a href="/blog/lista-de-empresas-por-cidade">lista de empresas por cidade e por CNAE</a>.</p>

<h2>Etapa 3: enriqueça com contato e decisor</h2>
<p>Os dados da Receita dizem quem a empresa é. Para conversar, você precisa de mais:</p>
<ul>
<li><strong>Telefone atualizado e WhatsApp.</strong> O do cadastro pode ser antigo; confira no site e no perfil da empresa no Google.</li>
<li><strong>Site.</strong> Mostra o que a empresa faz de verdade (às vezes diferente do CNAE) e dá assunto para a abordagem.</li>
<li><strong>E-mail comercial.</strong> Prefira o publicado pela própria empresa. Um e-mail nominal é melhor que o genérico, desde que seja público.</li>
<li><strong>Decisor.</strong> Em empresa pequena, normalmente o sócio-administrador que aparece no quadro de sócios da Receita; em empresas maiores, o gestor da área. Veja <a href="/blog/como-encontrar-o-decisor-da-empresa">como encontrar o decisor da empresa</a>.</li>
</ul>

<h2>Etapa 4: limpe a lista antes de abordar</h2>
<p>Pular a limpeza é o jeito mais rápido de queimar uma boa lista. Antes do primeiro contato:</p>
<ol>
<li><strong>Remova duplicados.</strong> A mesma empresa pode aparecer várias vezes por causa das filiais. As 8 primeiras posições do CNPJ (o CNPJ básico) identificam a empresa; o restante identifica cada estabelecimento.</li>
<li><strong>Tire clientes atuais e negociações em andamento.</strong></li>
<li><strong>Tire concorrentes e parceiros.</strong></li>
<li><strong>Cruze com a lista de quem pediu para não ser contatado.</strong> Respeitar o opt-out é obrigação, não gentileza.</li>
<li><strong>Corrija ou descarte</strong> telefones e e-mails com formato inválido ou que já falharam em tentativas anteriores.</li>
<li><strong>Padronize os campos:</strong> nome da cidade, telefone com DDD, segmento escrito sempre do mesmo jeito.</li>
</ol>

<h2>Modelo de colunas para a sua lista</h2>
<table>
<thead><tr><th>Coluna</th><th>Exemplo</th><th>Para que serve</th></tr></thead>
<tbody>
<tr><td>Empresa (nome fantasia)</td><td>Metalúrgica Exemplo</td><td>Como a empresa é conhecida</td></tr>
<tr><td>CNPJ</td><td>00.000.000/0001-00</td><td>Evitar duplicados</td></tr>
<tr><td>CNAE</td><td>2539-0/01 (usinagem)</td><td>Personalizar a mensagem</td></tr>
<tr><td>Cidade/UF</td><td>Caxias do Sul/RS</td><td>Rota e contexto</td></tr>
<tr><td>Porte</td><td>EPP</td><td>Prioridade</td></tr>
<tr><td>Decisor e cargo</td><td>Nome, sócio-administrador</td><td>Por quem perguntar</td></tr>
<tr><td>Telefone, e-mail e site</td><td>(54) ...</td><td>Canais de contato</td></tr>
<tr><td>Prioridade</td><td>A, B ou C</td><td>Ordem de abordagem</td></tr>
<tr><td>Etapa e próxima ação</td><td>Contactado, ligar dia 12</td><td>Não perder o follow-up</td></tr>
</tbody>
</table>

<h2>Trabalhe em lotes</h2>
<p>Não monte dez mil empresas de uma vez. Monte o suficiente para duas a quatro semanas de abordagem, trabalhe, aprenda com as respostas e ajuste os filtros para o próximo lote. A lista é algo vivo: o que você descobre nas conversas melhora o ICP.</p>

<h2>No braço ou com ferramenta</h2>
<p>Dá para fazer tudo isso com planilha, Google e consulta de CNPJ. Funciona, mas consome horas por semana. O TurboVenda automatiza as etapas 2 e 3: você descreve o que vende, a IA (Claude) gera os termos de busca, e o robô encontra empresas numa base de 6.739.551 CNPJs ativos da Receita e coleta telefone, e-mail, site e decisor de fontes públicas. Os leads caem num CRM Kanban, prontos para abordar.</p>

<p><strong>Teste o tamanho da sua lista:</strong> a <a href="/ferramentas/lista-de-empresas">ferramenta gratuita de lista de empresas</a> mostra quantas empresas do seu segmento existem em qualquer cidade e o perfil delas, sem login. Para montar a lista já com os contatos, é só <a href="/cadastro?utm_source=blog&utm_medium=organic&utm_campaign=como-montar-lista-de-prospeccao">criar conta grátis com 50 leads</a>.</p>
"""
    },
    {
        'slug': 'como-conseguir-clientes-representante-comercial',
        'titulo': 'Como Conseguir Clientes Sendo Representante Comercial',
        'desc': 'Guia prático para representante comercial conseguir clientes: carteira das representadas, mapa do território, rota de visitas e prospecção entre as visitas.',
        'keywords': 'como conseguir clientes representante comercial, representante comercial, prospecção representante comercial, carteira de clientes, rota de visitas',
        'data': '2026-10-17',
        'tempo': '7 min',
        'conteudo': """
<p>O representante comercial vive de comissão, e comissão só vem com pedido. Isso cria uma pressão diferente da de um vendedor contratado: cada semana sem cliente novo é renda que não entra. Ao mesmo tempo, o representante tem uma vantagem que pouca gente aproveita: conhece o território, carrega várias representadas e pode oferecer mais de uma solução para o mesmo comprador. Este guia mostra como transformar isso em clientes novos de forma constante.</p>

<h2>1. Comece pela carteira que já existe</h2>
<p>Antes de prospectar empresas que nunca ouviram falar da sua representada, olhe para dentro:</p>
<ul>
<li><strong>Clientes inativos da representada no seu território.</strong> Peça à fábrica a lista de quem já comprou e parou. Eles conhecem o produto, e às vezes pararam por falta de atendimento, não por insatisfação.</li>
<li><strong>Clientes de uma representada que podem comprar de outra.</strong> Quem compra fixadores de uma representada talvez compre abrasivos da outra. O comprador é o mesmo e já te conhece.</li>
<li><strong>Indicação.</strong> Clientes satisfeitos conhecem outros empresários do setor. Peça de forma direta e específica: "Você conhece alguém em Bento Gonçalves que trabalhe com móveis sob medida e que eu deveria visitar?"</li>
</ul>

<h2>2. Mapeie o território empresa por empresa</h2>
<p>O representante que só visita quem já conhece fica limitado ao próprio caderno de contatos. O ideal é saber quais são todas as empresas do seu segmento-alvo em cada cidade da região. Um representante de insumos para a indústria metalmecânica que atende a Serra Gaúcha, por exemplo, deveria ter a lista de todas as usinagens, serralherias e fabricantes de estruturas metálicas de Caxias do Sul, Farroupilha, Bento Gonçalves, Garibaldi e Carlos Barbosa. Um representante de produtos agropecuários no norte do RS faria o mesmo com revendas e cerealistas de Passo Fundo, Carazinho, Erechim e arredores.</p>
<p>A forma mais rápida é partir do CNAE de cada segmento e filtrar por município. Veja, por exemplo, <a href="/empresas/cidade/passo-fundo-rs">as empresas de Passo Fundo por segmento</a>, e o passo a passo em <a href="/blog/lista-de-empresas-por-cidade">lista de empresas por cidade e por CNAE</a>.</p>

<h2>3. Monte a rota antes de sair</h2>
<p>Visita sem agenda queima combustível e dia de trabalho. Organize a semana por região:</p>
<ol>
<li>Separe clientes e prospects por cidade.</li>
<li>Defina o dia de cada cidade (por exemplo: terça em Caxias, quarta em Bento e Garibaldi, quinta em Farroupilha).</li>
<li>Dois ou três dias antes, mande mensagem aos prospects daquela cidade pedindo um horário.</li>
<li>Deixe espaços na agenda para encaixar visitas de oportunidade no mesmo bairro ou distrito industrial.</li>
</ol>
<p>Uma mensagem simples funciona: "Vou estar em Farroupilha na quinta visitando clientes da [Representada]. Consigo passar 20 minutos aí para mostrar [produto]?" Há mais modelos em <a href="/blog/mensagem-de-prospeccao-whatsapp">mensagens de prospecção para WhatsApp</a>.</p>

<h2>4. Prospecte entre as visitas</h2>
<p>O tempo no escritório é para prospecção a distância: ligações e mensagens para empresas da lista, agendamento das próximas rotas, follow-up de orçamentos. Reserve um bloco fixo, como a segunda de manhã e a sexta à tarde, só para isso. Se o bloco não estiver na agenda, a semana de visitas engole a prospecção.</p>

<h2>5. Fale a língua de cada comprador</h2>
<p>O mesmo produto é vendido de jeitos diferentes para o dono de uma confecção pequena em Brusque e para o comprador de uma indústria de embalagens em Joinville. O dono quer saber de preço, prazo e se resolve o problema dele agora. O comprador da indústria vai pedir ficha técnica, cadastro de fornecedor e condição de pagamento. Prepare as duas versões da conversa.</p>

<h2>6. Use feiras e associações</h2>
<p>Feiras do setor reúnem compradores e concorrentes no mesmo lugar. Antes de ir, levante a lista de expositores e marque quem você quer encontrar. Associações comerciais e industriais, núcleos setoriais e rodadas de negócios regionais também abrem portas, principalmente em cidades médias do interior, onde todo mundo se conhece.</p>

<h2>7. Organize tudo num lugar só</h2>
<p>Com várias representadas, dezenas de cidades e muitos orçamentos abertos, o caderno não dá conta. Um CRM simples com <a href="/blog/pipeline-de-vendas-como-montar">pipeline em Kanban</a> mostra em que etapa está cada empresa e qual é a próxima ação. Anote também qual representada interessa a cada cliente, para não perder a venda cruzada.</p>

<h2>Rotina semanal sugerida</h2>
<ul>
<li><strong>Segunda:</strong> planejamento da semana, ligações e mensagens para agendar visitas.</li>
<li><strong>Terça a quinta:</strong> rota de visitas por cidade, com encaixes de prospects próximos.</li>
<li><strong>Sexta:</strong> pedidos, follow-up de orçamentos, atualização do CRM e lista da semana seguinte.</li>
</ul>
<p>Ajuste ao tamanho do seu território. Quem cobre uma área grande pode alternar semanas de rota com semanas de prospecção a distância.</p>

<h2>Onde a tecnologia ajuda</h2>
<p>A parte mais trabalhosa para o representante é descobrir quais empresas existem em cada cidade e conseguir o contato certo. O TurboVenda encontra empresas numa base de 6.739.551 CNPJs ativos da Receita, coleta telefone, e-mail, site e decisor de fontes públicas, e a IA (Claude) escreve a mensagem de WhatsApp e de e-mail. Tudo fica num CRM Kanban, de Novo a Convertido.</p>

<p><strong>Mapeie o seu território:</strong> a <a href="/ferramentas/lista-de-empresas">ferramenta gratuita de lista de empresas</a> mostra quantas empresas de cada segmento existem nas cidades da sua região, sem login. Para ter os contatos e montar a rota, é só <a href="/cadastro?utm_source=blog&utm_medium=organic&utm_campaign=como-conseguir-clientes-representante-comercial">criar conta grátis com 50 leads</a>.</p>
"""
    },
    {
        'slug': 'como-vender-para-industrias',
        'titulo': 'Como Vender para Indústrias: Quem Decide, Como Abordar e o Que Evitar',
        'desc': 'Como vender para indústrias: quem decide a compra, como funciona o cadastro de fornecedor, como abordar o comprador e os erros que travam a venda.',
        'keywords': 'como vender para indústrias, vender para indústria, vendas industriais, prospecção de indústrias, homologação de fornecedor',
        'data': '2026-10-17',
        'tempo': '7 min',
        'conteudo': """
<p>Vender para a indústria tem regras próprias. A compra raramente é por impulso, quase sempre passa por mais de uma pessoa e, em muitos casos, exige que o fornecedor seja aprovado antes do primeiro pedido. Em compensação, uma indústria que vira cliente tende a comprar de forma recorrente. Este guia é para quem vende produto ou serviço para fábricas, em especial pequenas e médias indústrias como as que movem a economia do Sul.</p>

<h2>Como a indústria compra</h2>
<p>Separe o que você vende em um destes três tipos de compra, porque cada um segue um caminho diferente:</p>
<ul>
<li><strong>Matéria-prima e insumos de produção</strong> (aço, resina, embalagem, tecido): compra recorrente, negociada pelo setor de compras, com especificação definida pela engenharia ou pela qualidade. Trocar de fornecedor envolve teste e o risco de parar a linha.</li>
<li><strong>Manutenção, reparo e operação</strong> (ferramentas, peças, EPI, lubrificantes, serviços de manutenção): compras menores e frequentes. Quem pede é a manutenção ou a produção; quem fecha é compras.</li>
<li><strong>Investimento</strong> (máquina, sistema, reforma, automação): compra rara e cara, com o dono ou a diretoria envolvidos, orçamentos comparados e prazo de decisão longo.</li>
</ul>

<h2>Quem decide</h2>
<p>Numa indústria pequena, o dono participa de quase tudo. Conforme a empresa cresce, a decisão se divide. Uma referência prática:</p>
<table>
<thead><tr><th>O que você vende</th><th>Quem sente a dor</th><th>Quem negocia ou assina</th></tr></thead>
<tbody>
<tr><td>Insumo ou matéria-prima</td><td>Produção, qualidade, PCP</td><td>Compras; o dono, em empresa pequena</td></tr>
<tr><td>Ferramentas, peças, EPI</td><td>Manutenção, produção, segurança do trabalho</td><td>Compras</td></tr>
<tr><td>Segurança e adequação (NR-12, PPCI, laudos)</td><td>Segurança do trabalho, RH, gerente industrial</td><td>Dono ou diretor</td></tr>
<tr><td>Software, automação, TI</td><td>Gerente industrial, TI, financeiro</td><td>Dono ou diretoria</td></tr>
<tr><td>Frete e logística</td><td>Expedição, logística</td><td>Compras ou financeiro</td></tr>
</tbody>
</table>
<p>O caminho mais produtivo costuma ser entrar por quem sente a dor e, com a ajuda dessa pessoa, chegar a quem assina. Para descobrir os nomes, o quadro de sócios da Receita e o LinkedIn ajudam; o passo a passo está em <a href="/blog/como-encontrar-o-decisor-da-empresa">como encontrar o decisor da empresa</a>.</p>

<h2>Cadastro e homologação de fornecedor</h2>
<p>Muitas indústrias só compram de fornecedores cadastrados. O processo pode pedir documentos da empresa, certidões negativas, ficha técnica, amostra, teste em linha e, em alguns setores, certificações. Pergunte logo no primeiro contato: "Como funciona o cadastro de fornecedor de vocês?" A pergunta mostra que você conhece o processo e evita surpresa no meio da negociação.</p>

<h2>Como encontrar indústrias para prospectar</h2>
<p>Na classificação CNAE, a indústria de transformação é a seção C, que vai da divisão 10 (fabricação de produtos alimentícios) à 33 (manutenção, reparação e instalação de máquinas e equipamentos). Escolha as divisões e subclasses que compram o que você vende e filtre pelas cidades que atende. O Sul tem polos bem conhecidos: metalmecânico na Serra Gaúcha, têxtil e de confecção no Vale do Itajaí, agroindústria no oeste de SC e do PR, móveis em Bento Gonçalves e São Bento do Sul. Comece por páginas como <a href="/empresas/usinagem">usinagens</a> e <a href="/empresas/maquinas-industriais">fabricantes de máquinas industriais</a>, e veja como escolher os códigos em <a href="/blog/o-que-e-cnae-prospeccao">o que é CNAE</a>.</p>

<h2>Como abordar</h2>
<ol>
<li><strong>Mostre que entende o processo.</strong> "Trabalhamos com usinagens que fazem peça seriada para o setor automotivo" diz muito mais que "somos líderes em soluções".</li>
<li><strong>Fale de risco, não só de preço.</strong> Para a indústria, parar a linha custa caro. Prazo de entrega, estoque, assistência técnica e qualidade constante pesam tanto quanto o preço unitário.</li>
<li><strong>Ofereça um teste pequeno.</strong> Amostra, lote piloto ou serviço em uma máquina só. Isso reduz o risco de quem compra e facilita o primeiro sim.</li>
<li><strong>Peça uma visita técnica.</strong> Ver a fábrica funcionando revela problemas que nenhum e-mail mostra, e cria confiança.</li>
<li><strong>Tenha referências do mesmo setor.</strong> Um cliente atual que aceita atender um telefonema vale mais que qualquer apresentação.</li>
</ol>

<h2>Atenção ao calendário da fábrica</h2>
<p>Indústrias têm momentos ruins para conversar: fechamento de mês, picos de produção, auditorias. E momentos bons: o planejamento do orçamento do ano seguinte e as paradas programadas, quando a manutenção acontece. Muitas fábricas também dão férias coletivas no fim do ano, e propostas de investimento enviadas nessa época tendem a esperar a volta. Pergunte ao seu contato como funciona o calendário da empresa e anote no CRM.</p>

<h2>O que evitar</h2>
<ul>
<li>Mandar tabela de preço sem entender a aplicação.</li>
<li>Passar por cima de compras indo direto ao dono numa indústria que tem processo formal. Você pode ganhar a reunião e perder o cadastro.</li>
<li>Prometer um prazo de entrega que não consegue cumprir. Na indústria, um atraso pode custar o cliente.</li>
<li>Sumir depois do orçamento. O ciclo é longo, e um <a href="/blog/follow-up-de-vendas">follow-up</a> organizado mantém você na lista de fornecedores considerados.</li>
</ul>

<h2>Uma lista de indústrias com contato</h2>
<p>Encontrar as indústrias certas e o contato de quem decide é a parte que mais toma tempo. O TurboVenda busca empresas numa base de 6.739.551 CNPJs ativos da Receita, coleta telefone, e-mail, site e decisor de fontes públicas, e a IA (Claude) escreve a abordagem de e-mail e WhatsApp.</p>

<p><strong>Prepare a primeira abordagem:</strong> o <a href="/ferramentas/gerador-de-mensagem-de-prospeccao">gerador de mensagem de prospecção</a> escreve com IA um primeiro contato para o tipo de indústria que você quer atingir. Para ter a lista de indústrias com telefone, e-mail, site e decisor, é só <a href="/cadastro?utm_source=blog&utm_medium=organic&utm_campaign=como-vender-para-industrias">criar conta grátis com 50 leads</a>.</p>
"""
    },
    {
        'slug': 'follow-up-de-vendas',
        'titulo': 'Follow-up de Vendas: Quantas Vezes Insistir e Qual Cadência Usar',
        'desc': 'Quantas vezes fazer follow-up em vendas B2B, qual intervalo usar entre os contatos, o que escrever em cada tentativa e a hora certa de parar de insistir.',
        'keywords': 'follow-up de vendas, quantas vezes fazer follow-up, cadência de vendas, follow-up b2b, como fazer follow-up',
        'data': '2026-10-17',
        'tempo': '6 min',
        'conteudo': """
<p>Você mandou a mensagem, ligou, enviou a proposta. E nada. A dúvida que vem em seguida é sempre a mesma: insisto ou desisto? No B2B, silêncio raramente quer dizer "não". Quer dizer que a pessoa está ocupada, que o assunto não é prioridade nesta semana ou que a sua mensagem se perdeu entre muitas outras. O follow-up existe para isso. A questão é fazer do jeito certo: com intervalo, com algo novo a cada contato e com um ponto final claro.</p>

<h2>Quantas vezes fazer follow-up?</h2>
<p>Não existe um número que sirva para todo mundo. Uma referência prática para prospecção fria B2B é uma sequência de <strong>5 a 7 tentativas ao longo de 3 a 4 semanas</strong>, alternando canais, terminando com uma mensagem que avisa que você vai parar. Depois disso, o lead descansa por alguns meses antes de uma nova abordagem, com outro assunto.</p>
<p>Com menos tentativas, você desiste de gente que só não viu a sua mensagem. Com muito mais, no mesmo período, você vira incômodo. Use a referência como ponto de partida e ajuste conforme as respostas da sua lista.</p>

<h2>Cadência sugerida para o primeiro contato</h2>
<table>
<thead><tr><th>Dia</th><th>Canal</th><th>O que fazer</th></tr></thead>
<tbody>
<tr><td>1</td><td>Telefone ou WhatsApp</td><td>Primeiro contato: quem você é, por que aquela empresa, uma pergunta</td></tr>
<tr><td>2</td><td>E-mail</td><td>Versão um pouco mais completa, com um exemplo de como você ajuda empresas parecidas</td></tr>
<tr><td>5</td><td>Telefone</td><td>Ligação curta: "mandei um e-mail na terça, consegue falar dois minutos?"</td></tr>
<tr><td>9</td><td>E-mail</td><td>Algo útil sem pedir nada em troca: um checklist, uma dica do setor, uma mudança de norma</td></tr>
<tr><td>14</td><td>WhatsApp</td><td>Pergunta direta: "faz sentido conversar ou não é prioridade agora?"</td></tr>
<tr><td>21</td><td>Telefone</td><td>Última tentativa de conversa</td></tr>
<tr><td>25</td><td>E-mail ou WhatsApp</td><td>Mensagem de encerramento, deixando a porta aberta</td></tr>
</tbody>
</table>
<p>Adapte ao seu ciclo. Quem vende algo simples e de valor baixo pode encurtar os intervalos; quem vende projeto de investimento para indústria pode espaçar mais.</p>

<h2>Follow-up depois da proposta</h2>
<p>Aqui o lead já demonstrou interesse, então a cadência é outra:</p>
<ul>
<li><strong>No dia seguinte:</strong> confirme que a proposta chegou e pergunte quem mais vai avaliar.</li>
<li><strong>De 3 a 5 dias depois:</strong> pergunte se ficou dúvida sobre prazo, condição ou escopo.</li>
<li><strong>Uma semana depois:</strong> traga algo novo, como uma alternativa de condição, um caso parecido ou uma data de entrega.</li>
<li><strong>Depois disso:</strong> peça uma definição clara, mesmo que seja "agora não".</li>
</ul>
<p>O melhor follow-up de proposta é o que foi combinado antes: termine toda reunião com a próxima data marcada ("posso te ligar na quinta às 10h para ouvir o retorno?").</p>

<h2>O que escrever em cada tentativa</h2>
<ul>
<li><strong>Traga algo novo toda vez:</strong> uma informação, uma pergunta, um exemplo. "Só passando para saber se viu meu e-mail" não ajuda ninguém.</li>
<li><strong>Retome o contexto em uma linha.</strong> A pessoa provavelmente não lembra quem você é.</li>
<li><strong>Facilite a resposta</strong> com uma pergunta de sim ou não, ou duas opções de horário.</li>
<li><strong>Mude o ângulo.</strong> Se falar de economia não funcionou, fale de prazo, de risco ou de uma exigência legal do setor.</li>
</ul>
<p>Há modelos prontos em <a href="/blog/mensagem-de-prospeccao-whatsapp">mensagens de prospecção para WhatsApp</a> e em <a href="/blog/email-marketing-b2b-templates">templates de e-mail B2B</a>.</p>

<h2>Exemplo de sequência em que cada toque traz algo novo</h2>
<p>Imagine uma consultoria de segurança do trabalho de Chapecó tentando falar com o dono de uma transportadora da região:</p>
<ul>
<li><strong>Toque 1 (WhatsApp):</strong> apresentação em duas linhas e a pergunta "hoje quem cuida da segurança do trabalho e dos treinamentos da equipe de vocês?"</li>
<li><strong>Toque 2 (e-mail):</strong> como a consultoria organiza o calendário de treinamentos e exames de uma empresa com frota, sem falar de preço.</li>
<li><strong>Toque 3 (ligação):</strong> "liguei para saber se faz sentido uma conversa de 15 minutos sobre aquele e-mail".</li>
<li><strong>Toque 4 (e-mail):</strong> um checklist simples dos documentos de segurança do trabalho que a empresa deve manter em dia.</li>
<li><strong>Toque 5 (WhatsApp):</strong> encerramento educado, deixando o contato para quando fizer sentido.</li>
</ul>
<p>Repare que nenhum toque repete o anterior. Cada um dá à pessoa um motivo diferente para responder e mostra um pouco mais do que você sabe fazer.</p>

<h2>Quando parar</h2>
<p>Pare imediatamente quando a pessoa pedir. "Não tenho interesse" e "não me mande mais mensagens" encerram a sequência: registre o pedido e não volte a abordar. Além de ser o mínimo de respeito, oferecer e respeitar o opt-out é parte do que mantém a prospecção B2B compatível com a LGPD. O legítimo interesse, base em que esse tipo de contato costuma se apoiar, não cobre insistir depois de um pedido para parar.</p>
<p>Também é hora de pausar quando a sequência terminou sem resposta. Mande a mensagem de encerramento e marque o lead para uma nova tentativa daqui a alguns meses, com outro assunto.</p>

<h2>Quando insistir mais</h2>
<p>Alguns sinais pedem paciência, não desistência: "me chama em março", "estamos no meio da safra", "quem decide está de férias". Nesses casos, registre a data e volte exatamente quando combinou. Um retorno pontual, no dia prometido, mostra organização e costuma ser bem recebido.</p>

<h2>Sem registro, não existe follow-up</h2>
<p>Nenhuma cadência sobrevive só na memória. Cada lead precisa de etapa e de próxima ação com data. Num <a href="/blog/pipeline-de-vendas-como-montar">pipeline de vendas</a> em Kanban, como o do TurboVenda (Novo, Contactado, Respondeu, Qualificado, Demo, Convertido), fica fácil ver quem está esperando retorno e quem pode avançar. A IA do TurboVenda também escreve mensagens de e-mail e WhatsApp, o que ajuda a variar o texto entre uma tentativa e outra.</p>

<p><strong>Comece a sequência com o pé direito:</strong> o <a href="/ferramentas/gerador-de-mensagem-de-prospeccao">gerador de mensagem de prospecção</a> escreve com IA a mensagem de primeiro contato por WhatsApp ou e-mail, de graça. Para organizar os follow-ups num CRM com leads novos, é só <a href="/cadastro?utm_source=blog&utm_medium=organic&utm_campaign=follow-up-de-vendas">criar conta grátis com 50 leads</a>.</p>
"""
    },
    {
        'slug': 'o-que-e-cnae-prospeccao',
        'titulo': 'O Que é CNAE e Como Usar para Segmentar a Prospecção',
        'desc': 'Entenda o que é CNAE, como ler o código de atividade de uma empresa e como usar o CNAE principal e os secundários para segmentar a prospecção B2B.',
        'keywords': 'o que é cnae, cnae prospecção, código cnae, cnae principal e secundário, segmentação por cnae',
        'data': '2026-10-17',
        'tempo': '6 min',
        'conteudo': """
<p>Se você vende para empresas e quer uma lista de clientes potenciais, mais cedo ou mais tarde vai esbarrar no CNAE. É ele que permite dizer "quero todas as usinagens de Caxias do Sul" em vez de "quero metalúrgicas, acho". Este guia explica o que é o CNAE, como ler o código e como usá-lo para segmentar a prospecção sem cair nas armadilhas mais comuns.</p>

<h2>O que é CNAE</h2>
<p>CNAE é a <strong>Classificação Nacional de Atividades Econômicas</strong>, a tabela oficial usada no Brasil para dizer o que cada empresa faz. É mantida pelo IBGE, por meio da Comissão Nacional de Classificação (CONCLA), e usada pela Receita Federal no cadastro de CNPJ, pelas prefeituras e por outros órgãos públicos.</p>
<p>Toda empresa tem um <strong>CNAE principal</strong>, que deveria corresponder à sua atividade principal, e pode ter vários <strong>CNAEs secundários</strong>, para as demais atividades que exerce.</p>

<h2>Como ler o código</h2>
<p>O CNAE que aparece no CNPJ tem 7 dígitos e é organizado em níveis. Veja o exemplo de uma usinagem:</p>
<table>
<thead><tr><th>Nível</th><th>Código</th><th>Descrição</th></tr></thead>
<tbody>
<tr><td>Seção</td><td>C</td><td>Indústrias de transformação</td></tr>
<tr><td>Divisão</td><td>25</td><td>Fabricação de produtos de metal, exceto máquinas e equipamentos</td></tr>
<tr><td>Grupo</td><td>25.3</td><td>Forjaria, estamparia, metalurgia do pó e serviços de tratamento de metais</td></tr>
<tr><td>Classe</td><td>25.39-0</td><td>Serviços de usinagem, solda, tratamento e revestimento em metais</td></tr>
<tr><td>Subclasse</td><td>2539-0/01</td><td>Serviços de usinagem, tornearia e solda</td></tr>
</tbody>
</table>
<p>Isso permite segmentar com diferentes graus de detalhe. Filtrar pela divisão 25 traz todo tipo de fabricante de produtos de metal; filtrar pela subclasse 2539-0/01 traz apenas usinagem, tornearia e solda. As seções vão de A (agricultura e pecuária) a U (organismos internacionais).</p>

<h2>Por que usar CNAE na prospecção</h2>
<ul>
<li><strong>É objetivo.</strong> Toda empresa tem um CNAE, e o mesmo código vale no país inteiro.</li>
<li><strong>Combina com outros filtros.</strong> CNAE, cidade e porte formam a base de praticamente qualquer lista B2B.</li>
<li><strong>Permite personalizar a mensagem.</strong> Se você sabe que a empresa é uma construtora, fala de obra; se é uma clínica odontológica, fala de consultório.</li>
<li><strong>Mostra o tamanho do mercado.</strong> Saber quantas empresas de um CNAE existem na sua região indica se vale montar uma oferta específica para aquele nicho.</li>
</ul>

<h2>Como descobrir os CNAEs certos para você</h2>
<ol>
<li><strong>Comece pelos seus clientes.</strong> Consulte o CNPJ dos seus 10 a 20 melhores clientes. O comprovante de inscrição mostra o CNAE principal e os secundários.</li>
<li><strong>Agrupe os códigos que se repetem.</strong> Eles formam o núcleo da sua segmentação.</li>
<li><strong>Procure vizinhos.</strong> Pesquise por palavra-chave na tabela CNAE no site da CONCLA, do IBGE. Quem atende usinagens provavelmente também atende serralherias e fabricantes de estruturas metálicas.</li>
<li><strong>Valide com uma amostra.</strong> Abra o site de algumas empresas de cada código e confira se elas fazem mesmo o que você imagina.</li>
</ol>

<h2>Exemplos: o que você vende e quais CNAEs mirar</h2>
<table>
<thead><tr><th>Você vende</th><th>CNAEs para começar</th></tr></thead>
<tbody>
<tr><td>Ferramentas de corte e manutenção industrial</td><td>2539-0/01 usinagem, tornearia e solda; 2511-0/00 estruturas metálicas; 2869-1/00 máquinas para uso industrial específico</td></tr>
<tr><td>Software de gestão de obras</td><td>4120-4/00 construção de edifícios; 4321-5/00 instalação e manutenção elétrica</td></tr>
<tr><td>Contabilidade para empresas de tecnologia</td><td>6201-5/01 software sob encomenda; 6202-3/00 software customizável</td></tr>
<tr><td>Embalagens, etiquetas e tags</td><td>4639-7/01 atacado de produtos alimentícios em geral; 1412-6/01 confecção de vestuário</td></tr>
<tr><td>Rastreamento e gestão de frota</td><td>4930-2/02 transporte rodoviário de carga intermunicipal, interestadual e internacional</td></tr>
<tr><td>Material e equipamentos odontológicos</td><td>8630-5/04 atividade odontológica</td></tr>
</tbody>
</table>

<h2>Principal ou secundário: qual filtrar?</h2>
<p>Filtrar só pelo CNAE principal gera uma lista menor e mais precisa: empresas que declaram aquela atividade como a mais importante. Incluir os secundários aumenta a lista, mas traz também empresas para as quais a atividade é marginal ou só está no cadastro por precaução. Uma regra prática:</p>
<ul>
<li><strong>Use só o principal</strong> quando o seu produto depende de a empresa viver daquela atividade, como insumos para quem usina peças todos os dias.</li>
<li><strong>Inclua os secundários</strong> quando o segmento é pequeno na sua região ou quando as empresas costumam ter várias frentes, como construtoras que também fazem instalações.</li>
<li><strong>Nos dois casos,</strong> marque na lista se o código veio do principal ou de um secundário e aborde primeiro as empresas do principal.</li>
</ul>

<h2>As armadilhas do CNAE</h2>
<ul>
<li><strong>CNAE desatualizado.</strong> O código é escolhido na abertura, muitas vezes pelo contador, e nem sempre é atualizado quando a empresa muda de foco.</li>
<li><strong>Atividade real no secundário.</strong> Uma empresa pode ter "comércio" como principal e fabricar no secundário, ou o contrário. Se a ferramenta permitir, inclua os secundários.</li>
<li><strong>Segmentos sem código próprio.</strong> Alguns mercados não têm CNAE específico. Uma integradora de energia solar, por exemplo, pode estar cadastrada como instalação elétrica. Nesses casos, combine o CNAE com busca por palavra-chave no nome ou no site.</li>
<li><strong>Códigos genéricos.</strong> Subclasses com descrições como "não especificados anteriormente" ou "em geral" juntam negócios muito diferentes. Valide antes de abordar.</li>
</ul>

<h2>CNAE e cidade: o começo de qualquer lista</h2>
<p>Com os CNAEs definidos, o passo seguinte é cruzar com as cidades que você atende. Veja quantas empresas de cada segmento existem por cidade em <a href="/empresas">empresas por segmento e cidade</a>, por exemplo <a href="/empresas/usinagem">usinagens</a> ou <a href="/empresas/clinicas-odontologicas">clínicas odontológicas</a>. O passo a passo para transformar isso em lista está em <a href="/blog/lista-de-empresas-por-cidade">lista de empresas por cidade e por CNAE</a>.</p>
<p>No TurboVenda, você descreve o que vende e a IA (Claude) gera os termos de busca; o robô procura empresas numa base de 6.739.551 CNPJs ativos da Receita e coleta telefone, e-mail, site e decisor de fontes públicas.</p>

<p><strong>Veja o tamanho do seu nicho:</strong> a <a href="/ferramentas/lista-de-empresas">ferramenta gratuita de lista de empresas</a> mostra quantas empresas existem em qualquer segmento e cidade, com o perfil de porte, sem login. Para receber essas empresas com contato e decisor, é só <a href="/cadastro?utm_source=blog&utm_medium=organic&utm_campaign=o-que-e-cnae-prospeccao">criar conta grátis com 50 leads</a>.</p>
"""
    },
    {
        'slug': 'como-encontrar-o-decisor-da-empresa',
        'titulo': 'Como Encontrar o Decisor da Empresa (Inclusive pelos Sócios na Receita)',
        'desc': 'Como descobrir quem decide a compra numa empresa: quadro de sócios (QSA) da Receita, site, LinkedIn e as perguntas certas para chegar ao decisor no B2B.',
        'keywords': 'como encontrar o decisor da empresa, decisor de compra, quadro de sócios qsa, sócios da empresa receita, prospecção b2b decisor',
        'data': '2026-10-17',
        'tempo': '7 min',
        'conteudo': """
<p>Uma boa abordagem feita para a pessoa errada não vende. No B2B, muito tempo de prospecção se perde exatamente aí: falar com a recepção, com o estagiário ou com alguém que gosta da ideia mas não tem poder para comprar. Este guia mostra onde encontrar o nome do decisor, como usar o quadro de sócios da Receita Federal e como confirmar que você está falando com a pessoa certa.</p>

<h2>Quem é o decisor, afinal?</h2>
<p>Depende do tamanho da empresa e do que você vende.</p>
<ul>
<li><strong>Empresa pequena:</strong> na maioria das vezes, o dono ou um dos sócios decide tudo que envolve dinheiro.</li>
<li><strong>Empresa média:</strong> um gestor de área (compras, manutenção, financeiro, comercial) avalia e recomenda; o dono ou diretor aprova.</li>
<li><strong>Empresa maior:</strong> várias pessoas participam: quem usa, quem avalia tecnicamente, quem negocia e quem assina.</li>
</ul>
<p>Por isso, mais útil do que perguntar "quem é o decisor?" é mapear os papéis: quem sente a dor, quem influencia, quem compra e quem assina.</p>

<h2>Fonte 1: o quadro de sócios (QSA) da Receita</h2>
<p>Todo CNPJ tem um <strong>Quadro de Sócios e Administradores (QSA)</strong>, que faz parte dos dados abertos da Receita Federal. Para cada sócio aparecem o nome, a qualificação e a data de entrada na sociedade. O CPF aparece parcialmente mascarado.</p>
<p>A qualificação é o campo mais útil. Termos como <strong>sócio-administrador</strong> e <strong>administrador</strong> indicam quem responde pela gestão. Numa Ltda pequena de Chapecó com dois sócios, sendo um deles sócio-administrador, é bem provável que ele decida ou pelo menos participe de qualquer compra relevante.</p>
<p>Cuidados ao usar o QSA:</p>
<ul>
<li><strong>Holding como sócia.</strong> Se o sócio é outra empresa, você precisa olhar o QSA dessa empresa para chegar às pessoas.</li>
<li><strong>Sócio investidor.</strong> Nem todo sócio participa do dia a dia. A qualificação e a data de entrada ajudam a separar.</li>
<li><strong>Empresas grandes.</strong> Em sociedades anônimas e empresas com diretoria profissional, os administradores listados podem estar longe da compra do seu produto.</li>
<li><strong>Dado desatualizado.</strong> Mudanças societárias podem levar tempo para aparecer. Confirme em outra fonte.</li>
</ul>
<p>Os demais campos da base estão explicados em <a href="/blog/base-de-dados-de-empresas-cnpj">base de dados de empresas CNPJ</a>.</p>

<h2>Fonte 2: o site da empresa</h2>
<p>Páginas como "Quem somos", "Nossa história" e "Equipe" costumam citar fundadores e gestores. Notícias publicadas no próprio site (inauguração, nova linha de produtos, certificação) também mencionam nomes e cargos.</p>

<h2>Fonte 3: LinkedIn</h2>
<p>Busque pelo nome da empresa e filtre as pessoas pelo cargo: "compras", "suprimentos", "manutenção", "gerente industrial", "diretor". Depois cruze com o QSA: se o nome do sócio-administrador aparece no LinkedIn como diretor da empresa, a informação se confirma. Conferir o nome nas duas fontes também evita abordar um homônimo.</p>

<h2>Fonte 4: perguntar para quem atende</h2>
<p>Muitas vezes, a forma mais rápida é perguntar. Ligue para o número da empresa e seja direto:</p>
<blockquote>Bom dia, aqui é o [Seu nome], da [Sua empresa]. Trabalho com [o que você faz] para [segmento]. Quem aí cuida de [compras de embalagem / manutenção das máquinas]? Qual a melhor forma de falar com essa pessoa?</blockquote>
<p>Se você já tem um nome do QSA, use: "Gostaria de falar com o [Nome do sócio], é sobre [assunto]." Pedir alguém pelo nome muda o tom da conversa com a recepção.</p>

<h2>Fonte 5: entidades e imprensa local</h2>
<p>As diretorias de associações comerciais e industriais, sindicatos patronais e núcleos setoriais são públicas e trazem nomes de empresários da região. Jornais e portais locais de cidades como Passo Fundo, Caxias do Sul ou Cascavel publicam matérias sobre ampliações de fábrica e novas empresas, citando os responsáveis.</p>

<h2>Como confirmar que é a pessoa certa</h2>
<p>Na primeira conversa, faça duas perguntas simples:</p>
<ul>
<li>"Além de você, quem mais participa desse tipo de decisão aqui?"</li>
<li>"Como vocês costumam avaliar um fornecedor novo?"</li>
</ul>
<p>As respostas mostram se você está com o decisor, com um influenciador ou com alguém que pode te levar até a pessoa certa. Os três são úteis; o erro é tratar um como se fosse o outro. Se você vende para fábricas, o mapa de quem decide cada tipo de compra está em <a href="/blog/como-vender-para-industrias">como vender para indústrias</a>.</p>

<h2>Cuidados com a LGPD</h2>
<p>O nome de um sócio é dado pessoal, mesmo vindo de uma base pública. A prospecção B2B costuma se apoiar no legítimo interesse quando o contato tem relação com a atividade profissional da pessoa. Na prática: use canais profissionais (telefone e e-mail da empresa, perfil profissional), explique por que está entrando em contato, ofereça uma forma simples de não receber mais mensagens e respeite o pedido. Isto é orientação geral, não parecer jurídico; em caso de dúvida, consulte um especialista.</p>

<h2>Sem fazer isso empresa por empresa</h2>
<p>Pesquisar o decisor de cada empresa à mão leva tempo. O TurboVenda coleta telefone, e-mail, site e decisor de fontes públicas para as empresas que encontra, e a IA (Claude) escreve a abordagem de e-mail e WhatsApp. Para ideias de texto, veja também os <a href="/blog/mensagem-de-prospeccao-whatsapp">modelos de mensagem de prospecção no WhatsApp</a>.</p>

<p><strong>Prepare a abordagem ao decisor:</strong> o <a href="/ferramentas/gerador-de-mensagem-de-prospeccao">gerador de mensagem de prospecção</a> escreve com IA um primeiro contato por WhatsApp ou e-mail. Para receber empresas já com decisor, telefone e e-mail, é só <a href="/cadastro?utm_source=blog&utm_medium=organic&utm_campaign=como-encontrar-o-decisor-da-empresa">criar conta grátis com 50 leads</a>.</p>
"""
    },
]
