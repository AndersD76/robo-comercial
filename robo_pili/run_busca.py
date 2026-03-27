# -*- coding: utf-8 -*-
"""
Máquina de Vendas — Bot de Busca
Roda somente o ciclo de prospecção (sem WhatsApp).
Uso: python run_busca.py --schema emp_1
"""

import argparse
import asyncio
import json
import os
import random
import re
import sys

import aiohttp
import psycopg2
import psycopg2.extras

# Domínios de blogs, portais e sites que NÃO são empresas compradores
_DOMINIOS_BLACKLIST = {
    'globo.com', 'g1.globo.com', 'uol.com.br', 'terra.com.br',
    'exame.com', 'folha.uol.com.br', 'estadao.com.br',
    'infomoney.com.br', 'valor.globo.com', 'cnnbrasil.com.br',
    'gazetadopovo.com.br', 'r7.com', 'ig.com.br', 'band.uol.com.br',
    'medium.com', 'wikipedia.org', 'pt.wikipedia.org',
    'youtube.com', 'facebook.com', 'instagram.com', 'twitter.com',
    'linkedin.com', 'tiktok.com', 'pinterest.com', 'reddit.com',
    'amazon.com.br', 'mercadolivre.com.br', 'magazineluiza.com.br',
    'gov.br', 'jus.br', 'senado.leg.br', 'camara.leg.br',
    'sebrae.com.br', 'jusbrasil.com.br', 'conjur.com.br',
    'techtudo.com.br', 'canaltech.com.br', 'tecmundo.com.br',
    'olhardigital.com.br', 'tecnoblog.net', 'b9.com.br',
    'rockcontent.com', 'resultadosdigitais.com.br', 'neilpatel.com',
    'hubspot.com', 'salesforce.com', 'pipedrive.com',
    'blog.bling.com.br', 'blog.contaazul.com',
    'glassdoor.com.br', 'indeed.com.br', 'vagas.com.br',
    'catho.com.br', 'gupy.io', 'infojobs.com.br',
    'clicksign.com', 'docusign.com.br',
    'bitrix24.com.br', 'bitrix24.com', 'clockify.me',
    'sesametime.com', 'pontomais.com.br',
    'guiadacarreira.com.br', 'mundoconectado.com.br',
}

# Palavras no domínio que indicam blog/portal (não empresa)
_DOMINIO_PATTERNS_SKIP = [
    'blog', 'wiki', 'forum', 'noticias', 'news', 'revista',
    'jornal', 'guia', 'portal', 'dicas', 'tutorial',
    'comparativo', 'ranking', 'melhor', 'review',
]

# Adiciona o diretório atual ao path para importar buscador.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from buscador import Buscador  # noqa: E402


def _fix_url(url: str) -> str:
    if url.startswith('psql://'):
        return 'postgresql://' + url[7:]
    if url.startswith('postgres://'):
        return 'postgresql://' + url[11:]
    return url


DATABASE_URL = _fix_url(os.environ.get('DATABASE_URL', ''))


def _conn(schema: str):
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    with conn.cursor() as c:
        c.execute('SET search_path TO %s, public', (schema,))
    conn.commit()
    return conn


