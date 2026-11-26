# -*- coding: utf-8 -*-
"""Jobs e gerador do crescimento contra PostgreSQL real, com a API do Claude
simulada (nenhuma chamada sai daqui): sementes, lote, portão, onda,
distribuição, off-page, linha de base, mapa de buscas."""
import json
from types import SimpleNamespace

import app as A
import conteudo_motor as cm
import crescimento as cfg
import gerador_conteudo as gen
import jobs_crescimento as jobs
import mapa_buscas
import sementes_conteudo as sem
from conftest import sql


class _Lotes:
    def __init__(self, saida_de):
        self.pedidos, self.saida_de = {}, saida_de

    def create(self, requests):
        self.pedidos['lote_1'] = requests
        return SimpleNamespace(id='lote_1', processing_status='in_progress')

    def retrieve(self, lote_id):
        return SimpleNamespace(id=lote_id, processing_status='ended')

    def results(self, lote_id):
        for p in self.pedidos[lote_id]:
            entrada = json.loads(p['params']['messages'][0]['content'])
            texto = json.dumps(self.saida_de(entrada), ensure_ascii=False)
            msg = SimpleNamespace(content=[SimpleNamespace(type='text', text=texto)], stop_reason='end_turn',
                                  model='claude-opus-5-5',
                                  usage=SimpleNamespace(input_tokens=3000, output_tokens=5000, cache_read_input_tokens=0))
            yield SimpleNamespace(custom_id=p['custom_id'], result=SimpleNamespace(type='succeeded', message=msg))


def _saida_boa(entrada):
    consulta = entrada['CONSULTA']
    termo = consulta.replace('o que é ', '')
    links = [l['url'] for l in entrada['LINKS']][:4]
    secoes = [{'titulo': 'Definição', 'html': '<p>' + f'{termo} explicado com clareza para quem vende B2B. ' * 30 + '</p>'},
              {'titulo': 'Exemplo prático', 'html': '<pre>Empresa: exemplo\nSegmento: usinagem\nPróximo passo: ligar</pre>'},
              {'titulo': 'Onde usar', 'html': '<p>' + ' '.join(f'<a href="{u}">veja aqui</a>' for u in links)
               + ' <a href="https://externo.com">externo</a> <a href="/rota-que-nao-existe">quebrado</a></p>'}]
    return {'titulo': f'{consulta.capitalize()}: definição e exemplo'[:60],
            'descricao': f'Entenda {termo} com definição simples, um exemplo pronto e como aplicar na prospecção B2B da sua empresa.',
            'h1': consulta.capitalize(),
            'resposta': f'{termo.capitalize()} é um conceito de vendas B2B que ajuda o time a focar em quem compra. ' * 2
                        + 'Na prática, entra na lista de prospecção e na primeira mensagem.',
            'secoes': secoes, 'faq': [{'pergunta': f'Para que serve {termo}?', 'resposta': 'Para focar o esforço.'}],
            'valor_proprio': 'exemplo pronto em bloco', 'fontes_usadas': [], 'termo': termo}


def test_sementes_lote_portao_onda_e_custo(monkeypatch):
    conn = A._conn()
    try:
        c = conn.cursor()
        cfg.criar_tabelas(c)
        segs = list(A.CNAE_B2B)[:2]
        n = sem.semear(c, segs)
        conn.commit()
        assert n >= 300
        # só 3 alvos de glossário entram no lote do teste
        c.execute("""UPDATE conteudo_paginas SET extra = extra || '{"prioridade": 99}'::jsonb
                     WHERE url IN ('/glossario/icp', '/glossario/sdr', '/glossario/cac')""")
        conn.commit()
        lotes = _Lotes(_saida_boa)
        cliente = SimpleNamespace(messages=SimpleNamespace(batches=lotes))
        ctx = jobs._contexto_fn(A, c)
        lote_id, n = gen.enviar_lote(conn, cliente, ctx, limite=3)
        assert lote_id == 'lote_1' and n == 3
        p0 = lotes.pedidos['lote_1'][0]['params']
        assert p0['model'] == 'claude-opus-5-5' and p0['output_config']['format']['type'] == 'json_schema'
        assert sql("SELECT COUNT(*) AS n FROM conteudo_paginas WHERE status = 'gerando'")[0]['n'] == 3
        feitos = gen.processar_lotes(conn, cliente, ctx, jobs._avaliador(A))
        assert feitos == [('lote_1', 3, 0)]
    finally:
        conn.close()
    paginas = sql("SELECT url, status, corpo, custo_usd FROM conteudo_paginas WHERE url IN ('/glossario/icp', '/glossario/sdr', '/glossario/cac')")
    assert {p['status'] for p in paginas} <= {'aprovada', 'rascunho', 'revisao'}
    for p in paginas:
        assert 'externo.com' not in p['corpo'] and 'rota-que-nao-existe' not in p['corpo']   # link fora da lista vira texto
        assert float(p['custo_usd']) == round((3000 * 2.0 + 5000 * 10.0) / 1e6, 4)
    lote = sql("SELECT * FROM conteudo_lotes WHERE id = 'lote_1'")[0]
    assert lote['concluidos'] == 3 and float(lote['custo_usd']) > 0 and lote['processado_em']
    assert sql("SELECT COUNT(*) AS n FROM conteudo_qualidade WHERE url LIKE '/glossario/%%'")[0]['n'] >= 3


