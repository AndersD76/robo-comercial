# -*- coding: utf-8 -*-
"""Crescimento orgânico: iscas, sequência de e-mails, motor de conteúdo e
portão de qualidade. Sem banco e sem rede."""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import conteudo_motor as cm  # noqa: E402
import crescimento as cfg  # noqa: E402
import iscas  # noqa: E402
import lgpd_textos  # noqa: E402
import sequencias as seq  # noqa: E402


# --- canais -----------------------------------------------------------------
def test_canal_inclui_respostas_de_ia_como_organico():
    assert cfg.canal_de('https://chatgpt.com/') == 'ia'
    assert cfg.canal_de('https://www.perplexity.ai/search') == 'ia'
    assert cfg.canal_de('https://gemini.google.com/app') == 'ia'
    assert cfg.canal_de('https://copilot.microsoft.com/') == 'ia'
    assert cfg.canal_de('https://claude.ai/chat/x') == 'ia'
    assert cfg.canal_de('', 'chatgpt.com') == 'ia'
    assert cfg.canal_de('https://www.google.com.br/') == 'busca'
    assert cfg.canal_de('https://www.bing.com/search?q=x') == 'busca'
    assert cfg.canal_de('https://www.linkedin.com/feed') == 'social'
    assert cfg.canal_de('https://outro-site.com.br/post') == 'referencia'
    assert cfg.canal_de('') == 'direto'
    assert cfg.canal_de('https://www.turbovenda.com.br/blog') == 'direto'


def test_taxonomia_objeto_acao_com_props_obrigatorias():
    for nome, ev in cfg.TAXONOMIA_EVENTOS.items():
        assert '_' in nome
    for nome in ('isca_vista', 'isca_iniciada', 'isca_concluida', 'lead_capturado', 'cta_produto_clicado'):
        assert set(cfg.PROPS_PAGINA) <= set(cfg.TAXONOMIA_EVENTOS[nome]['props'])
    assert cfg.TAXONOMIA_EVENTOS['payment_succeeded']['origem'] == 'servidor'   # compra nunca do navegador
    assert 'payment_succeeded' not in cfg.EVENTOS_NAVEGADOR_CRESCIMENTO


# --- iscas ------------------------------------------------------------------
def test_pelo_menos_dez_iscas_e_cada_cluster_aponta_para_uma_que_existe():
    assert len(iscas.ISCAS) >= 10
    for c, v in cfg.CLUSTERS.items():
        assert v['isca'] in iscas.ISCAS, c
    for k in iscas.NOVAS:
        i = iscas.ISCAS[k]
        assert len(i['titulo']) <= 60, k
        assert 70 <= len(i['descricao']) <= 155, k
        assert 30 <= len(i['resposta'].split()) <= 75, k


def test_diagnostico_da_nota_e_os_pontos_fracos():
    todos_sim = {k: 'sim' for k, *_ in iscas._DIAG}
    assert iscas.calcular('diagnostico-prospeccao', todos_sim)['dados']['nota'] == 100
    metade = dict(todos_sim, icp='nao', lista='as_vezes')
    r = iscas.calcular('diagnostico-prospeccao', metade)
    assert r['dados']['nota'] == 85 and 'gerador-de-icp' in r['tela']
    assert iscas.calcular('diagnostico-prospeccao', {'icp': 'sim'}) is None   # incompleto


def test_cac_ltv_payback():
    r = iscas.calcular('calculadora-cac', {'marketing': '3000', 'vendas': '7000', 'novos': '10', 'ticket': '500',
                                           'meses': '12', 'margem': '50'})
    assert r['dados'] == {'cac': 1000.0, 'ltv': 3000.0, 'razao': 3.0}
    assert 'R$ 1.000' in r['tela'] and '4.0 meses' in r['tela']
    assert iscas.calcular('calculadora-cac', {'novos': '0'}) is None


def test_roi_usa_o_preco_real_do_plano():
    r = iscas.calcular('calculadora-roi', {'horas': '10', 'custo_hora': '50', 'leads': '20', 'automatizavel': '50',
                                           'plano': 'starter'}, {'precos': {'starter': 97.0, 'pro': 297.0}})
    assert round(r['dados']['custo_mes']) == round(10 * 52 / 12 * 50)
    assert 'Starter' in r['tela'] and 'R$ 97' in r['tela']


