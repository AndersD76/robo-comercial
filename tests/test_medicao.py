# -*- coding: utf-8 -*-
"""Ingestão de Search Console e Bing com respostas simuladas (sem rede e
sem banco): confere o que é gravado a partir do formato das APIs."""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import medicao  # noqa: E402


class Resp:
    def __init__(self, dados, status=200):
        self._d, self.status_code = dados, status

    def json(self):
        return self._d

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class SessaoGSC:
    def __init__(self):
        self.chamadas = []

    def post(self, url, json=None):
        self.chamadas.append(url)
        if 'searchAnalytics' in url and json['dimensions'] == ['date', 'page']:
            return Resp({'rows': [
                {'keys': ['2026-11-05', 'https://www.turbovenda.com.br/empresas/usinagem/caxias-do-sul-rs'],
                 'clicks': 9, 'impressions': 400, 'ctr': .0225, 'position': 8.1}]})
        if 'searchAnalytics' in url:
            return Resp({'rows': [
                {'keys': ['2026-11-05', 'lista de empresas por cidade', 'https://www.turbovenda.com.br/ferramentas/lista-de-empresas'],
                 'clicks': 3, 'impressions': 120, 'ctr': .025, 'position': 6.4},
                {'keys': ['2026-11-05', 'metalurgicas caxias', 'https://www.turbovenda.com.br/'],
                 'clicks': 0, 'impressions': 10, 'ctr': 0, 'position': 12.0}]})
        return Resp({'inspectionResult': {'indexStatusResult': {
            'verdict': 'PASS', 'coverageState': 'Enviada e indexada', 'lastCrawlTime': '2026-11-04T10:00:00Z'}}})

    def get(self, url, **kw):
        self.chamadas.append(url)
        return Resp({'sitemap': [{'path': 'https://www.turbovenda.com.br/sitemap-empresas-1.xml',
                                  'contents': [{'type': 'web', 'submitted': '5000', 'indexed': '3100'}]}]})


class Cursor:
    def __init__(self, log):
        self.log = log

    def execute(self, sql, params=None):
        self.log.append((' '.join(sql.split())[:60], params))


class Conn:
    def __init__(self):
        self.log = []

    def cursor(self):
        return Cursor(self.log)

    def commit(self):
        pass


def test_ingestao_gsc_grava_consultas_sitemaps_e_inspecao():
    conn, s = Conn(), SessaoGSC()
    n = medicao.ingerir_gsc(conn, '{}', 'sc-domain:turbovenda.com.br', sessao=s)
    assert n == 3
    consultas = [p for sql, p in conn.log if 'busca_consultas' in sql and p]
    assert consultas[0] == ('2026-11-05', 'lista de empresas por cidade', '/ferramentas/lista-de-empresas', 3, 120, 6.4)
    assert consultas[1][2] == '/'   # URL da home vira caminho "/"
    # segunda passada: total da página, com as consultas escondidas, sob consulta '*'
    assert consultas[2] == ('2026-11-05', '*', '/empresas/usinagem/caxias-do-sul-rs', 9, 400, 8.1)
    sitemaps = [p for sql, p in conn.log if 'busca_sitemaps' in sql and p]
    assert sitemaps[0][1:] == ('https://www.turbovenda.com.br/sitemap-empresas-1.xml', 5000, 3100)
    inspecoes = [p for sql, p in conn.log if 'busca_inspecao' in sql and p]
    assert len(inspecoes) == len(medicao.URLS_PRIORITARIAS) and inspecoes[0][2] == 'PASS'
    assert 'sc-domain%3Aturbovenda.com.br' in s.chamadas[0]


def test_propriedade_de_prefixo_ganha_a_barra_final():
    s = SessaoGSC()
    medicao.ingerir_gsc(Conn(), '{}', 'https://www.turbovenda.com.br', sessao=s)
    assert 'sites/https%3A%2F%2Fwww.turbovenda.com.br%2F/' in s.chamadas[0]


def test_ingestao_bing_le_datas_e_separa_consulta_de_pagina():
    class SessaoBing:
        def get(self, url, params=None, timeout=None):
            if 'GetQueryStats' in url:
                return Resp({'d': [{'Date': '/Date(1762300800000)/', 'Query': 'lista de empresas',
                                    'Clicks': 2, 'Impressions': 40, 'AvgImpressionPosition': 7.5}]})
            return Resp({'d': [{'Date': '/Date(1762300800000-0800)/', 'Query': 'https://www.turbovenda.com.br/precos',
                                'Clicks': 1, 'Impressions': 9, 'AvgImpressionPosition': 3}]})
    conn = Conn()
    assert medicao.ingerir_bing(conn, 'chave', sessao=SessaoBing()) == 2
    linhas = [p for sql, p in conn.log if 'busca_consultas' in sql and p]
    assert linhas[0] == (date(2025, 11, 5), 'lista de empresas', '*', 2, 40, 7.5)
    assert linhas[1][1:3] == ('*', '/precos')


def test_tipo_de_pagina():
    assert medicao.tipo_de_pagina('/empresas/usinagem/caxias-do-sul-rs') == 'segmento por cidade'
    assert medicao.tipo_de_pagina('/empresas/usinagem/estado/rs') == 'segmento por estado'
    assert medicao.tipo_de_pagina('/empresas/cidade/passo-fundo-rs') == 'empresas por cidade'
    assert medicao.tipo_de_pagina('/blog/x') == 'blog' and medicao.tipo_de_pagina('/') == 'home'


def test_share_of_voice_uma_rodada_por_mes():
    import pytest
    if not os.environ.get('DATABASE_URL'):
        pytest.skip('precisa de DATABASE_URL (mesmo falsa) para importar o app')
    import app

    class C:
        def __init__(self, existe, ultima):
            self.r, self.existe, self.ultima = None, existe, ultima

        def execute(self, sql, params=None):
            self.r = {'t': 'share_of_voice' if self.existe else None} if 'to_regclass' in sql else {'r': self.ultima}

        def fetchone(self):
            return self.r
    hoje = date(2026, 12, 1)
    assert app._sov_pendente(C(False, None), hoje)                    # nunca rodou
    assert app._sov_pendente(C(True, date(2026, 11, 9)), hoje)        # última no mês passado
    assert not app._sov_pendente(C(True, date(2026, 12, 1)), hoje)    # já rodou neste mês
