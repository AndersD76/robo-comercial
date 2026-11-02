# -*- coding: utf-8 -*-
"""
Validação de telefone e e-mail de lead — usada pelo robô (na coleta), pelo
painel (na exibição) e pelos envios (antes de disparar).

Por que existe: o robô gravava lixo como contato. Quando a empresa não tinha
site, ele raspava a própria página do Google Maps e pegava o press@google.com
do rodapé, e a regex de telefone recortava 11 dígitos do meio de qualquer
número comprido do HTML (IDs, avaliações "4,9(17)") — telefones como
(17) 93472-9613 para lojas de Goiás.
"""

import re

# DDD -> UF (Anatel)
DDD_UF = {}
for _uf, _ddds in {
    'SP': '11 12 13 14 15 16 17 18 19', 'RJ': '21 22 24', 'ES': '27 28',
    'MG': '31 32 33 34 35 37 38', 'PR': '41 42 43 44 45 46', 'SC': '47 48 49',
    'RS': '51 53 54 55', 'DF': '61', 'GO': '62 64', 'TO': '63', 'MT': '65 66',
    'MS': '67', 'AC': '68', 'RO': '69', 'BA': '71 73 74 75 77', 'SE': '79',
    'PE': '81 87', 'AL': '82', 'PB': '83', 'RN': '84', 'CE': '85 88',
    'PI': '86 89', 'PA': '91 93 94', 'AM': '92 97', 'RR': '95', 'AP': '96',
    'MA': '98 99',
}.items():
    for _d in _ddds.split():
        DDD_UF[_d] = _uf

# Cidades do Entorno do DF (GO) usam o 61
_DDD_UF_EXTRA = {('61', 'GO')}

# Telefone só no formato de telefone: separador antes dos 4 últimos dígitos,
# nada de dígito, vírgula, ponto, barra ou "(" grudado antes (avaliação
# "4,9(17)", IDs, datas) e nenhum dígito depois.
_TEL_RE = re.compile(
    r'(?<![\d,./(])\(?(\d{2})\)?[\s.-]?(\d{4,5})[\s.-](\d{4})(?!\d)')

# Domínios que nunca são contato da empresa prospectada
_DOMINIOS_PLATAFORMA = {
    'google.com', 'google.com.br', 'gstatic.com', 'googleusercontent.com',
    'googleapis.com', 'googlemail.com.br', 'youtube.com', 'facebook.com',
    'fb.com', 'instagram.com', 'whatsapp.com', 'whatsapp.net',
    'linkedin.com', 'twitter.com', 'x.com', 'tiktok.com', 'bing.com',
    'microsoft.com', 'duckduckgo.com', 'yahoo-inc.com', 'apple.com',
    'shopee.com', 'shopee.com.br', 'mercadolivre.com.br', 'mercadolibre.com',
    'amazon.com', 'amazon.com.br', 'magazineluiza.com.br', 'wix.com',
    'wixpress.com', 'godaddy.com', 'hostgator.com.br', 'locaweb.com.br',
    'kinghost.com.br', 'umbler.com', 'cloudflare.com', 'sentry.io',
    'jsdelivr.net', 'w3.org', 'schema.org', 'example.com', 'example.org',
    'domain.com', 'email.com', 'dominio.com', 'dominio.com.br',
    'empresa.com.br', 'seusite.com.br', 'seudominio.com.br', 'yourdomain.com',
    'reclameaqui.com.br', 'guiamais.com.br', 'apontador.com.br', 'yelp.com',
    'tripadvisor.com', 'tripadvisor.com.br', 'ifood.com.br', 'yandex.ru',
    'yandex.com', 'brave.com', 'cnpj.biz', 'cnpj.info', 'econodata.com.br',
}
_SUFIXOS_PLATAFORMA = ('.gov.br', '.jus.br', '.leg.br')
_LOCAIS_RUINS = {'press', 'abuse', 'noreply', 'no-reply', 'donotreply',
                 'do-not-reply', 'postmaster', 'mailer-daemon', 'webmaster',
                 'hostmaster', 'privacy', 'example', 'seuemail', 'email',
                 'nome', 'usuario', 'user', 'teste', 'test'}