def _ensure_bot_config(schema: str):
    """Cria tabela bot_config se não existir."""
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS bot_config (
            id SERIAL PRIMARY KEY,
            empresa_nome TEXT, website TEXT, descricao TEXT,
            termos_busca JSONB DEFAULT '[]',
            linkedin_email TEXT, linkedin_password TEXT,
            linkedin_cargos JSONB DEFAULT '[]',
            atualizado_em TIMESTAMP DEFAULT NOW()
        )""")
        conn.commit()
        conn.close()
    except Exception:
        pass


def get_descricao_empresa(schema: str) -> str:
    """Lê a descrição da empresa do bot_config."""
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute("SELECT descricao FROM bot_config ORDER BY id DESC LIMIT 1")
        row = c.fetchone()
        conn.close()
        if row and row.get('descricao'):
            return row['descricao']
    except Exception:
        pass
    return ''


def _gerar_palavras_concorrente(descricao: str) -> list:
    """Extrai palavras-chave do produto/serviço para filtrar concorrentes.

    Retorna palavras substantivas que identificam o que a empresa VENDE.
    Se um resultado de busca contém várias dessas, provavelmente é concorrente.
    """
    if not descricao:
        return []
    desc = descricao.lower()
    # Remove pontuação
    desc = re.sub(r'[.,;:!?()"\']', ' ', desc)

    # Stop words — palavras que não significam nada sozinhas
    stop = {
        'de', 'do', 'da', 'dos', 'das', 'em', 'no', 'na', 'nos', 'nas',
        'um', 'uma', 'uns', 'umas', 'o', 'a', 'os', 'as', 'e', 'ou',
        'que', 'para', 'por', 'com', 'como', 'se', 'mais', 'muito',
        'seu', 'sua', 'seus', 'suas', 'ele', 'ela', 'nós', 'nos',
        'é', 'são', 'ser', 'ter', 'está', 'foi', 'ao', 'à', 'às',
        'pelo', 'pela', 'isso', 'isto', 'esse', 'essa', 'este', 'esta',
        'todo', 'toda', 'cada', 'entre', 'sobre', 'após', 'até',
    }

    tokens = desc.split()
    # Palavras significativas (substantivos, verbos importantes)
    significativas = [t for t in tokens
                      if t not in stop and len(t) > 3]

    resultado = []
    # Palavras soltas significativas
    for t in significativas:
        resultado.append(t)

    # Bigramas significativos (duas palavras sem stop words no meio)
    for i in range(len(tokens) - 1):
        a, b = tokens[i], tokens[i + 1]
        if a not in stop and b not in stop and len(a) > 2 and len(b) > 2:
            resultado.append(f'{a} {b}')

    # Remove duplicatas
    vistos = set()
    unicas = []
    for p in resultado:
        if p not in vistos:
            vistos.add(p)
            unicas.append(p)
    return unicas


def get_termos(schema: str) -> list:
    """Lê termos de busca da tabela bot_config. Fallback para config.py."""
    _ensure_bot_config(schema)
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute("SELECT termos_busca FROM bot_config ORDER BY id DESC LIMIT 1")
        row = c.fetchone()
        conn.close()
        if row and row['termos_busca']:
            termos = row['termos_busca']
            if isinstance(termos, str):
                termos = json.loads(termos)
            if termos:
                return termos
    except Exception as e:
        print(f'[run_busca] erro ao ler termos: {e}', flush=True)
    # Fallback
    try:
        from config import TERMOS_BUSCA
        return TERMOS_BUSCA
    except ImportError:
        return ['empresa industria site:.com.br contato']


def log_db(schema: str, tipo: str, mensagem: str):
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute("INSERT INTO logs (tipo, mensagem) VALUES (%s, %s)", (tipo, mensagem))
        conn.commit()
        conn.close()
    except Exception:
        pass


def incrementar(schema: str, tipo: str):
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute("""INSERT INTO acoes_diarias (data, tipo, quantidade) VALUES (CURRENT_DATE,%s,1)
                     ON CONFLICT(data,tipo) DO UPDATE SET quantidade=acoes_diarias.quantidade+1""",
                  (tipo,))
        conn.commit()
        conn.close()
    except Exception:
        pass


def get_contagem_diaria(schema: str, tipo: str) -> int:
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute("SELECT quantidade FROM acoes_diarias WHERE data=CURRENT_DATE AND tipo=%s", (tipo,))
        r = c.fetchone()
        conn.close()
        return r['quantidade'] if r else 0
    except Exception:
        return 0


def salvar_empresa(schema: str, dados: dict):
    conn = _conn(schema)
    c = conn.cursor()
    try:
        for field in ('cnpj', 'website'):
            if dados.get(field):
                c.execute(f"SELECT id FROM empresas WHERE {field} = %s", (dados[field],))
                ex = c.fetchone()
                if ex:
                    conn.close()
                    return None  # já existe

        # Verifica telefone/whatsapp duplicado
        tel = dados.get('whatsapp') or dados.get('telefone')
        if tel:
            numero = ''.join(filter(str.isdigit, str(tel)))
            if len(numero) >= 8:
                c.execute("SELECT id FROM empresas WHERE whatsapp LIKE %s OR telefone LIKE %s",
                          (f'%{numero[-8:]}%', f'%{numero[-8:]}%'))
                if c.fetchone():
                    conn.close()
                    return None

        c.execute("""INSERT INTO empresas (
            cnpj, razao_social, nome_fantasia, segmento, porte, funcionarios,
            endereco, cidade, estado, telefone, telefone2, whatsapp, email,
            website, linkedin, instagram, fonte, score
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                  (dados.get('cnpj'), dados.get('razao_social'), dados.get('nome_fantasia'),
                   dados.get('segmento'), dados.get('porte'), dados.get('funcionarios'),
                   dados.get('endereco'), dados.get('cidade'), dados.get('estado'),
                   dados.get('telefone'), dados.get('telefone2'), dados.get('whatsapp'),
                   dados.get('email'), dados.get('website'), dados.get('linkedin'),
                   dados.get('instagram'), dados.get('fonte'), dados.get('score', 0)))
        empresa_id = c.fetchone()['id']
        conn.commit()
        return empresa_id
    except psycopg2.IntegrityError:
        conn.rollback()
        return None
    except Exception as e:
        conn.rollback()
        print(f'[salvar_empresa] {e}', flush=True)
        return None
    finally:
        conn.close()