def test_icp_mostra_a_contagem_da_base():
    ctx = {'segmentos': {'usinagem': {'codigo': '2539001', 'label': 'Usinagem'}}, 'ufs': {'RS': 'Rio Grande do Sul'},
           'contar': lambda codigo, uf, porte: 1234 if (codigo, uf) == ('2539001', 'RS') else 0}
    r = iscas.calcular('gerador-icp', {'segmento': 'usinagem', 'uf': 'rs', 'porte': 'todos', 'cargo': '<b>dono</b>'}, ctx)
    assert '1.234' in r['tela'] and '/empresas/usinagem/estado/rs' in r['tela']
    assert '<b>dono</b>' not in r['tela'] and '&lt;b&gt;' in r['tela']           # texto digitado escapado
    assert iscas.calcular('gerador-icp', {'segmento': 'nao-existe'}, ctx) is None


def test_cadencia_e_funil():
    r = iscas.calcular('cadencia-prospeccao', {'canal_email': '1', 'canal_whatsapp': '1', 'dias': '14'})
    assert r['dados']['toques'] == 5 and 'Dia 1' in r['tela']
    assert iscas.calcular('cadencia-prospeccao', {'dias': '14'}) is None
    f = iscas.calcular('calculadora-funil', {'leads': '1000', 'respostas': '100', 'reunioes': '40', 'propostas': '20',
                                             'vendas': '1', 'melhora': '50'})
    assert f['dados']['gargalo'] == 'vendas'
    assert iscas.calcular('calculadora-funil', {'leads': '10', 'respostas': '20'}) is None   # etapa maior que a anterior


def test_checklist_lgpd_cita_o_texto_oficial_certo():
    trechos = {k: iscas._trecho(a, i) for k, _, a, i, _ in iscas._LGPD}
    assert trechos['base_legal'].startswith('IX - quando necessário para atender aos interesses legítimos')
    assert trechos['minimo'].startswith('§ 1º Quando o tratamento for baseado no legítimo interesse')
    assert trechos['transparencia'].startswith('§ 2º O controlador deverá adotar medidas para garantir a transparência')
    assert trechos['publico'].startswith('§ 3º O tratamento de dados pessoais cujo acesso é público')
    assert trechos['descadastro'].startswith('§ 2º O titular pode opor-se')
    assert 'até 15 (quinze) dias' in trechos['prazo']
    r = iscas.calcular('checklist-lgpd', {'enviado': '1', 'base_legal': '1'})
    assert r['dados']['nota'] == 10 and 'não substitui orientação jurídica' in r['completo']
    assert lgpd_textos.FONTE['url'].startswith('https://www.planalto.gov.br/')


def test_consulta_cnae_e_planilha():
    ctx = {'buscar_cnae': lambda q, n: [{'codigo': '4930202', 'formatado': '4930-2/02', 'descricao': 'TRANSPORTE', 'empresas': 10}]}
    r = iscas.calcular('consulta-cnae', {'q': 'transporte'}, ctx)
    assert '/cnae/4930202' in r['tela'] and 'https://www.turbovenda.com.br/cnae/4930202' in r['completo']
    assert iscas.calcular('consulta-cnae', {'q': 'ab'}, ctx) is None
    csv = iscas.planilha_csv()
    assert csv.startswith('﻿Empresa;CNPJ;') and csv.count('\n') == 2


# --- sequência --------------------------------------------------------------
class _Cur:
    def __init__(self, linhas=None):
        self.feitos, self.linhas, self.rowcount = [], linhas or [], 1

    def execute(self, sql, params=None):
        self.feitos.append((' '.join(sql.split()), params))

    def fetchone(self):
        return {'id': 7, 'email': 'a@b.com.br'}

    def fetchall(self):
        return self.linhas


class _Conn:
    def __init__(self, cur):
        self.cur = cur

    def cursor(self):
        return self.cur

    def commit(self):
        pass


