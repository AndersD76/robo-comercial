# -*- coding: utf-8 -*-
"""
TurboVenda — Bot de Busca
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
    # Grandes corporações (aparecem nas páginas altas do Google)
    'bb.com.br', 'itau.com.br', 'bradesco.com.br', 'santander.com.br',
    'caixa.gov.br', 'bndes.gov.br', 'vivo.com.br', 'claro.com.br',
    'tim.com.br', 'oi.com.br', 'citroen.com.br', 'ford.com.br',
    'chevrolet.com.br', 'toyota.com.br', 'honda.com.br', 'fiat.com.br',
    'volkswagen.com.br', 'ambev.com.br', 'nestle.com.br', 'unilever.com.br',
    'coca-cola.com.br', 'pepsi.com.br', 'heineken.com', 'careers.theheinekencompany.com',
    'chiquinho.com.br', 'supergasbras.com.br', 'shell.com.br', 'petrobras.com.br',
    'natura.com.br', 'boticario.com.br', 'renner.com.br', 'riachuelo.com.br',
    'americanas.com.br', 'casasbahia.com.br', 'pernambucanas.com.br',
    'carrefour.com.br', 'paodeacucar.com', 'extra.com.br',
    'sympla.com.br', 'solutudo.com.br', 'ohub.com.br',
    'econodata.com.br', 'empresas.serasaexperian.com.br', 'cnpj.biz',
    'empresaqui.com.br', 'cronoshare.com.br',
    'manychat.com', 'descomplica.com.br', 'sereducacional.com',
    'escoteiros.org.br', 'espro.org.br', 'komatsu.com.br',
    'prefeitura.rio', '1746.rio', 'light.com.br',
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


def load_serper_key(schema: str):
    """Lê serper_api_key do bot_config e seta como env var."""
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute("SELECT serper_api_key FROM bot_config ORDER BY id DESC LIMIT 1")
        row = c.fetchone()
        conn.close()
        key = row.get('serper_api_key') if row else None
        if key:
            os.environ['SERPER_API_KEY'] = key
            return True
    except Exception:
        pass
    return False


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


def get_estados_atuacao(schema: str) -> list:
    """UFs que o cliente marcou. Vazio = Brasil todo."""
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute('SELECT estados_atuacao FROM bot_config '
                  'ORDER BY id DESC LIMIT 1')
        row = c.fetchone()
        conn.close()
        if row and row['estados_atuacao']:
            ufs = row['estados_atuacao']
            if isinstance(ufs, str):
                ufs = json.loads(ufs)
            return [str(u).upper().strip() for u in ufs if str(u).strip()]
    except Exception as e:
        print(f'[run_busca] erro ao ler estados_atuacao: {e}', flush=True)
    return []


def _tel_canonico(valor):
    """Mesmo formato que a ingestao grava: (DD) NNNNNNNN."""
    d = re.sub(r'\D', '', str(valor or ''))
    if d.startswith('55') and len(d) > 11:
        d = d[2:]
    if len(d) == 11 and d[2] == '9':      # celular: a base costuma ter 8
        return [f'({d[:2]}) {d[2:]}', f'({d[:2]}) {d[3:]}']
    if len(d) in (10, 11):
        return [f'({d[:2]}) {d[2:]}']
    return []


# Palavras que nao identificam empresa nenhuma: termo societario, generico
# de ramo, e o lixo de titulo de pagina ("Termos de Uso", "Fale Conosco").
_PALAVRAS_VAZIAS = (
    'ltda', 'epp', 'eireli', 'mei', 'cia', 'sociedade', 'individual',
    'associacao', 'servicos', 'servico', 'comercio', 'industria',
    'transportes', 'consultoria', 'assessoria', 'empresa', 'empresas',
    'grupo', 'centro', 'brasil', 'brasileira', 'nacional',
    'termos', 'termo', 'privacidade', 'politica', 'home', 'inicial',
    'inicio', 'contato', 'contatos', 'fale', 'conosco', 'quem', 'somos',
    'sobre', 'institucional', 'produtos', 'solucoes', 'blog', 'noticias',
    'trabalhe', 'localizacao', 'cookies', 'login', 'orcamento',
    'atendimento', 'pagina', 'site', 'oficial', 'bem', 'vindo',
)


def _tokens_nome(valor):
    """Palavras significativas do nome, sem acento nem termo societario."""
    t = _sem_acento(str(valor or '')).lower()
    t = re.sub(r'&[a-z]+;', ' ', t)          # &gt; e afins vindos do HTML
    t = re.sub(r'[^a-z0-9 ]', ' ', t)
    return {p for p in t.split()
            if len(p) >= 4 and p not in _PALAVRAS_VAZIAS}


def _nome_confere(nome_web, oficial):
    """O nome oficial tem a ver com o que a web trouxe?

    O telefone acha o candidato, mas sozinho ja colocou
    "Signo Assessoria Contabil" como "Trma Manutencao". Exigir uma palavra
    significativa em comum barra esse tipo de troca. Quando o nome da web
    e so lixo ("Termos de Uso"), nao ha o que conferir e aceitamos — e
    justamente o caso em que mais precisamos do dado oficial.
    """
    web = _tokens_nome(nome_web)
    if not web:
        return True
    alvo = _tokens_nome(oficial.get('razao_social')) | \
        _tokens_nome(oficial.get('nome_fantasia'))
    if not alvo:
        return True
    if web & alvo:
        return True
    # "AndersTech" x "ANDERS CONSULTORIA": uma comeca com a outra
    return any(a.startswith(w) or w.startswith(a)
               for w in web for a in alvo if min(len(w), len(a)) >= 5)


def validar_na_receita(lead):
    """Cruza o lead achado na web com a base da Receita.

    A web descobre a empresa, mas o nome vem do titulo da pagina e o CNPJ
    pode ser qualquer numero no rodape. Aqui trocamos isso por dado
    oficial: razao social, CNPJ valido, UF, municipio e CNAE.

    Casa por CNPJ, senao por telefone (chave bem mais confiavel que nome).
    Devolve dict com o que achou, ou {} se nao identificou.
    """
    try:
        conn = psycopg2.connect(
            DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    except Exception as e:
        print(f'[receita] sem conexao: {e}', flush=True)
        return {}
    try:
        c = conn.cursor()
        row = None

        cnpj_d = re.sub(r'\D', '', lead.get('cnpj') or '')
        if len(cnpj_d) == 14:
            c.execute('SELECT * FROM public.empresas_publicas '
                      'WHERE cnpj_basico = %s', (cnpj_d[:8],))
            row = c.fetchone()

        if not row:
            variantes = []
            for campo in ('telefone', 'whatsapp'):
                variantes.extend(_tel_canonico(lead.get(campo)))
            if variantes:
                # Busca DUAS: 23% dos telefones da Receita sao de contador
                # ou despachante e aparecem em varias empresas (um deles em
                # 8.783). Nesse caso o numero nao identifica ninguem, e
                # aceitar a primeira sobrescreveria um lead bom com dado de
                # outra empresa. So vale quando o telefone e unico.
                c.execute(
                    'SELECT * FROM public.empresas_publicas '
                    'WHERE telefone = ANY(%s) OR telefone2 = ANY(%s) '
                    'LIMIT 2', (variantes, variantes))
                achados = c.fetchall()
                if len(achados) == 1:
                    cand = dict(achados[0])
                    if _nome_confere(lead.get('nome_fantasia'), cand):
                        row = cand
                    else:
                        print('[receita] nome nao confere, ignorando: '
                              f'{lead.get("nome_fantasia")} x '
                              f'{cand.get("razao_social")}', flush=True)
                elif len(achados) > 1:
                    print('[receita] telefone compartilhado, ignorando: '
                          f'{lead.get("nome_fantasia")}', flush=True)
        return dict(row) if row else {}
    except Exception as e:
        print(f'[receita] erro na consulta: {e}', flush=True)
        return {}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def aplicar_dados_receita(lead, oficial):
    """Sobrepoe o que veio da web com o dado oficial."""
    if not oficial:
        return lead, False
    cb = (oficial.get('cnpj_basico') or '').strip()
    if cb and len(cb) == 8 and not lead.get('cnpj'):
        # a Receita indexa por raiz; a ordem/DV ficam para o enriquecimento
        lead['cnpj_raiz'] = cb
    nome_oficial = (oficial.get('nome_fantasia')
                    or oficial.get('razao_social') or '').strip()
    if nome_oficial:
        lead['razao_social'] = (oficial.get('razao_social') or '').strip()
        # o nome da web vem do <title>; o oficial e melhor
        lead['nome_fantasia'] = nome_oficial.title()
    for origem, destino in (('uf', 'estado'), ('municipio', 'cidade')):
        v = (oficial.get(origem) or '').strip()
        if v:
            lead[destino] = v
    if oficial.get('cnae_principal'):
        lead['segmento'] = str(oficial['cnae_principal']).strip()
    # Decisor oficial: o socio-administrador vale mais que qualquer nome
    # raspado do site, porque e quem assina a compra.
    if oficial.get('socio_nome'):
        lead['decisor_nome'] = oficial['socio_nome']
        lead['decisor_cargo'] = oficial.get('socio_cargo') or 'Sócio'
    if not lead.get('email') and oficial.get('email'):
        lead['email'] = oficial['email']
    if not lead.get('telefone') and oficial.get('telefone'):
        lead['telefone'] = oficial['telefone']
    return lead, True


def get_exigir_cnpj(schema: str) -> bool:
    """Cliente pediu para so aceitar lead com CNPJ identificado."""
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute('SELECT exigir_cnpj FROM bot_config '
                  'ORDER BY id DESC LIMIT 1')
        row = c.fetchone()
        conn.close()
        return bool(row and row.get('exigir_cnpj'))
    except Exception:
        return False


def _fora_dos_estados(lead, estados):
    """True se o lead e de um estado que o cliente nao escolheu.

    So descarta quando a UF foi realmente detectada — sem UF nao da para
    provar que esta fora, e descartar mataria metade dos leads bons.
    """
    if not estados:
        return False
    uf = (lead.get('estado') or '').upper().strip()
    return bool(uf) and uf not in estados


def get_evitar(schema: str) -> list:
    """Palavras que denunciam concorrente do cliente, não lead."""
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute('SELECT segmentos_evitar FROM bot_config '
                  'ORDER BY id DESC LIMIT 1')
        row = c.fetchone()
        conn.close()
        if row and row['segmentos_evitar']:
            ev = row['segmentos_evitar']
            if isinstance(ev, str):
                ev = json.loads(ev)
            return [str(x).lower() for x in ev if str(x).strip()]
    except Exception as e:
        print(f'[run_busca] erro ao ler segmentos_evitar: {e}', flush=True)
    return []


def _e_concorrente(lead, evitar, texto_bruto=''):
    """True se o lead parece ser do mesmo ramo do cliente.

    Olha também o título/snippet originais: o nome já vem limpo, então
    "Contato Qualità - Sistema de Gestão" viraria só "Qualità" e o ramo
    se perderia.
    """
    if not evitar:
        return False
    alvo = _sem_acento(
        f"{lead.get('nome_fantasia', '')} {lead.get('website', '')} "
        f"{texto_bruto}".lower())
    return any(_sem_acento(e) in alvo for e in evitar)


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


PLAN_LEAD_LIMITS = {
    'trial': 50,
    'starter': 500,
    'pro': None,
    'enterprise': None
}


def _check_lead_limit_busca(schema: str) -> bool:
    """Retorna True se pode inserir, False se atingiu limite."""
    try:
        # Acessar public schema para pegar plano do user
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        c = conn.cursor()
        # schema = emp_N -> user_id = N
        uid = schema.replace('emp_', '')
        c.execute('SELECT plano FROM public.users WHERE id = %s', (uid,))
        row = c.fetchone()
        conn.close()
        plano = (row['plano'] if row else 'trial') or 'trial'
        limite = PLAN_LEAD_LIMITS.get(plano)
        if limite is None:
            return True
        conn2 = _conn(schema)
        c2 = conn2.cursor()
        c2.execute('SELECT COUNT(*) AS total FROM empresas')
        total = c2.fetchone()['total']
        conn2.close()
        return total < limite
    except Exception:
        return True


def salvar_empresa(schema: str, dados: dict):
    # Verificar limite do plano
    if not _check_lead_limit_busca(schema):
        print(f'[{schema}] ✗ Limite de leads atingido no plano trial', flush=True)
        return None

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
    """Extrai emails de um texto, limpando resíduo de URL (%20, mailto:)."""
    if not texto:
        return []
    from urllib.parse import unquote
    texto = unquote(texto.replace('mailto:', ' '))
    brutos = re.findall(
        r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', texto)
    limpos = []
    for e in brutos:
        # sobra de encoding/HTML grudada no começo do local-part
        e = re.sub(r'^[%\d]+(?=[a-zA-Z])', '', e)
        e = e.strip('._-%+')
        if re.fullmatch(r'[a-zA-Z0-9._+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', e):
            limpos.append(e)
    return limpos


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


def _cnpj_valido(digitos):
    """Valida os dois dígitos verificadores do CNPJ."""
    d = re.sub(r'\D', '', digitos or '')
    if len(d) != 14 or len(set(d)) == 1:
        return False
    for tamanho in (12, 13):
        pesos = list(range(tamanho - 7, 1, -1)) + list(range(9, 1, -1))
        soma = sum(int(d[i]) * pesos[i] for i in range(tamanho))
        resto = soma % 11
        esperado = 0 if resto < 2 else 11 - resto
        if int(d[tamanho]) != esperado:
            return False
    return True


def _extrair_cnpj(texto):
    """Extrai CNPJ válido de um texto. Ignora sequências inventadas."""
    if not texto:
        return None
    for m in re.finditer(r'\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}', texto):
        if _cnpj_valido(m.group()):
            return m.group()
    for m in re.finditer(r'(?<!\d)(\d{14})(?!\d)', texto):
        d = m.group()
        if _cnpj_valido(d):
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


_TITULO_JUNK = (
    'termos de uso', 'termos', 'politica de privacidade', 'privacidade',
    'home', 'homepage', 'pagina inicial', 'inicial', 'inicio', 'principal',
    'contato', 'contatos', 'fale conosco', 'quem somos', 'sobre nos',
    'sobre', 'institucional', 'a empresa', 'nossa empresa', 'empresa',
    'produtos', 'servicos', 'solucoes', 'blog', 'noticias', 'novidades',
    'trabalhe conosco', 'localizacao', 'onde estamos', 'lgpd', 'cookies',
    'area do cliente', 'login', 'orcamento', 'faq', 'duvidas', 'atendimento',
)


def _sem_acento(t):
    import unicodedata
    return ''.join(c for c in unicodedata.normalize('NFD', t or '')
                   if unicodedata.category(c) != 'Mn')


def _e_junk(t):
    return _sem_acento((t or '').strip().lower()).strip(' -–—|:.') \
        in _TITULO_JUNK


def _limpar_nome_empresa(titulo, dominio):
    """Tira 'Contato -', 'Home |' e taglines do título da página.

    O título é a única fonte de nome que temos, mas metade das páginas
    indexadas é 'Termos de Uso' ou 'Sobre nós - Fulano'. Sem isso o lead
    entra na lista chamado 'Termos de Uso'.
    """
    titulo = re.sub(r'\s+', ' ', (titulo or '')).strip()
    partes = [p.strip() for p in re.split(r'\s*[|:]\s*|\s+[-–—]\s+', titulo)
              if p.strip()]
    nome = ''
    for p in partes:
        if not _e_junk(p) and len(p) >= 3:
            nome = p
            break
    if not nome:
        # título inteiro é lixo ("Termos de Uso") — usa o domínio
        base = re.sub(r'^www\.', '', (dominio or '')).split('.')[0]
        return base.replace('-', ' ').title() if base else ''
    # "Contato Qualità" -> "Qualità"; "Grupo XYZ Home" -> "Grupo XYZ"
    for _ in range(3):
        ant = nome
        for j in _TITULO_JUNK:
            nome = re.sub(rf'^{re.escape(j)}\s+', '', nome,
                          flags=re.IGNORECASE)
            nome = re.sub(rf'\s+{re.escape(j)}$', '', nome,
                          flags=re.IGNORECASE)
        nome = nome.strip(' -–—|:,.')
        if nome == ant:
            break
    if len(nome) < 3:
        base = re.sub(r'^www\.', '', (dominio or '')).split('.')[0]
        return base.replace('-', ' ').title() if base else ''
    return nome[:100]


def _resultado_para_empresa(r):
    """Converte resultado do buscador para formato de empresa."""
    titulo = r.get('titulo', '')
    snippet = r.get('snippet', '')
    dominio = r.get('dominio', '')
    telefones = r.get('telefones', [])
    url = r.get('url', '')
    texto_completo = titulo + ' ' + snippet

    nome = _limpar_nome_empresa(titulo, dominio)

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
                      palavras_concorrente: list = None,
                      evitar: list = None, estados: list = None,
                      exigir_cnpj: bool = False) -> tuple:
    """Um ciclo de busca. Retorna (qtd_leads_salvos, termo_usado)."""

    termo = random.choice(termos)
    if not hasattr(buscador, '_termo_paginas'):
        buscador._termo_paginas = {}
    pagina = buscador._termo_paginas.get(termo, 0)
    if pagina >= 5:
        pagina = 0
        buscador._termo_paginas[termo] = 0
    buscador._termo_paginas[termo] = pagina + 1
    start = pagina * 10

    if start > 0:
        print(f'[{schema}] 🔍 Buscando: "{termo}" (página {pagina + 1})', flush=True)
    else:
        print(f'[{schema}] 🔍 Buscando: "{termo}"', flush=True)
    log_db(schema, 'info', f'Busca: {termo} (p{pagina + 1})')

    try:
        resultados = await buscador.buscar_leads(termo, start=start)
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

        # Filtro preciso: lista da IA com o ramo do próprio cliente.
        # Um match já basta — "consultoria", "certificadora" etc. nunca
        # são cliente de quem vende consultoria.
        if _e_concorrente(lead, evitar,
                          r.get('titulo', '') + ' ' + r.get('snippet', '')):
            print(f'[{schema}]   ✗ Skip (mesmo ramo do cliente): '
                  f'{lead.get("nome_fantasia", dominio)}', flush=True)
            continue

        # Antes so os termos citavam as cidades escolhidas; nada impedia o
        # buscador de devolver empresa de outro estado.
        if _fora_dos_estados(lead, estados):
            print(f'[{schema}]   ✗ Skip ({lead.get("estado")} fora dos '
                  f'estados escolhidos): '
                  f'{lead.get("nome_fantasia", dominio)}', flush=True)
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

        # Cruza com a Receita: a web descobriu a empresa, aqui o dado vira
        # oficial (razao social no lugar do titulo da pagina, CNPJ valido,
        # UF e municipio reais). Roda antes do filtro de estado para que
        # ele decida sobre a UF verdadeira, nao sobre a adivinhada.
        oficial = validar_na_receita(lead)
        lead, casou = aplicar_dados_receita(lead, oficial)
        if casou:
            print(f'[{schema}]   ✓ Receita: {lead.get("nome_fantasia")} '
                  f'({lead.get("estado")}/{lead.get("cidade")})', flush=True)

        if _fora_dos_estados(lead, estados):
            print(f'[{schema}]   ✗ Skip ({lead.get("estado")} fora dos '
                  f'estados, confirmado na Receita): '
                  f'{lead.get("nome_fantasia")}', flush=True)
            continue

        # EXIGE telefone E email — sem os dois não serve
        if (not lead.get('telefone') or not lead.get('email')
                or (exigir_cnpj and not lead.get('cnpj'))):
            falta = []
            if not lead.get('telefone'):
                falta.append('tel')
            if not lead.get('email'):
                falta.append('email')
            if exigir_cnpj and not lead.get('cnpj'):
                falta.append('CNPJ')
            print(f'[{schema}]   ✗ Descartado (sem {"+".join(falta)}): {lead.get("nome_fantasia", "")}', flush=True)
            continue

        empresa_id = salvar_empresa(schema, lead)
        if empresa_id:
            salvos += 1
            # Socio da Receita entra como decisor: e quem assina a compra,
            # e vale mais que qualquer nome raspado da pagina "Equipe".
            if lead.get('decisor_nome'):
                try:
                    _c = _conn(schema)
                    _k = _c.cursor()
                    _k.execute(
                        'SELECT 1 FROM contatos WHERE empresa_id=%s '
                        'AND decisor=1 LIMIT 1', (empresa_id,))
                    if not _k.fetchone():
                        _k.execute(
                            'INSERT INTO contatos (empresa_id, nome, cargo, '
                            'decisor, fonte) VALUES (%s,%s,%s,1,%s)',
                            (empresa_id, lead['decisor_nome'],
                             lead.get('decisor_cargo') or 'Sócio', 'receita'))
                        _c.commit()
                        print(f'[{schema}]     👤 {lead["decisor_nome"]} — '
                              f'{lead.get("decisor_cargo")} (Receita)',
                              flush=True)
                    _c.close()
                except Exception as e:
                    print(f'[{schema}]     ⚠ decisor: {e}', flush=True)
            nome = lead.get('nome_fantasia') or lead.get('website') or 'Lead'
            score = lead.get('score', 0)
            partes = ['TEL', 'EMAIL']
            if lead.get('whatsapp'):
                partes.append('WA')
            if lead.get('cnpj'):
                partes.append('CNPJ')
            tag = '+'.join(partes)
            print(f'[{schema}] ✓ [{tag}] score={score} | {nome} | {lead["email"]}', flush=True)
            # Auto-enriquecer CNPJ
            if lead.get('cnpj'):
                try:
                    cnpj_d = ''.join(
                        ch for ch in lead['cnpj'] if ch.isdigit())
                    if len(cnpj_d) == 14:
                        async with aiohttp.ClientSession() as s:
                            async with s.get(
                                f'https://brasilapi.com.br/api/cnpj/v1/{cnpj_d}',
                                timeout=aiohttp.ClientTimeout(total=8)
                            ) as resp:
                                if resp.status == 200:
                                    d = await resp.json()
                                    conn_e = _conn(schema)
                                    ce = conn_e.cursor()
                                    ce.execute("""UPDATE empresas SET
                                        razao_social = COALESCE(
                                            NULLIF(razao_social,''), %s),
                                        porte = %s,
                                        cidade = COALESCE(
                                            NULLIF(cidade,''), %s),
                                        estado = COALESCE(
                                            NULLIF(estado,''), %s),
                                        enriquecido = TRUE,
                                        enriquecido_em = NOW()
                                        WHERE id = %s""",
                                        (d.get('razao_social', ''),
                                         d.get('porte', ''),
                                         d.get('municipio', ''),
                                         d.get('uf', ''),
                                         empresa_id))
                                    conn_e.commit()
                                    conn_e.close()
                except Exception:
                    pass
        else:
            print(f'[{schema}]   ↩ Duplicado: {lead.get("website", "?")}', flush=True)

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
    return salvos, termo


async def main_loop(schema: str):
    print(f'\n{"="*60}', flush=True)
    print(f'[TurboVenda] Iniciando bot de busca — schema: {schema}', flush=True)
    print(f'{"="*60}\n', flush=True)

    buscador = Buscador()
    try:
        await buscador.iniciar()
    except Exception as e:
        print(f'[{schema}] Erro ao iniciar navegador: {e}', flush=True)
        print(f'[{schema}] Tentando modo HTTP...', flush=True)

    # Carrega Serper API key do banco
    if load_serper_key(schema):
        print(f'[{schema}] Serper.dev API configurada',
              flush=True)

    # Carrega descrição do produto para filtrar concorrentes
    descricao = get_descricao_empresa(schema)
    palavras_conc = _gerar_palavras_concorrente(descricao)
    if palavras_conc:
        print(f'[{schema}] Filtro concorrentes: {len(palavras_conc)} palavras-chave do produto', flush=True)
    estados_ok = get_estados_atuacao(schema)
    if estados_ok:
        print(f'[{schema}] Estados escolhidos: {", ".join(estados_ok)}',
              flush=True)
    exigir_cnpj = get_exigir_cnpj(schema)
    if exigir_cnpj:
        print(f'[{schema}] So aceita lead com CNPJ identificado', flush=True)
    evitar = get_evitar(schema)
    if evitar:
        print(f'[{schema}] Ramo do cliente (nao prospectar): '
              f'{", ".join(evitar)}', flush=True)

    ciclo = 0
    # Rastreia páginas já buscadas por termo: {termo: página_atual}
    termo_pagina = {}
    # Termos esgotados (3 páginas sem novos leads)
    termos_esgotados = set()
    # Rodadas sem novos leads por termo
    termo_sem_novos = {}

    while True:
        ciclo += 1
        termos = get_termos(schema)
        if not termos:
            print(f'[{schema}] Nenhum termo configurado. Configure em /configurar', flush=True)
            await asyncio.sleep(60)
            continue

        # Filtra termos não esgotados
        termos_ativos = [t for t in termos if t not in termos_esgotados]
        if not termos_ativos:
            # Todos esgotados — reseta e tenta de novo (novos resultados podem aparecer)
            print(f'[{schema}] Todos os {len(termos)} termos esgotados. Resetando...', flush=True)
            termos_esgotados.clear()
            termo_pagina.clear()
            termo_sem_novos.clear()
            termos_ativos = termos

        # Verificar limite de leads antes de gastar buscas
        if not _check_lead_limit_busca(schema):
            print(f'[{schema}] ⚠ Limite de leads do plano atingido. Robô pausado. Faça upgrade para continuar.', flush=True)
            log_db(schema, 'limite', 'Limite de leads do plano atingido')
            await asyncio.sleep(300)  # Espera 5min e verifica de novo
            continue

        print(f'\n[{schema}] ━━━ Ciclo #{ciclo} | buscas hoje: {get_contagem_diaria(schema, "buscas")} | termos ativos: {len(termos_ativos)}/{len(termos)} ━━━', flush=True)

        termo_usado = None
        try:
            resultado = await ciclo_busca(schema, buscador, termos_ativos,
                                          palavras_conc, evitar, estados_ok,
                                          exigir_cnpj)
            if isinstance(resultado, tuple):
                salvos, termo_usado = resultado
            else:
                salvos = resultado
        except Exception as e:
            print(f'[{schema}] Erro no ciclo: {e}', flush=True)
            log_db(schema, 'erro', str(e))
            salvos = 0

        if salvos == 0 and termo_usado:
            termo_sem_novos[termo_usado] = termo_sem_novos.get(termo_usado, 0) + 1
            if termo_sem_novos[termo_usado] >= 5:
                termos_esgotados.add(termo_usado)
                print(f'[{schema}]   ⏭ Termo esgotado: "{termo_usado[:50]}"', flush=True)
        elif salvos > 0 and termo_usado:
            termo_sem_novos.pop(termo_usado, None)

        # Processar sequências de email pendentes (a cada 10 ciclos)
        if ciclo % 10 == 0:
            try:
                conn_seq = _conn(schema)
                cs = conn_seq.cursor()
                cs.execute("""SELECT COUNT(*) AS n
                    FROM sequencia_leads
                    WHERE status = 'ativo'
                    AND proximo_envio <= NOW()""")
                pend = cs.fetchone()['n']
                conn_seq.close()
                if pend > 0:
                    import requests as http_req
                    port = os.environ.get('PORT', '5000')
                    http_req.post(
                        f'http://localhost:{port}'
                        f'/api/{schema}/sequencias/processar',
                        timeout=30)
                    print(f'[{schema}] Sequencias: {pend} pendente(s) processadas', flush=True)
            except Exception:
                pass

        # Delay adaptativo — mais lento quando sem resultados novos
        total_esgotados = len(termos_esgotados)
        total_termos = len(termos)
        if total_esgotados > total_termos * 0.8:
            delay = random.uniform(120, 180)
        elif total_esgotados > total_termos * 0.5:
            delay = random.uniform(60, 90)
        else:
            delay = random.uniform(20, 40)
        await asyncio.sleep(delay)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--schema', required=True, help='Schema do usuário (ex: emp_1)')
    args = parser.parse_args()

    if not DATABASE_URL:
        print('ERRO: DATABASE_URL não configurado', flush=True)
        sys.exit(1)

    asyncio.run(main_loop(args.schema))
