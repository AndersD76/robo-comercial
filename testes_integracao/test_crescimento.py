# -*- coding: utf-8 -*-
"""Crescimento orgânico contra PostgreSQL real e base sintética: CNAE do IBGE
+ estatísticas, onda de publicação, sitemap, página do banco com portão,
lead de isca com sequência e descadastro, painel do admin."""
import json

import app as A
import cnae_paginas
import conteudo_motor as cm
import crescimento as cfg
import jobs_crescimento
import sequencias
from conftest import sql

IBGE = [{'id': '4930202', 'descricao': 'TRANSPORTE RODOVIÁRIO DE CARGA, EXCETO PRODUTOS PERIGOSOS E MUDANÇAS, INTERMUNICIPAL',
         'classe': {'id': '49302', 'descricao': 'TRANSPORTE RODOVIÁRIO DE CARGA',
                    'observacoes': ['Esta classe compreende\r\n- o transporte rodoviário de mercadorias em geral',
                                    'Esta classe não compreende\r\n- o transporte de mudanças (49.30-2)'],
                    'grupo': {'id': '493', 'descricao': 'TRANSPORTE RODOVIÁRIO DE CARGA',
                              'divisao': {'id': '49', 'descricao': 'TRANSPORTE TERRESTRE',
                                          'secao': {'id': 'H', 'descricao': 'TRANSPORTE, ARMAZENAGEM E CORREIO'}}}},
         'atividades': ['TRANSPORTE RODOVIÁRIO DE CARGAS EM GERAL, INTERMUNICIPAL']},
        {'id': '4930201', 'descricao': 'TRANSPORTE RODOVIÁRIO DE CARGA, EXCETO PRODUTOS PERIGOSOS E MUDANÇAS, MUNICIPAL',
         'classe': {'id': '49302', 'descricao': 'TRANSPORTE RODOVIÁRIO DE CARGA', 'observacoes': [],
                    'grupo': {'id': '493', 'descricao': 'TRANSPORTE RODOVIÁRIO DE CARGA',
                              'divisao': {'id': '49', 'descricao': 'TRANSPORTE TERRESTRE',
                                          'secao': {'id': 'H', 'descricao': 'TRANSPORTE, ARMAZENAGEM E CORREIO'}}}},
         'atividades': []}]
EST = {'total': 1200, 'com_email': 900, 'com_telefone': 1100, 'com_socio': 800,
       'por_uf': [{'uf': 'RS', 'n': 700}, {'uf': 'SC', 'n': 500}],
       'por_porte': [{'porte': '01', 'n': 1000}, {'porte': '05', 'n': 200}],
       'por_ano': [{'ano': 2025, 'n': 100}], 'cidades': [{'municipio': 'Caxias do Sul', 'uf': 'RS', 'n': 300}],
       'ufs': {'RS': {'porte': {'01': 600, '05': 100}, 'por_ano': [{'ano': 2025, 'n': 60}],
                      'cidades': [{'municipio': 'Caxias do Sul', 'n': 300}]},
               'SC': {'porte': {'01': 400}, 'por_ano': [], 'cidades': [{'municipio': 'Joinville', 'n': 200}]}}}


def _preparar_cnae():
    conn = A._conn()
    c = conn.cursor()
    cfg.criar_tabelas(c)
    cnae_paginas.importar_ibge(c, IBGE)
    c.execute("""INSERT INTO cnae_estatisticas (codigo, base_mes, dados) VALUES ('4930202', '2026-10', %s)
                 ON CONFLICT (codigo) DO UPDATE SET dados = EXCLUDED.dados""", (json.dumps(EST),))
    conn.commit()
    return conn, c


def test_cnae_vira_pagina_entra_na_onda_e_no_sitemap():
    conn, c = _preparar_cnae()
    try:
        assert cnae_paginas.buscar(c, 'transporte carga')[0]['codigo'] == '4930202'
        assert [x['codigo'] for x in cnae_paginas.buscar(c, '4930.2')] == ['4930201', '4930202']
        jobs_crescimento.paginas_cnae(c)
        conn.commit()
        urls = {r['url']: r['status'] for r in sql("SELECT url, status FROM conteudo_paginas WHERE tipo = 'programatica'")}
        assert urls.get('/cnae/4930202') == 'aprovada' and urls.get('/cnae/4930202/rs') == 'aprovada'
        assert '/cnae/4930202/sc' in urls                       # 500 empresas >= limiar de 300
        assert '/cnae/4930201' not in urls                      # sem estatística, sem célula
    finally:
        conn.close()
    cli = A.app.test_client()
    r = cli.get('/cnae/4930202')
    assert r.status_code == 200 and 'noindex' in r.get_data(as_text=True)   # aprovada, ainda fora da onda
    conn = A._conn()
    try:
        c = conn.cursor()
        publicado = cm.publicar_onda(c, limite_total=50)
        conn.commit()
    finally:
        conn.close()
    assert publicado.get('programatica', 0) >= 2
    html = cli.get('/cnae/4930202').get_data(as_text=True)
    assert 'content="index, follow"' in html and '1.200' in html and 'Caxias do Sul' in html
    assert 'o transporte de mudanças' in html                    # "não compreende" do IBGE
    assert 'Dataset' in html and 'FAQPage' in html
    html_uf = cli.get('/cnae/4930202/rs').get_data(as_text=True)
    assert '700' in html_uf and 'content="index, follow"' in html_uf
    assert cli.get('/cnae/4930201').status_code == 200          # sem estatística: abre, mas noindex
    assert 'noindex' in cli.get('/cnae/4930201').get_data(as_text=True)
    mapa = A._sitemaps_crescimento()
    assert any(u.endswith('sitemap-cnae-1.xml') for u in mapa)
    xml = cli.get('/sitemap-cnae-1.xml').get_data(as_text=True)
    assert 'https://www.turbovenda.com.br/cnae/4930202</loc>' in xml
    assert sql("SELECT 1 FROM anotacoes WHERE tipo = 'onda'")
    assert sql("SELECT 1 FROM conteudo_qualidade WHERE url = '/cnae/4930202' AND aprovado")