def _extrair_emails(texto):
    """Extrai emails de um texto."""
    if not texto:
        return []
    return re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', texto)


def _extrair_telefones_texto(texto):
    """Extrai telefones brasileiros de um texto (snippet, título)."""
    if not texto:
        return []
    # Padrões: (XX) XXXXX-XXXX, (XX) XXXX-XXXX, XX XXXXX-XXXX, etc.
    padrao = r'\(?\d{2}\)?\s*\d{4,5}[-.\s]?\d{4}'
    encontrados = re.findall(padrao, texto)
    # Limpa e retorna só dígitos
    resultado = []
    for t in encontrados:
        digitos = re.sub(r'\D', '', t)
        if 10 <= len(digitos) <= 11:
            resultado.append(digitos)
    return resultado


_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml',
    'Accept-Language': 'pt-BR,pt;q=0.9',
}

# Páginas onde normalmente tem contato — ordem de prioridade
_CONTATO_PATHS = [
    '', '/contato', '/contact', '/fale-conosco',
    '/sobre', '/about', '/quem-somos',
    '/empresa', '/a-empresa',
]

_EMAIL_BLACKLIST = [
    '@sentry', '@example', '@test', '@wixpress', '@w3.org',
    '@schema.org', '@googlegroups', '@apple.com', '@microsoft',
    '.png', '.jpg', '.svg', '.gif', '.webp', '.css', '.js',
    'noreply', 'no-reply', 'mailer-daemon', 'postmaster',
    'wordpress', 'cookie', 'privacy', 'webmaster', 'hostmaster',
    'prefixo@dominio',
]

# Cargos de decisor de compra
_CARGOS_DECISOR = [
    'diretor', 'gerente', 'coordenador', 'supervisor', 'responsável',
    'compras', 'comercial', 'operações', 'operacoes', 'logística',
    'logistica', 'administrativo', 'financeiro', 'CEO', 'proprietário',
    'proprietario', 'sócio', 'socio', 'presidente', 'head',
    'manager', 'director', 'buyer', 'purchasing',
    'recebimento', 'armazenagem', 'produção', 'producao',
]


def _extrair_cnpj(texto):
    """Extrai CNPJ de um texto (XX.XXX.XXX/XXXX-XX ou só dígitos)."""
    if not texto:
        return None
    m = re.search(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}', texto)
    if m:
        return m.group()
    m = re.search(r'(?<!\d)(\d{14})(?!\d)', texto)
    if m:
        d = m.group()
        return f'{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}'
    return None


