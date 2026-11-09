# -*- coding: utf-8 -*-
"""Regras puras da conta do cliente: cadastro, login e e-mails de sistema.

Sem banco e sem Flask, para testar com DATABASE_URL vazio (como no CI).
"""
import hashlib
import re
from html import escape as _esc
from urllib.parse import urlparse

URL_SITE = 'https://www.turbovenda.com.br'
# O domínio turbovenda.com.br não tem MX: e-mail para suporte@/contato@
# volta. O suporte é pelo WhatsApp.
WHATSAPP_SUPORTE = '5554999648368'
WHATSAPP_SUPORTE_TXT = '(54) 99964-8368'


def usa_template_pili(email_usuario):
    """O template antigo (email_pili.html, propaganda da Pili Equipamentos)
    só vale para a conta da própria Pili. Para qualquer outro cliente ele
    mandava a propaganda da Pili em nome do cliente."""
    email = (email_usuario or '').strip().lower()
    return email.endswith('@pili.ind.br')


# ------------------------------------------------------------------ site ---

def normalizar_site(valor):
    """Site digitado pelo cliente -> 'https://empresa.com.br' (ou '').

    O campo era <input type="url"> e o navegador barrava o cadastro de
    quem digitava "empresa.com.br" sem https:// — num campo opcional.
    Aceita "empresa.com.br", "www.empresa.com.br", "http(s)://..." e
    caminho; devolve '' para vazio ou para o que não parece um site.
    """
    v = (valor or '').strip()
    if not v:
        return ''
    if any(ch.isspace() for ch in v) or '@' in v:
        return ''
    if not re.match(r'^[a-z][a-z0-9+.\-]*://', v, re.I):
        v = 'https://' + v.lstrip('/')
    try:
        p = urlparse(v)
        porta = p.port
    except ValueError:
        return ''
    if p.scheme.lower() not in ('http', 'https'):
        return ''
    host = (p.hostname or '').lower().rstrip('.')
    try:
        host_ascii = host.encode('idna').decode('ascii')
    except UnicodeError:
        return ''
    if ('.' not in host_ascii
            or not re.fullmatch(r'[a-z0-9.\-]+', host_ascii)
            or host_ascii.startswith(('.', '-'))
            or '..' in host_ascii
            or not re.search(r'\.[a-z]{2,}$', host_ascii)):
        return ''
    caminho = p.path if p.path not in ('', '/') else ''
    porta = f':{porta}' if porta else ''
    return f'{p.scheme.lower()}://{host}{porta}{caminho}'


# ----------------------------------------------------------------- login ---

def next_seguro(valor):
    """Destino depois do login, só se for caminho relativo DESTE site.

    Aceita '/dashboard?upgrade=starter'. Recusa URL absoluta, '//outro',
    '/\\outro', esquema (javascript:), caractere de controle e as próprias
    páginas de login/logout/cadastro (evita laço). Senão devolve None.
    """
    v = (valor or '').strip()
    if not v or len(v) > 500:
        return None
    if not v.startswith('/') or v.startswith('//') or '\\' in v:
        return None
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in v):
        return None
    p = urlparse(v)
    if p.scheme or p.netloc:
        return None
    if p.path.rstrip('/') in ('/login', '/logout', '/cadastro'):
        return None
    return v


# ------------------------------------------------------ senha esquecida ---

def hash_token(token):
    """Hash do token de redefinição de senha. Só o hash vai para o banco:
    quem ler a tabela não consegue usar o link."""
    return hashlib.sha256((token or '').encode('utf-8')).hexdigest()


# ------------------------------------------------- e-mails de sistema ---

def _rodape_suporte():
    return (
        '<p style="font-size:13px;color:#64748b;line-height:1.6;margin:28px 0 0">'
        f'Precisa de ajuda? Fale com a gente pelo WhatsApp '
        f'<a href="https://wa.me/{WHATSAPP_SUPORTE}" style="color:#6366f1">'
        f'{WHATSAPP_SUPORTE_TXT}</a>.</p>'
        '<hr style="border:none;border-top:1px solid #e2e8f0;margin:28px 0 16px">'
        '<p style="font-size:12px;color:#94a3b8;text-align:center;margin:0">'
        'TurboVenda — prospecção B2B com IA</p>')


def _botao(link, texto):
    return (
        '<p style="text-align:center;margin:28px 0">'
        f'<a href="{_esc(link)}" style="display:inline-block;background:#6366f1;'
        'color:#ffffff;text-decoration:none;padding:14px 32px;border-radius:8px;'
        f'font-size:16px;font-weight:600">{_esc(texto)}</a></p>')


def _corpo(conteudo):
    return ('<div style="font-family:Arial,Helvetica,sans-serif;max-width:600px;'
            'margin:0 auto;padding:24px;color:#1e293b;font-size:16px;'
            'line-height:1.6">'
            '<h1 style="color:#6366f1;font-size:22px;margin:0 0 24px">'
            'TurboVenda</h1>' + conteudo + _rodape_suporte() + '</div>')


def html_boas_vindas(empresa, url_login, tem_termos=False):
    """E-mail de boas-vindas do cadastro, com o próximo passo."""
    nome = _esc((empresa or '').strip() or 'tudo bem')
    if tem_termos:
        passo = (
            '<p><strong>Próximo passo:</strong> o robô já sabe o que procurar. '
            'Entre, confira os termos em Configurar e clique em '
            '<strong>Salvar e ir para o Dashboard</strong> — o robô liga '
            'sozinho e os primeiros leads aparecem em alguns minutos.</p>')
    else:
        passo = (
            '<p><strong>Próximo passo:</strong> em Configurar, descreva o que '
            'você vende e para quem, escolha os estados e clique em '
            '<strong>Configurar tudo</strong>. Depois clique em '
            '<strong>Salvar e ir para o Dashboard</strong> — o robô liga '
            'sozinho e os primeiros leads aparecem em alguns minutos.</p>')
    return _corpo(
        f'<p>Olá, {nome}.</p>'
        '<p>Sua conta no TurboVenda está criada. O teste grátis inclui até '
        '50 leads com telefone e e-mail, encontrados pelo robô.</p>'
        + passo + _botao(url_login, 'Entrar no TurboVenda'))


def html_redefinir_senha(link):
    """E-mail com o link de redefinição de senha (vale 1 hora, uso único)."""
    return _corpo(
        '<p>Recebemos um pedido para criar uma nova senha para a sua conta.</p>'
        + _botao(link, 'Criar nova senha') +
        '<p>O link vale por <strong>1 hora</strong> e só pode ser usado uma '
        'vez. Se não foi você que pediu, ignore este e-mail: sua senha '
        'continua a mesma.</p>')