def test_pagina_do_banco_passa_no_portao_e_e_publicada_com_isca():
    conn = A._conn()
    try:
        c = conn.cursor()
        cfg.criar_tabelas(c)
        corpo = ('<h2>O que é</h2><p>' + 'ICP é o perfil da empresa que mais compra de você. ' * 40 + '</p>'
                 '<h2>Exemplo</h2><pre>Segmento: usinagem\nPorte: pequena\nRegião: RS</pre>'
                 '<h2>Como usar</h2><p>Use no <a href="/ferramentas/gerador-de-icp">gerador</a>, na '
                 '<a href="/empresas">lista</a> e no <a href="/glossario">glossário</a>.</p>')
        pg = {'url': '/glossario/icp-teste', 'tipo': 'glossario', 'cluster': 'decisor', 'consulta': 'o que é icp',
              'titulo': 'O que é ICP: definição e exemplo prático', 'h1': 'O que é ICP',
              'descricao': 'ICP é o perfil de cliente ideal da sua empresa. Veja a definição, um exemplo pronto e como usar na '
                           'prospecção B2B.',
              'resposta': 'ICP, ou perfil de cliente ideal, é a descrição da empresa que mais compra de você: segmento, '
                          'porte, região e cargo de quem decide. Ele orienta a lista de prospecção e a mensagem, para o time '
                          'falar só com quem tem chance real de comprar.',
              'corpo': corpo, 'faq': [], 'fontes': [], 'extra': {'valor_proprio': 'exemplo pronto', 'termo': 'ICP'},
              'isca': 'gerador-icp'}
        r = cm.avaliar(pg, links_entrada=3, iscas_validas={'gerador-icp'}, links_saida_auto=0)
        assert r['aprovado'], r['motivo']
        cm.salvar(c, pg['url'], dict({k: v for k, v in pg.items() if k != 'url'}, status='aprovada', origem='llm'))
        cm.registrar_avaliacao(c, pg['url'], r)
        cm.publicar_onda(c, limite_total=10)
        conn.commit()
    finally:
        conn.close()
    cli = A.app.test_client()
    html = cli.get('/glossario/icp-teste').get_data(as_text=True)
    assert 'content="index, follow"' in html and 'DefinedTerm' in html
    assert 'data-isca="gerador-icp"' in html and 'isca-barra' in html     # meio, fim e barra do celular
    assert 'Equipe TurboVenda' in html and '/politica-editorial' in html
    hub = cli.get('/glossario').get_data(as_text=True)
    assert '/glossario/icp-teste' in hub and 'content="index, follow"' in hub
    assert 'https://www.turbovenda.com.br/glossario/icp-teste</loc>' in cli.get('/sitemap-conteudo.xml').get_data(as_text=True)


def test_lead_da_isca_grava_origem_sequencia_e_descadastro(emails):
    cli = A.app.test_client()
    cli.set_cookie('tv_lt', json.dumps({'lp': '/glossario/cac', 'ref': 'www.google.com', 'us': 'google', 'um': 'organic', 'uc': ''}))
    r = cli.post('/api/isca/calculadora-cac/lead', json={
        'email': 'lead.sintetico@exemplo.com.br', 'opt_in': True, 'consulta': 'calculadora de cac',
        'params': {'marketing': '2000', 'vendas': '3000', 'novos': '5', 'ticket': '400'}},
        headers={'Referer': 'https://www.turbovenda.com.br/ferramentas/calculadora-de-cac?x=1'})
    assert r.status_code == 200
    lead = sql("SELECT * FROM leads_isca WHERE email = 'lead.sintetico@exemplo.com.br'")[0]
    assert lead['opt_in_marketing'] and lead['passo_sequencia'] == 1 and lead['proximo_email_em'] is not None
    assert lead['utm']['utm_source'] == 'google' and lead['last_touch']['lp'] == '/glossario/cac'
    assert lead['resultado']['dados']['cac'] == 1000.0
    from datetime import datetime, timedelta, timezone
    conn = A._conn()
    try:
        enviados = []
        n = sequencias.rodar(conn, lambda para, a, h: enviados.append((para, a, h)) or True, lambda i: f'https://x/{i}',
                             agora=datetime.now(timezone.utc) + timedelta(days=2))
    finally:
        conn.close()
    assert n == 1 and enviados[0][0] == 'lead.sintetico@exemplo.com.br' and 'https://x/' in enviados[0][2]
    assert sql("SELECT passo_sequencia FROM leads_isca WHERE id = %s", (lead['id'],))[0]['passo_sequencia'] == 2
    token = sequencias.token_lead(lead['id'], A.app.secret_key)
    assert 'não vai mais receber' in cli.get(f'/descadastrar/{token}').get_data(as_text=True)
    assert sql("SELECT descadastrado_em FROM leads_isca WHERE id = %s", (lead['id'],))[0]['descadastrado_em']


def test_painel_do_admin_abre_com_dados():
    cli = A.app.test_client()
    with cli.session_transaction() as s:
        s['admin_auth'] = True
    r = cli.get('/admin/crescimento')
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and 'Crescimento orgânico' in html and 'Conteúdo: publicado' in html