def test_passada_sem_ia_prepara_dados_distribui_e_mede(monkeypatch):
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    conn = A._conn()
    try:
        c = conn.cursor()
        cfg.criar_tabelas(c)
        cm.salvar(c, '/modelos/teste-distribuicao', {'tipo': 'modelo', 'cluster': 'email', 'consulta': 'modelo teste',
                                                     'titulo': 'Modelo teste', 'h1': 'Modelo de teste',
                                                     'resposta': 'Resposta curta.', 'corpo': '<h2>Um</h2><p>x</p><h2>Dois</h2>',
                                                     'status': 'publicada'})
        conn.commit()
    finally:
        conn.close()
    feito = A._crescimento_passada(forcar={'dados', 'distribuicao', 'linha_base'})
    assert 'dados' in feito and feito['dados']['sementes'] >= 0 and feito['dados']['offpage'] >= 100
    assert sql('SELECT COUNT(*) AS n FROM alvos_link')[0]['n'] >= 100
    assert sql("SELECT COUNT(*) AS n FROM pecas_offpage WHERE tipo = 'diretorio'")[0]['n'] >= 15
    canais = {r['canal'] for r in sql("SELECT canal FROM fila_distribuicao WHERE url = '/modelos/teste-distribuicao'")}
    assert canais == {'linkedin', 'video'}
    texto = sql("SELECT texto, link_utm FROM fila_distribuicao WHERE canal = 'linkedin' AND url = '/modelos/teste-distribuicao'")[0]
    assert 'utm_source=linkedin' in texto['link_utm'] and texto['link_utm'] in texto['texto']
    assert sql("SELECT COUNT(*) AS n FROM linha_base")[0]['n'] >= 3
    assert sql("SELECT COUNT(*) AS n FROM mapa_buscas")[0]['n'] >= 300      # sementes + combinações entram no mapa


def test_mapa_classifica_e_escolhe_satelites_sem_duplicar():
    assert mapa_buscas.classificar('o que é cnae')['tipo_pagina'] == 'glossario'
    assert mapa_buscas.classificar('econodata vs speedio')['intencao'] == 'comercial'
    assert mapa_buscas.classificar('modelo de e-mail de prospecção')['tipo_pagina'] == 'modelo'
    assert mapa_buscas.classificar('lgpd e-mail marketing')['cluster'] == 'lgpd'
    assert mapa_buscas.classificar('calculadora de cac')['tipo_pagina'] == 'ferramenta'
    conn = A._conn()
    try:
        c = conn.cursor()
        cfg.criar_tabelas(c)
        for q in ('como prospectar clientes para transportadora', 'como prospectar clientes transportadora',
                  'como fazer prospecção de clientes por telefone b2b', 'receita de bolo de cenoura'):
            mapa_buscas.gravar(c, q, 'teste', impressoes=500)
        # demanda real caindo numa página que não responde (lista de empresas, posição 23)
        mapa_buscas.gravar(c, 'como abordar cliente b2b pela primeira vez', 'gsc', impressoes=300, posicao=23.0,
                           pagina='/empresas/usinagem')
        mapa_buscas.gravar(c, 'como montar lista de prospecção de clientes', 'gsc', impressoes=300, posicao=4.0,
                           pagina='/empresas/usinagem')
        alvos = mapa_buscas.alvos_satelites(c, 10)
        conn.commit()
    finally:
        conn.close()
    consultas = [a['consulta'] for a in alvos]
    assert sum('transportadora' in q for q in consultas) == 1          # quase-duplicata vira uma página só
    assert 'receita de bolo de cenoura' not in consultas                 # fora do ICP
    assert 'como abordar cliente b2b pela primeira vez' in consultas     # posição 23 numa lista: merece resposta
    assert 'como montar lista de prospecção de clientes' not in consultas  # já ranqueia bem (posição 4)