_EMAIL_RE = re.compile(r'^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$')


def _so_digitos(v):
    return re.sub(r'\D', '', str(v or ''))


def normalizar_telefone(valor):
    """'(62) 99494-0765' / '5562994940765' -> '62994940765'; None se não for
    um telefone brasileiro plausível."""
    d = _so_digitos(valor)
    if d.startswith('55') and len(d) in (12, 13):
        d = d[2:]
    if re.fullmatch(r'0[3589]00\d{7}', d):   # 0800/0300/0500/0900
        return d
    if d.startswith('0') and len(d) in (11, 12):  # 0 + DDD (discagem antiga)
        d = d[1:]
    if len(d) not in (10, 11) or d[:2] not in DDD_UF:
        return None
    numero = d[2:]
    if len(numero) == 8 and numero[0] in '6789':
        # Celular no formato antigo, de antes do 9º dígito: todo celular
        # brasileiro ganhou o 9 na frente
        numero = '9' + numero
        d = d[:2] + numero
    if len(numero) == 9 and numero[0] != '9':
        return None
    if len(numero) == 8 and numero[0] not in '2345':
        return None
    if len(set(numero)) <= 2:  # 99999-9999, 12121212...
        return None
    return d


def telefones_do_texto(texto):
    """Telefones válidos encontrados num texto/HTML, sem repetição."""
    achados = []
    for m in _TEL_RE.finditer(texto or ''):
        n = normalizar_telefone(''.join(m.groups()))
        if n and n not in achados:
            achados.append(n)
    return achados


def telefone_compativel(telefone, uf):
    """O DDD é do estado da empresa? Sem UF conhecida, aceita."""
    n = normalizar_telefone(telefone)
    if not n:
        return False
    if n.startswith('0'):  # 0800: nacional, vale em qualquer estado
        return True
    uf = (uf or '').strip().upper()
    if len(uf) != 2:
        return True
    return DDD_UF.get(n[:2]) == uf or (n[:2], uf) in _DDD_UF_EXTRA


def dominio_plataforma(dominio):
    d = (dominio or '').lower().strip().strip('.')
    d = re.sub(r'^https?://', '', d).split('/')[0].split(':')[0]
    d = re.sub(r'^www\.', '', d)
    if not d:
        return False
    if d.endswith(_SUFIXOS_PLATAFORMA):
        return True
    return any(d == p or d.endswith('.' + p) for p in _DOMINIOS_PLATAFORMA) \
        or d.startswith(('google.', 'maps.google.'))


def email_valido(email):
    """E-mail plausível de uma empresa (não de plataforma, imagem ou modelo)."""
    e = (email or '').strip().lower()
    if not _EMAIL_RE.match(e) or len(e) > 80:
        return False
    local, dominio = e.split('@', 1)
    if local in _LOCAIS_RUINS or dominio_plataforma(dominio):
        return False
    if re.search(r'\.(png|jpe?g|gif|svg|webp|css|js)$', e):
        return False
    return True


def limpar_contatos(lead, checar_uf=False):
    """Apaga (no dicionário, não no banco) e-mail e telefones que não passam
    na validação. Se o e-mail era de plataforma, o lead foi raspado de uma
    página do Google/afins e os telefones de lá também não são confiáveis.

    checar_uf: também descarta telefone cujo DDD não é do estado do lead.
    Só use quando o estado é confiável (veio da Receita): o estado que o
    robô adivinha pelo texto da busca erra, e aí o telefone bom sumiria."""
    email_lixo = bool(lead.get('email')) and not email_valido(lead['email'])
    if email_lixo:
        lead['email'] = None
    uf = lead.get('estado') if checar_uf else None
    for campo in ('telefone', 'telefone2', 'whatsapp'):
        v = lead.get(campo)
        if v and (email_lixo or not telefone_compativel(v, uf)):
            lead[campo] = None
    return lead