def _email_valido(email):
    """Filtra emails genéricos, de imagem, etc."""
    low = email.lower()
    if any(x in low for x in _EMAIL_BLACKLIST):
        return False
    if len(email) < 6 or len(email) > 80:
        return False
    # Rejeita emails com domínio genérico demais
    dominio = low.split('@')[-1]
    if dominio in ('dominio.com.br', 'empresa.com.br', 'seusite.com.br', 'email.com'):
        return False
    return True


def _extrair_mailto_tel(html):
    """Extrai emails de mailto: e telefones de tel: / href com whatsapp."""
    emails = []
    tels = []
    # mailto:
    for m in re.findall(r'mailto:([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})', html):
        if _email_valido(m) and m not in emails:
            emails.append(m)
    # tel: e wa.me
    for m in re.findall(r'(?:tel:|href=["\']tel:)[\s]*([+\d\s\-().]+)', html):
        digitos = re.sub(r'\D', '', m)
        if 10 <= len(digitos) <= 13 and digitos not in tels:
            tels.append(digitos)
    # wa.me links
    for m in re.findall(r'wa\.me/(\d+)', html):
        if m not in tels:
            tels.append(m)
    # api.whatsapp.com
    for m in re.findall(r'api\.whatsapp\.com/send\?phone=(\d+)', html):
        if m not in tels:
            tels.append(m)
    return emails, tels


def _nome_valido(nome):
    """Verifica se parece um nome de pessoa (2-4 palavras capitalizadas, sem lixo)."""
    if not nome or len(nome) < 5 or len(nome) > 50:
        return False
    palavras = nome.split()
    if len(palavras) < 2 or len(palavras) > 5:
        return False
    # Cada palavra deve começar com maiúscula e ter >1 char
    for p in palavras:
        if len(p) < 2:
            return False
        if not p[0].isupper():
            return False
    # Rejeita se tem palavras que não são nomes
    lixo = ['home', 'page', 'menu', 'site', 'click', 'ver', 'mais', 'nosso', 'nossa',
            'contato', 'sobre', 'aqui', 'whatsapp', 'email', 'telefone', 'rodovia',
            'ltda', 'eireli', 'unidade', 'grãos', 'grão', 'soja', 'milho',
            'cooperativa', 'armazém', 'armazem', 'silo', 'agro', 'top', 'footer',
            'header', 'nav', 'link', 'button', 'endereço', 'rua', 'avenida']
    for p in palavras:
        if p.lower() in lixo:
            return False
    return True


def _cargo_valido(cargo):
    """Verifica se parece um cargo real (curto, com palavra-chave de cargo)."""
    if not cargo or len(cargo) < 5 or len(cargo) > 60:
        return False
    low = cargo.lower()
    # Deve conter pelo menos uma palavra-chave de cargo
    cargo_palavras = ['diretor', 'gerente', 'coordenador', 'supervisor', 'responsável',
                      'presidente', 'sócio', 'socio', 'proprietário', 'proprietario',
                      'CEO', 'head', 'manager', 'director', 'compras', 'comercial',
                      'operações', 'operacoes', 'logística', 'logistica', 'financeiro',
                      'administrativo', 'recebimento', 'produção', 'producao']
    if not any(kw in low for kw in cargo_palavras):
        return False
    # Rejeita se muito longo ou com lixo
    if any(x in low for x in ['http', 'www', 'click', '.com', 'whatsapp', 'ver mais', 'saiba']):
        return False
    return True