def test_token_de_descadastro_do_lead():
    t = seq.token_lead(42, 'segredo')
    assert seq.lead_do_token(t, 'segredo') == 42
    assert seq.lead_do_token(t, 'outro') is None
    assert seq.lead_do_token('l43.' + t.split('.')[1], 'segredo') is None


def test_sequencia_so_com_opt_in_e_curso_sem_opt_in():
    agora = dt.datetime(2026, 11, 26, 12, tzinfo=dt.timezone.utc)
    cur = _Cur()
    seq.registrar(cur, {'email': ' A@B.com.br ', 'isca': 'calculadora-cac', 'opt_in': False}, agora)
    assert cur.feitos[-1][1][0] == 'a@b.com.br' and cur.feitos[-1][1][12] is None      # sem marketing: nada agendado
    seq.registrar(cur, {'email': 'a@b.com.br', 'isca': 'calculadora-cac', 'opt_in': True}, agora)
    assert cur.feitos[-1][1][12] == agora + dt.timedelta(days=1)
    seq.registrar(cur, {'email': 'a@b.com.br', 'isca': 'mini-curso', 'opt_in': False}, agora)
    assert cur.feitos[-1][1][12] == agora + dt.timedelta(days=1)                         # o curso é o pedido


def test_rodar_manda_o_proximo_passo_e_termina_na_oferta():
    criado = dt.datetime(2026, 11, 1, tzinfo=dt.timezone.utc)
    lead = {'id': 9, 'email': 'x@y.com.br', 'nome': 'Ana Souza', 'cluster': 'metas', 'isca': 'calculadora-cac',
            'passo_sequencia': 4, 'criado_em': criado}
    cur = _Cur([lead])
    enviados = []
    n = seq.rodar(_Conn(cur), lambda para, assunto, html: enviados.append((para, assunto, html)) or True,
                  lambda i: f'https://x/descadastrar/{i}', agora=criado + dt.timedelta(days=9))
    assert n == 1 and enviados[0][1].startswith('Teste o TurboVenda por 14 dias')
    assert 'Olá, Ana!' in enviados[0][2] and 'https://x/descadastrar/9' in enviados[0][2]
    assert cur.feitos[-1][1] == (5, None, 9)                                              # fim da sequência


def test_email_do_resultado_tem_cta_absoluto_e_descadastro():
    r = iscas.calcular('calculadora-cac', {'marketing': '1000', 'vendas': '1000', 'novos': '2', 'ticket': '300'})
    assunto, html = seq.email_resultado('calculadora-cac', r, 'https://x/d/1')
    assert assunto.startswith('Seu resultado') and 'https://www.turbovenda.com.br/cadastro?' in html
    assert 'https://x/d/1' in html and 'href="/' not in html


# --- motor de conteúdo --------------------------------------------------------
def test_html_limpo_tira_script_atributos_e_links_perigosos():
    sujo = ('<h1>Título</h1><p onclick="x()">Oi <script>alert(1)</script><a href="javascript:alert(1)">mal</a> '
            '<a href="//evil.com">proto</a> <a href="/blog/x">bom</a> <a href="https://gov.br">fora</a></p>'
            '<img src=x onerror=alert(1)><table><tr><td>1</td></tr></table>')
    limpo = cm.html_limpo(sujo)
    assert '<script' not in limpo and 'alert' not in limpo.replace('mal', '') and 'onclick' not in limpo
    assert 'javascript:' not in limpo and '//evil.com' not in limpo and '<img' not in limpo
    assert '<a href="/blog/x">bom</a>' in limpo and 'rel="noopener"' in limpo
    assert limpo.startswith('<h2>Título</h2>') and '<td>1</td>' in limpo


def test_ancoras_e_divisao_para_a_isca_do_meio():
    html, sumario = cm.com_ancoras('<h2>Um</h2><p>a</p><h2>Dois</h2><p>b</p><h2>Um</h2><p>c</p><h2>Três</h2>')
    assert [s[0] for s in sumario] == ['um', 'dois', 'um-2', 'tres']
    a, b = cm.dividir_no_meio(html)
    assert a and b and a + b == html and b.startswith('<h2')


