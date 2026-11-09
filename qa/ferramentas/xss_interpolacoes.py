# -*- coding: utf-8 -*-
"""Interpolações ${...} de campos de dados nos templates que montam HTML em JS.

- `python qa/ferramentas/xss_interpolacoes.py <arquivos>`: lista e classifica
  o contexto (texto, atributo, url, JS em atributo, HTML aninhado);
- `inseguras(arquivo)`: o que chega ao HTML sem esc()/escOu()/urlSegura(),
  inclusive dentro de HTML aninhado (usado em tests/test_seguranca_qa.py).
"""
import re
import sys

CAMPO = re.compile(r'\b[a-z]{1,5}\.(nome_fantasia|nome|razao_social|email|segmento|cidade|website|site|descricao|'
                   r'local|cargo|mensagem|empresa|empresa_nome|url_perfil|whatsapp|telefone|cnpj|assunto|resposta|'
                   r'titulo|label|token_preview|schema_name|bairro|endereco|observacao|obs|notas|texto|corpo|'
                   r'linkedin|instagram|socio|decisor|_decisor|_decisor_linkedin|origem|fonte|termo|motivo|erro|error)\b')
PROTEGIDO = re.compile(r'\b(esc|escOu|urlSegura)\((?:[^()]|\([^()]*\))*\)')
CONDICAO = re.compile(r'^\s*[a-z]{1,5}\.[a-z_]+\s*\?')
ANINHADO = re.compile(r'`([^`]*)`')


def expressoes(s):
    i = 0
    while True:
        i = s.find('${', i)
        if i < 0:
            return
        prof, j = 1, i + 2
        while j < len(s) and prof:
            prof += {'{': 1, '}': -1}.get(s[j], 0)
            j += 1
        yield i, s[i + 2:j - 1]
        i = j


def contexto(s, i):
    antes = s[max(0, i - 160):i]
    tag = antes.rsplit('<', 1)[-1] if '<' in antes else ''
    if '>' in tag:
        return 'texto'
    if re.search(r'\bon[a-z]+\s*=\s*"[^"]*$', tag):
        return 'js-em-atributo'
    if re.search(r'\b(href|src|action)\s*=\s*"[^"]*$', tag):
        return 'url'
    if re.search(r'=\s*"[^"]*$', tag):
        return 'atributo'
    return 'texto'


def _checar(texto, ruins, linha0=0):
    for i, e in expressoes(texto):
        linha = linha0 + texto.count('\n', 0, i)
        for corpo in ANINHADO.findall(e):          # HTML aninhado: checa por dentro
            _checar(corpo, ruins, linha)
        restos = ANINHADO.sub('', e)
        restos = PROTEGIDO.sub('', restos)
        restos = CONDICAO.sub('', restos)          # campo só como condição do ternário
        if CAMPO.search(restos):
            ruins.append((linha + 1, e[:80]))


def inseguras(caminho):
    ruins = []
    _checar(open(caminho, encoding='utf-8').read(), ruins)
    return ruins


def _main():
    for f in sys.argv[1:]:
        s = open(f, encoding='utf-8').read()
        for i, e in expressoes(s):
            if not CAMPO.search(e) or e.strip().startswith(('esc(', 'escOu(', 'urlSegura(')):
                continue
            tipo = 'html-aninhado' if ('`' in e or '<' in e) else contexto(s, i)
            print(f"{f}:{s.count(chr(10), 0, i) + 1}\t{tipo}\t{e[:90]}")


if __name__ == '__main__':
    _main()