def _extrair_decisores(html):
    """Extrai nomes e cargos de possíveis decisores do HTML."""
    decisores = []
    # Remove tags script/style/nav
    limpo = re.sub(r'<(script|style|nav|header|footer)[^>]*>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)
    # Remove tags HTML mas preserva separação
    texto = re.sub(r'<[^>]+>', ' | ', limpo)
    texto = re.sub(r'\s+', ' ', texto)

    # Padrão: Nome Sobrenome - Cargo (ex: "João Silva - Diretor Comercial")
    _NOME = r'([A-ZÀ-Ú][a-zà-ú]+(?:\s+(?:de|da|do|dos|das|e)?\s*[A-ZÀ-Ú][a-zà-ú]+){1,3})'
    _CARGO = r'([A-ZÀ-Úa-zà-ú][^|]{4,55})'

    # "Nome - Cargo"
    for m in re.finditer(_NOME + r'\s*[-–|/]\s*' + _CARGO, texto):
        nome = m.group(1).strip()
        cargo = m.group(2).strip()
        if _nome_valido(nome) and _cargo_valido(cargo):
            decisores.append({'nome': nome, 'cargo': cargo})

    # "Cargo: Nome" ou "Cargo - Nome"
    for m in re.finditer(_CARGO + r'\s*[-–:|]\s*' + _NOME, texto):
        cargo = m.group(1).strip()
        nome = m.group(2).strip()
        if _nome_valido(nome) and _cargo_valido(cargo):
            decisores.append({'nome': nome, 'cargo': cargo})

    # Deduplica por nome
    vistos = set()
    unicos = []
    for d in decisores:
        if d['nome'] not in vistos:
            vistos.add(d['nome'])
            unicos.append(d)
    return unicos[:3]


async def _scrape_site(url: str) -> dict:
    """Acessa o site e extrai telefone, email, CNPJ e decisores."""
    resultado = {'telefones': [], 'emails': [], 'cnpj': None, 'decisores': []}
    if not url:
        return resultado

    base = url.rstrip('/')
    if not base.startswith('http'):
        base = 'https://' + base
    from urllib.parse import urlparse
    parsed = urlparse(base)
    raiz = f'{parsed.scheme}://{parsed.netloc}'

    timeout = aiohttp.ClientTimeout(total=8)
    todo_html = ''
    paginas_ok = 0

    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=_HEADERS) as sess:
            # Fase 1: percorre páginas padrão
            for path in _CONTATO_PATHS:
                try:
                    target = raiz + path
                    async with sess.get(target, ssl=False, allow_redirects=True) as resp:
                        if resp.status != 200:
                            continue
                        html = await resp.text(errors='replace')
                        paginas_ok += 1
                        todo_html += ' ' + html

                        # Extrai mailto: e tel: do HTML (mais confiável que regex no texto)
                        mt_emails, mt_tels = _extrair_mailto_tel(html)
                        for e in mt_emails:
                            if e not in resultado['emails']:
                                resultado['emails'].append(e)
                        for t in mt_tels:
                            if t not in resultado['telefones']:
                                resultado['telefones'].append(t)

                        # Extrai emails do texto
                        for e in _extrair_emails(html):
                            if _email_valido(e) and e not in resultado['emails']:
                                resultado['emails'].append(e)
                        # Extrai telefones do texto
                        for t in _extrair_telefones_texto(html):
                            if t not in resultado['telefones']:
                                resultado['telefones'].append(t)
                        # CNPJ
                        if not resultado['cnpj']:
                            resultado['cnpj'] = _extrair_cnpj(html)

                        # Se já tem tudo, para de buscar páginas padrão
                        if resultado['emails'] and resultado['telefones']:
                            break
                except Exception:
                    continue

            # Fase 2: segue links internos de contato se ainda falta dado
            if not resultado['emails'] or not resultado['telefones']:
                links = re.findall(
                    r'href=["\']([^"\']*(?:contato|contact|fale|whatsapp|telefone|equipe|diretoria|time)[^"\']*)["\']',
                    todo_html, re.IGNORECASE
                )
                # Também pega links com "email" ou "atendimento"
                links += re.findall(
                    r'href=["\']([^"\']*(?:email|atendimento|ouvidoria|sac)[^"\']*)["\']',
                    todo_html, re.IGNORECASE
                )
                urls_vistas = set()
                for href in links[:3]:
                    try:
                        if href.startswith('mailto:') or href.startswith('tel:') or href.startswith('#'):
                            continue
                        if href.startswith('/'):
                            href = raiz + href
                        elif not href.startswith('http'):
                            continue
                        if href in urls_vistas:
                            continue
                        urls_vistas.add(href)
                        async with sess.get(href, ssl=False, allow_redirects=True) as resp:
                            if resp.status != 200:
                                continue
                            html = await resp.text(errors='replace')
                            todo_html += ' ' + html
                            mt_emails, mt_tels = _extrair_mailto_tel(html)
                            for e in mt_emails:
                                if e not in resultado['emails']:
                                    resultado['emails'].append(e)
                            for t in mt_tels:
                                if t not in resultado['telefones']:
                                    resultado['telefones'].append(t)
                            for e in _extrair_emails(html):
                                if _email_valido(e) and e not in resultado['emails']:
                                    resultado['emails'].append(e)
                            for t in _extrair_telefones_texto(html):
                                if t not in resultado['telefones']:
                                    resultado['telefones'].append(t)
                            if not resultado['cnpj']:
                                resultado['cnpj'] = _extrair_cnpj(html)
                    except Exception:
                        continue

            # Fase 3: extrai decisores do HTML acumulado
            resultado['decisores'] = _extrair_decisores(todo_html)

    except Exception:
        pass
    return resultado