def test_numero_inventado_vai_para_revisao():
    permitidos = cm.numeros_de({'total': 123456, 'por_uf': [{'uf': 'RS', 'n': 4321}]})
    assert cm.numeros_suspeitos('Há 123.456 empresas e 4.321 no RS, em 2025, em 5 passos.', permitidos) == []
    assert cm.numeros_suspeitos('72% dos vendedores desistem', permitidos) == ['72%']
    assert cm.numeros_suspeitos('custa R$ 300 por mês', permitidos) == ['R$ 300']


def _pagina_boa(**mud):
    p = {'tipo': 'satelite', 'url': '/blog/como-prospectar-transportadoras', 'consulta': 'como prospectar transportadoras',
         'titulo': 'Como prospectar transportadoras: guia com dados',
         'descricao': 'Veja como prospectar transportadoras com lista da Receita, cadência e mensagem pronta. Com o total '
                      'de empresas ativas por estado.',
         'h1': 'Como prospectar transportadoras',
         'resposta': 'Para prospectar transportadoras, comece pela lista de empresas ativas do CNAE de transporte de carga '
                     'na sua região, fale com o sócio que decide e siga uma cadência de seis toques em dois canais, '
                     'com mensagem que cite a rota ou a frota da empresa.',
         'corpo': '<h2>Quantas existem</h2><table><tr><td>RS</td><td>4.321</td></tr></table>'
                  + '<p>' + ' '.join(['texto útil sobre prospecção de transportadoras'] * 160) + '</p>'
                  + '<p><a href="/cnae/4930202">CNAE</a> <a href="/empresas">empresas</a> <a href="/ferramentas/gerador-de-cadencia-de-prospeccao">cadência</a></p>',
         'faq': [{'pergunta': 'Qual CNAE?', 'resposta': 'O de transporte de carga.'},
                 {'pergunta': 'Quem decide?', 'resposta': 'O sócio.'}],
         'fontes': [], 'extra': {'valor_proprio': 'tabela com o total por UF da base da Receita'},
         'isca': 'cadencia-prospeccao'}
    p.update(mud)
    return p


def test_portao_aprova_pagina_completa():
    r = cm.avaliar(_pagina_boa(), links_entrada=3, numeros_permitidos=cm.numeros_de({'rs': 4321}),
                   iscas_validas=set(iscas.ISCAS))
    assert r['aprovado'], r['motivo']
    assert not r['revisao']


def test_portao_reprova_e_explica():
    r = cm.avaliar(_pagina_boa(titulo='Guia definitivo e completo de absolutamente tudo sobre vendas B2B'),
                   links_entrada=1, iscas_validas=set(iscas.ISCAS))
    assert not r['aprovado']
    for k in ('titulo', 'links_entrada', 'numeros_com_fonte'):
        assert k in r['motivo']
    assert r['revisao']   # número sem fonte depende do dono
    lei = cm.avaliar(_pagina_boa(corpo=_pagina_boa()['corpo'] + '<p>Conforme a Lei nº 13.709 e o art. 7º.</p>'),
                     links_entrada=3, numeros_permitidos=cm.numeros_de({'rs': 4321, 'lei': '13.709'}),
                     iscas_validas=set(iscas.ISCAS))
    assert not lei['checks']['norma_com_fonte_oficial'] and lei['revisao']


def test_similaridade_pega_pagina_quase_igual():
    base = _pagina_boa()
    ind = cm.Indice([{'url': '/blog/outra', 'tipo': 'satelite', 'cluster': 'setores', 'titulo': base['titulo'],
                      'texto': cm.texto_puro(base['corpo'])}])
    r = cm.avaliar(base, indice=ind, links_entrada=3, numeros_permitidos=cm.numeros_de({'rs': 4321}),
                   iscas_validas=set(iscas.ISCAS))
    assert not r['checks']['similaridade'] and r['similar'] == '/blog/outra'


def test_grafo_sem_orfa_com_tres_entradas():
    paginas = [{'url': f'/glossario/t{i}', 'tipo': 'glossario', 'cluster': 'gestao', 'titulo': f'termo {i}',
                'texto': ('vendas ' * (i + 1)) + ('funil ' * (10 - i))} for i in range(8)]
    paginas.append({'url': '/glossario/sozinha', 'tipo': 'glossario', 'cluster': 'lgpd', 'titulo': 'x', 'texto': 'y'})
    g = cm.Indice(paginas).grafo(por_pagina=2)
    ent = cm.entradas(g)
    for p in paginas[:8]:
        assert ent[p['url']] >= 3, p['url']
        assert p['url'] not in g[p['url']]
    assert g['/glossario/sozinha'] == []


