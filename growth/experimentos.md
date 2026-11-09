# Experimentos (Fase 6 do Prompt 2)

**Infraestrutura (no ar desde 09/11/2026):**
- **Divisão estável por visitante:** a divisão é própria, feita em `app.py` (`EXPERIMENTOS`, `variante()`), pelo cookie `tv_vid`.
- **Exposição:** cada exibição grava o evento `experimento_exposto`. Só conta visita de pessoa: robô e pré-carregamento do Chrome ficam fora.
- **Clique:** registrado pelo `data-cta` com o sufixo da versão.
- **Cadastro:** o evento `signup_completed` guarda a versão de cada experimento.
- **Resultado:** aparece em `/admin/receita`.
- **Recusa de cookies:** quem recusou cookies vê sempre a versão "a" e não entra na conta.

**Regras:**
- Uma variável por teste.
- Métrica primária e métrica de proteção definidas antes de começar.
- A decisão sai com p < 0,05 (teste de duas proporções), ou quando o prazo máximo vence, o que vier primeiro. Se o prazo vencer sem diferença significativa, fica a versão "a", que é a mais simples.
- Amostra mínima calculada com α = 0,05 e poder de 80%, a partir da linha de base real.

| # | Hipótese | Métrica primária | Proteção | Linha de base | Amostra mínima por versão | Prazo máximo | ICE | Situação |
|---|---|---|---|---|---|---|---|---|
| 1 | Na página segmento × cidade, "Buscar telefone e e-mail destas empresas" (B) gera mais cliques que "Quero o contato dessas empresas" (A) | clique no botão do topo ÷ visitas expostas | cadastros ÷ visitas; 1º lead ÷ cadastros | 3,6% (46 cliques em 1.270 visitas do Google, 28 dias) | 614 para detectar +100%; 2.068 para +50% | 8 semanas | 7·6·10 = 420 | **rodando** (`pseo_cta`) |
| 2 | Cadastro sem os campos opcionais "site" e "região" converte mais quem clicou no botão | cadastros ÷ cliques em botão | 1º lead ÷ cadastros | 20,4% (30 cadastros em 147 cliques, 28 dias) | 286 para +50%; 1.066 para +25% | 8 semanas | 6·6·9 = 324 | pronto para rodar depois do 1 |
| 3 | A faixa de oferta a partir do 10º lead, e não só quando a cota de 50 acaba, leva mais gente a iniciar pagamento | `checkout_started` ÷ contas com 1º lead | cancelamentos e reembolsos | sem linha de base: `checkout_started` começou a ser gravado em 09/11 | calcular depois de 4 semanas de linha de base | 10 semanas | 8·5·8 = 320 | aguardando linha de base |
| 4 | Plano anual com desconto aumenta a receita por pagante sem reduzir a conversão | receita ÷ visitante que viu a oferta | conversão em pagamento | sem linha de base | idem | 12 semanas | 7·5·5 = 175 | **TODO-VALIDAR:** valor e desconto do anual (decisão do dono) |
| 5 | Nas páginas de empresas, uma isca ("receba por e-mail as 20 primeiras empresas com contato") captura quem não está pronto para criar conta, sem tirar cadastros | e-mails capturados ÷ visitas | cadastros ÷ visitas | sem linha de base | 614 por versão, se a captura for ≥ 3,6% | 8 semanas | 6·4·5 = 120 | depende da Fase 5 (sequência de nutrição) |

**Cálculo da amostra.** n = (z<sub>α/2</sub>·√(2p̄(1−p̄)) + z<sub>β</sub>·√(p₁(1−p₁) + p₂(1−p₂)))² ÷ (p₂ − p₁)², com z<sub>α/2</sub> = 1,96 e z<sub>β</sub> = 0,84.

**Ritmo.** No volume atual (~1.300 visitas do Google por mês nas páginas segmento × cidade), o teste 1 detecta só diferenças grandes (o dobro de cliques) em cerca de 1 mês; diferenças de +50% levam cerca de 3 meses. Por isso os testes rodam um de cada vez, em ordem de ICE.