def _resultado_para_empresa(r):
    """Converte resultado do buscador para formato de empresa."""
    titulo = r.get('titulo', '')
    snippet = r.get('snippet', '')
    dominio = r.get('dominio', '')
    telefones = r.get('telefones', [])
    url = r.get('url', '')
    texto_completo = titulo + ' ' + snippet

    # Extrair nome da empresa do título (remove sufixos comuns)
    nome = re.sub(
        r'\s*[-–|]\s*(Fone|Tel|Contato|Home|Página|Site).*$', '',
        titulo, flags=re.IGNORECASE
    ).strip()
    if len(nome) > 100:
        nome = nome[:100]
    if not nome or len(nome) < 3:
        nome = dominio.replace('www.', '').split('.')[0].title()

    # Extrair emails do snippet
    emails = _extrair_emails(texto_completo)
    email = emails[0] if emails else None

    # Extrair telefones do snippet também (buscador nem sempre pega)
    if not telefones:
        telefones = _extrair_telefones_texto(texto_completo)

    # Telefone principal
    telefone = telefones[0] if telefones else None

    # WhatsApp: telefones com 9 dígitos no número local
    whatsapp = None
    for t in telefones:
        digitos = re.sub(r'\D', '', str(t))
        # Celular tem 11 dígitos (DDD + 9xxxx-xxxx)
        if len(digitos) == 11 and digitos[2] == '9':
            whatsapp = '55' + digitos
            break

    # Extrair cidade/estado do snippet
    estado = None
    cidade = None
    estados_map = {
        'SP': 'São Paulo', 'RJ': 'Rio de Janeiro', 'MG': 'Minas Gerais',
        'RS': 'Rio Grande do Sul', 'PR': 'Paraná', 'SC': 'Santa Catarina',
        'BA': 'Bahia', 'GO': 'Goiás', 'MT': 'Mato Grosso',
        'MS': 'Mato Grosso do Sul', 'PE': 'Pernambuco', 'CE': 'Ceará',
        'PA': 'Pará', 'MA': 'Maranhão', 'ES': 'Espírito Santo',
        'TO': 'Tocantins', 'PI': 'Piauí', 'RN': 'Rio Grande do Norte',
    }
    for uf, nome_estado in estados_map.items():
        if f' {uf} ' in texto_completo or f' {uf},' in texto_completo:
            estado = uf
            break
        if nome_estado.lower() in texto_completo.lower():
            estado = uf
            break

    # Usa domínio como website (não URL completa) para evitar duplicatas da mesma empresa
    site = dominio if dominio else url
    if site:
        site = re.sub(r'^https?://', '', site).rstrip('/')
        # Remove www.
        site = re.sub(r'^www\.', '', site)

    # Extrai CNPJ do snippet
    cnpj = _extrair_cnpj(texto_completo)

    return {
        'nome_fantasia': nome,
        'cnpj': cnpj,
        'website': site,
        'telefone': telefone,
        'whatsapp': whatsapp,
        'email': email,
        'cidade': cidade,
        'estado': estado,
        'fonte': r.get('fonte', 'web'),
        'score': r.get('relevancia', 0),
        'segmento': '',
    }