def test_titulo_com_a_consulta_primeiro():
    assert cm.titulo_ok('O que é ICP: definição e exemplo', 'o que é icp')
    assert cm.titulo_ok('ICP: o que é, exemplo e como montar', 'o que é icp')
    assert not cm.titulo_ok('Guia de vendas para iniciantes e muito mais sobre ICP', 'o que é icp')
    assert not cm.titulo_ok('x' * 61, 'x')


def test_json_ld_valido_e_sem_fechar_script():
    import json
    p = _pagina_boa(publicado_em=dt.datetime(2026, 11, 26), atualizado_em=dt.datetime(2026, 11, 26))
    p['faq'][0]['resposta'] = 'Fim </script><script>alert(1)</script>'
    lds = cm.ld_pagina(p, migalhas=[('Início', '/'), ('Blog', '/blog')])
    assert all('</script' not in x for x in lds)
    tipos = [json.loads(x)['@type'] for x in lds]
    assert tipos == ['Article', 'BreadcrumbList', 'FAQPage']
    autor = json.loads(cm.ld_pagina(p, autor={'nome': 'Fulana', 'url': '/autor/fulana', 'cargo': 'Diretora'})[0])['author']
    assert autor['@type'] == 'Person' and autor['jobTitle'] == 'Diretora'


# --- robôs de IA verificados por IP ----------------------------------------
def test_robo_de_ia_so_verificado_dentro_da_faixa_oficial(monkeypatch):
    import time as _t
    import robos_ia
    redes = robos_ia.redes_de({'prefixes': [{'ipv4Prefix': '132.196.86.0/24'}, {'ipv6Prefix': '2a01:111::/32'}]})
    monkeypatch.setitem(robos_ia._cache, 'GPTBot', (_t.time() + 999, redes))
    assert robos_ia.verificado('GPTBot', '132.196.86.17') is True
    assert robos_ia.verificado('GPTBot', '8.8.8.8') is False           # user-agent falso, IP de fora
    assert robos_ia.verificado('GPTBot', 'lixo') is False
    assert robos_ia.verificado('ClaudeBot', '1.2.3.4') is None          # não publica faixas: outro método


def test_onda_redistribui_a_cota_que_sobra():
    class Cur:
        def __init__(self):
            self.feitos, self.rowcount, self._r = [], 0, None

        def execute(self, sql, params=None):
            s = ' '.join(sql.split())
            self.feitos.append((s, params))
            if s.startswith('SELECT tipo FROM conteudo_pausas'):
                self._r = []
            elif s.startswith('SELECT tipo, COUNT(*)'):
                self._r = [{'tipo': 'glossario', 'n': 10}, {'tipo': 'programatica', 'n': 5000}, {'tipo': 'modelo', 'n': 30}]
            elif s.startswith('INSERT INTO conteudo_ondas'):
                self._r = [{'id': len(self.feitos)}]
            elif s.startswith('UPDATE conteudo_paginas'):
                self.rowcount = params[-1]

        def fetchall(self):
            return self._r

        def fetchone(self):
            return self._r[0]

    r = cm.publicar_onda(Cur(), limite_total=400)
    assert r == {'glossario': 10, 'modelo': 30, 'programatica': 360}


def test_numero_de_exemplo_declarado_passa_e_estatistica_solta_nao():
    corpo = ('<p>Exemplo hipotético: com meta de R$ 60.000 e ticket de R$ 5.000, são 12 vendas.</p>'
             '<li>Imagine 1.000 leads por mês.</li><pre>Valor: R$ 300</pre>'
             '<p>No Brasil, 72% das empresas não prospectam.</p>')
    texto = cm.texto_puro(cm.sem_exemplos(corpo))
    assert cm.numeros_suspeitos(texto, set()) == ['72%']
    assert 'R$ 60.000' not in texto and '1.000' not in texto and 'R$ 300' not in texto
