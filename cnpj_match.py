# -*- coding: utf-8 -*-
"""Casamento de lead da web com a base da Receita.

Usado pelo robô (robo_pili/run_busca.py) e pelo worker local
(scripts/enriquecer_local.py), para os dois decidirem igual.

Medido contra o banco real em 2026-08:
  por nome    : 0/30   (o nome da web é título de página, não razão social)
  por email   : 0/40
  por domínio : 1/40
  por telefone: 32/204

Telefone acha o candidato; o nome confirma. Sem a confirmação o telefone
já trocou "Signo Assessoria Contábil" por "Trma Manutenção".
"""
import re
import unicodedata

# Palavras que não identificam empresa nenhuma: termo societário, genérico
# de ramo, e lixo de título de página ("Termos de Uso", "Fale Conosco").
PALAVRAS_VAZIAS = frozenset((
    'ltda', 'epp', 'eireli', 'mei', 'cia', 'sociedade', 'individual',
    'associacao', 'servicos', 'servico', 'comercio', 'industria',
    'transportes', 'consultoria', 'assessoria', 'empresa', 'empresas',
    'grupo', 'centro', 'brasil', 'brasileira', 'nacional',
    'termos', 'termo', 'privacidade', 'politica', 'home', 'inicial',
    'inicio', 'contato', 'contatos', 'fale', 'conosco', 'quem', 'somos',
    'sobre', 'institucional', 'produtos', 'solucoes', 'blog', 'noticias',
    'trabalhe', 'localizacao', 'cookies', 'login', 'orcamento',
    'atendimento', 'pagina', 'site', 'oficial', 'bem', 'vindo',
))


def sem_acento(texto):
    return ''.join(c for c in unicodedata.normalize('NFD', str(texto or ''))
                   if unicodedata.category(c) != 'Mn')


def telefone_canonico(valor):
    """Formatos possíveis do telefone, como a ingestão grava: (DD) NNNNNNNN.

    Devolve lista porque a Receita costuma guardar celular com 8 dígitos,
    sem o 9 que o site publica.
    """
    d = re.sub(r'\D', '', str(valor or ''))
    if d.startswith('55') and len(d) > 11:
        d = d[2:]
    if len(d) == 11 and d[2] == '9':
        return [f'({d[:2]}) {d[2:]}', f'({d[:2]}) {d[3:]}']
    if len(d) in (10, 11):
        return [f'({d[:2]}) {d[2:]}']
    return []


def tokens_nome(valor):
    """Palavras significativas do nome, sem acento nem termo genérico."""
    t = sem_acento(valor).lower()
    t = re.sub(r'&[a-z]+;', ' ', t)        # &gt; e afins vindos do HTML
    t = re.sub(r'[^a-z0-9 ]', ' ', t)
    return {p for p in t.split()
            if len(p) >= 4 and p not in PALAVRAS_VAZIAS}


def nome_confere(nome_web, oficial):
    """O nome oficial tem a ver com o que a web trouxe?

    Quando o nome da web é só lixo ("Termos de Uso") não há o que
    conferir e aceitamos — é justamente o caso em que mais precisamos do
    dado oficial.
    """
    web = tokens_nome(nome_web)
    if not web:
        return True
    alvo = (tokens_nome(oficial.get('razao_social'))
            | tokens_nome(oficial.get('nome_fantasia')))
    if not alvo:
        return True
    if web & alvo:
        return True
    # "AndersTech" x "ANDERS CONSULTORIA": uma começa com a outra
    return any(a.startswith(w) or w.startswith(a)
               for w in web for a in alvo if min(len(w), len(a)) >= 5)


def variantes_telefone(lead):
    v = []
    for campo in ('telefone', 'whatsapp'):
        v.extend(telefone_canonico(lead.get(campo)))
    return v


def aplicar(lead, oficial):
    """Sobrepõe o que veio da web com o dado oficial. (lead, casou)."""
    if not oficial:
        return lead, False
    cb = (oficial.get('cnpj_basico') or '').strip()
    if cb and len(cb) == 8 and not lead.get('cnpj'):
        lead['cnpj_raiz'] = cb
    nome_oficial = (oficial.get('nome_fantasia')
                    or oficial.get('razao_social') or '').strip()
    if nome_oficial:
        lead['razao_social'] = (oficial.get('razao_social') or '').strip()
        lead['nome_fantasia'] = nome_oficial.title()
    for origem, destino in (('uf', 'estado'), ('municipio', 'cidade')):
        v = (oficial.get(origem) or '').strip()
        if v:
            lead[destino] = v
    if oficial.get('cnae_principal'):
        lead['segmento'] = str(oficial['cnae_principal']).strip()
    # O sócio-administrador vale mais que qualquer nome raspado do site,
    # porque é quem assina a compra.
    if oficial.get('socio_nome'):
        lead['decisor_nome'] = oficial['socio_nome']
        lead['decisor_cargo'] = oficial.get('socio_cargo') or 'Sócio'
    if not lead.get('email') and oficial.get('email'):
        lead['email'] = oficial['email']
    if not lead.get('telefone') and oficial.get('telefone'):
        lead['telefone'] = oficial['telefone']
    return lead, True