async def ciclo_busca(schema: str, buscador: Buscador, termos: list,
                      palavras_concorrente: list = None) -> int:
    """Um ciclo de busca. Retorna qtd de leads salvos."""
    # Sem limite diário — roda direto

    termo = random.choice(termos)
    print(f'[{schema}] 🔍 Buscando: "{termo}"', flush=True)
    log_db(schema, 'info', f'Busca: {termo}')

    try:
        resultados = await buscador.buscar_leads(termo)
    except Exception as e:
        print(f'[{schema}] Erro na busca: {e}', flush=True)
        return 0

    salvos = 0
    for r in resultados:
        lead = _resultado_para_empresa(r)
        if not lead.get('website'):
            continue

        # Filtra blogs, portais e sites não-empresariais
        dominio = lead['website'].lower()
        dominio_limpo = re.sub(r'^www\.', '', dominio)
        is_blacklisted = False
        for bl in _DOMINIOS_BLACKLIST:
            if dominio_limpo == bl or dominio_limpo.endswith('.' + bl):
                is_blacklisted = True
                break
        if not is_blacklisted:
            for pat in _DOMINIO_PATTERNS_SKIP:
                if pat in dominio_limpo:
                    is_blacklisted = True
                    break
        if is_blacklisted:
            print(f'[{schema}]   ✗ Skip (blog/portal): {dominio}',
                  flush=True)
            continue

        # Filtra concorrentes (empresas que VENDEM o mesmo serviço)
        # Baseado na descrição do produto do user
        if palavras_concorrente:
            titulo_lower = r.get('titulo', '').lower()
            snippet_lower = r.get('snippet', '').lower()
            texto_result = titulo_lower + ' ' + snippet_lower
            matches = sum(1 for p in palavras_concorrente
                          if p in texto_result)
            # Se 3+ palavras-chave do produto batem, é concorrente
            if matches >= 3:
                print(f'[{schema}]   ✗ Skip (concorrente): '
                      f'{lead.get("nome_fantasia", dominio)}',
                      flush=True)
                continue

        # SEMPRE scrapa o site para buscar telefone, email, CNPJ e decisores
        url_scrape = r.get('url', lead.get('website', ''))
        decisores = []
        try:
            contatos = await asyncio.wait_for(_scrape_site(url_scrape), timeout=25)
            # Email
            if contatos['emails']:
                if not lead.get('email'):
                    lead['email'] = contatos['emails'][0]
            # Telefone
            if contatos['telefones']:
                if not lead.get('telefone'):
                    lead['telefone'] = contatos['telefones'][0]
                if len(contatos['telefones']) > 1 and not lead.get('telefone2'):
                    lead['telefone2'] = contatos['telefones'][1]
                # WhatsApp (celular)
                if not lead.get('whatsapp'):
                    for t in contatos['telefones']:
                        digitos = re.sub(r'\D', '', t)
                        if len(digitos) == 11 and digitos[2] == '9':
                            lead['whatsapp'] = '55' + digitos
                            break
                        # wa.me com 55 na frente
                        if len(digitos) == 13 and digitos[:2] == '55' and digitos[4] == '9':
                            lead['whatsapp'] = digitos
                            break
            # CNPJ
            if contatos['cnpj'] and not lead.get('cnpj'):
                lead['cnpj'] = contatos['cnpj']
            # Decisores
            decisores = contatos.get('decisores', [])

            n_tel = len(contatos['telefones'])
            n_email = len(contatos['emails'])
            extras = []
            if contatos['cnpj']:
                extras.append('CNPJ')
            if decisores:
                extras.append(f'{len(decisores)} decisor(es)')
            extra_str = (' | ' + ', '.join(extras)) if extras else ''
            print(f'[{schema}]   🔎 {lead["website"]}: {n_tel} tel, {n_email} email{extra_str}', flush=True)
        except asyncio.TimeoutError:
            print(f'[{schema}]   ⚠ Timeout scrape {lead["website"]} (>25s)', flush=True)
            contatos = {'telefones': [], 'emails': [], 'cnpj': None, 'decisores': []}
        except Exception as e:
            print(f'[{schema}]   ⚠ Erro scrape {lead["website"]}: {e}', flush=True)

        # EXIGE telefone E email — sem os dois não serve
        if not lead.get('telefone') or not lead.get('email'):
            falta = []
            if not lead.get('telefone'):
                falta.append('tel')
            if not lead.get('email'):
                falta.append('email')
            print(f'[{schema}]   ✗ Descartado (sem {"+".join(falta)}): {lead.get("nome_fantasia", "")}', flush=True)
            continue

        empresa_id = salvar_empresa(schema, lead)
        if empresa_id:
            salvos += 1
            nome = lead.get('nome_fantasia') or lead.get('website') or 'Lead'
            score = lead.get('score', 0)
            partes = ['TEL', 'EMAIL']
            if lead.get('whatsapp'):
                partes.append('WA')
            if lead.get('cnpj'):
                partes.append('CNPJ')
            tag = '+'.join(partes)
            print(f'[{schema}] ✓ [{tag}] score={score} | {nome} | {lead["email"]}', flush=True)

            # Salva decisores como contatos da empresa
            if decisores and empresa_id:
                try:
                    conn = _conn(schema)
                    c = conn.cursor()
                    for dec in decisores:
                        # Verifica se já existe
                        c.execute("SELECT id FROM contatos WHERE empresa_id=%s AND nome=%s",
                                  (empresa_id, dec['nome']))
                        if not c.fetchone():
                            c.execute("INSERT INTO contatos (empresa_id, nome, cargo, decisor) VALUES (%s,%s,%s,1)",
                                      (empresa_id, dec['nome'], dec['cargo']))
                    conn.commit()
                    conn.close()
                    for dec in decisores:
                        print(f'[{schema}]     👤 {dec["nome"]} — {dec["cargo"]}', flush=True)
                except Exception:
                    pass

    incrementar(schema, 'buscas')

    # Registra busca
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute("INSERT INTO buscas (termo, fonte, resultados) VALUES (%s,'web',%s)",
                  (termo, len(resultados)))
        conn.commit()
        conn.close()
    except Exception:
        pass

    print(f'[{schema}] ✓ {len(resultados)} sites → {salvos} lead(s) salvos', flush=True)
    return salvos


