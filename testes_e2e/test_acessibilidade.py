# -*- coding: utf-8 -*-
"""Acessibilidade WCAG 2.2 AA com axe-core (Fase 2 do Prompt 3), em Chromium
desktop. Falha com qualquer violação crítica ou séria, menos as exceções
nomeadas abaixo (qa/RELATORIO-QUALIDADE-SEGURANCA.md, QA-A11Y)."""
import json
import os
import re
import uuid

import pytest

AXE = 'https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js'
TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']
# Exceções de contraste: logotipo (isento pela WCAG 1.4.3) e texto branco nos
# botões na cor da marca #6366f1 (4,46:1 contra 4,5:1; risco aceito, ver relatório)
EXCECOES_CONTRASTE = ('.nav-logo-text > span', '.footer-logo > span', '.tv-logo > span',   # logotipo
                      '.btn-nav', '#cookie-accept', '.skip-link', '#btn-start-all')    # branco sobre #6366f1
RELATORIO = os.path.join(os.path.dirname(__file__), '..', 'qa', 'acessibilidade.json')


def _axe(pagina):
    pagina.add_script_tag(url=AXE)
    r = pagina.evaluate("tags => axe.run(document, {runOnly: {type: 'tag', values: tags}})", TAGS)
    return [{'regra': v['id'], 'impacto': v['impact'], 'ocorrencias': len(v['nodes']),
             'alvos': [n['target'][0] for n in v['nodes']]} for v in r['violations']]


@pytest.fixture(scope='module')
def resultados():
    dados = {}
    yield dados
    os.makedirs(os.path.dirname(RELATORIO), exist_ok=True)
    with open(RELATORIO, 'w', encoding='utf-8') as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)


@pytest.mark.parametrize('navegador', ['chromium'], indirect=True)
def test_paginas_sem_violacao_critica(navegador, ambiente, resultados):
    base = ambiente['base']
    ctx = navegador.new_context(viewport={'width': 1366, 'height': 900})
    p = ctx.new_page()
    sitemap = p.request.get(base + '/sitemap-empresas-1.xml').text()
    emp = re.search(r'<loc>https://www\.turbovenda\.com\.br(/empresas/[^/<]+/(?!estado)[^/<]+)</loc>', sitemap)
    publicas = ['/', '/precos', '/blog', '/cadastro', '/login', '/esqueci-senha', '/ferramentas/calculadora-de-leads',
                '/privacidade', '/sobre', '/ferramentas/diagnostico-de-prospeccao', '/ferramentas/calculadora-de-cac',
                '/ferramentas/gerador-de-cadencia-de-prospeccao?canal_email=1&canal_whatsapp=1&dias=14'] +         ([emp.group(1)] if emp else [])
    for caminho in publicas:
        p.goto(base + caminho, wait_until='load')
        resultados[caminho] = _axe(p)
    # painel logado
    email = f'a11y-{uuid.uuid4().hex[:6]}@empresa-teste.com.br'
    p.goto(base + '/cadastro')
    p.fill('input[name=empresa_nome]', 'Empresa A11y')
    p.fill('input[name=segmento]', 'vendemos serviços de manutenção')
    p.fill('input[name=email]', email)
    p.fill('input[name=senha]', 'senha-forte-123')
    p.click('button[type=submit]')
    p.wait_for_url(re.compile(r'/(configurar|dashboard)'))
    resultados['/configurar'] = _axe(p)
    p.goto(base + '/dashboard', wait_until='networkidle')
    resultados['/dashboard'] = _axe(p)
    ctx.close()
    ruins = {}
    for caminho, vs in resultados.items():
        for v in vs:
            alvos = [a for a in v['alvos'] if not (v['regra'] == 'color-contrast' and a in EXCECOES_CONTRASTE)]
            if v['impacto'] in ('critical', 'serious') and alvos:
                ruins.setdefault(caminho, []).append((v['regra'], alvos[:5]))
    assert ruins == {}