async def main_loop(schema: str):
    print(f'\n{"="*60}', flush=True)
    print(f'[MáquinaVendas] Iniciando bot de busca — schema: {schema}', flush=True)
    print(f'{"="*60}\n', flush=True)

    buscador = Buscador()
    try:
        await buscador.iniciar()
    except Exception as e:
        print(f'[{schema}] Erro ao iniciar navegador: {e}', flush=True)
        print(f'[{schema}] Tentando modo HTTP...', flush=True)

    # Carrega descrição do produto para filtrar concorrentes
    descricao = get_descricao_empresa(schema)
    palavras_conc = _gerar_palavras_concorrente(descricao)
    if palavras_conc:
        print(f'[{schema}] Filtro concorrentes: {len(palavras_conc)} palavras-chave do produto', flush=True)

    ciclo = 0
    while True:
        ciclo += 1
        termos = get_termos(schema)
        if not termos:
            print(f'[{schema}] Nenhum termo configurado. Configure em /configurar', flush=True)
            await asyncio.sleep(60)
            continue

        print(f'\n[{schema}] ━━━ Ciclo #{ciclo} | buscas hoje: {get_contagem_diaria(schema, "buscas")} ━━━', flush=True)

        try:
            salvos = await ciclo_busca(schema, buscador, termos, palavras_conc)
        except Exception as e:
            print(f'[{schema}] Erro no ciclo: {e}', flush=True)
            log_db(schema, 'erro', str(e))
            salvos = 0

        # Delay mínimo anti-bloqueio (3-5s) — evita rate-limit dos motores
        await asyncio.sleep(random.uniform(3, 5))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--schema', required=True, help='Schema do usuário (ex: emp_1)')
    args = parser.parse_args()

    if not DATABASE_URL:
        print('ERRO: DATABASE_URL não configurado', flush=True)
        sys.exit(1)

    asyncio.run(main_loop(args.schema))
