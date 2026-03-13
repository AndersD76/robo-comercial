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

import psycopg2
import psycopg2.extras

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

    return {
        'nome_fantasia': nome,
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


async def ciclo_busca(schema: str, buscador: Buscador, termos: list) -> int:
    """Um ciclo de busca. Retorna qtd de leads salvos."""
    MAX_DIA = 120
    if get_contagem_diaria(schema, 'buscas') >= MAX_DIA:
        print(f'[{schema}] Limite diário de buscas atingido ({MAX_DIA})', flush=True)
        return 0

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
        # Salva se tem qualquer contato OU pelo menos um website/nome
        if not lead.get('telefone') and not lead.get('whatsapp') and not lead.get('email') and not lead.get('website'):
            continue
        empresa_id = salvar_empresa(schema, lead)
        if empresa_id:
            salvos += 1
            nome = lead.get('nome_fantasia') or lead.get('website') or 'Lead'
            score = lead.get('score', 0)
            if lead.get('whatsapp'):
                tag = 'WA'
            elif lead.get('telefone'):
                tag = 'TEL'
            elif lead.get('email'):
                tag = 'EMAIL'
            else:
                tag = 'WEB'
            print(f'[{schema}] ✓ [{tag}] score={score} | {nome}', flush=True)

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
            await ciclo_busca(schema, buscador, termos)
        except Exception as e:
            print(f'[{schema}] Erro no ciclo: {e}', flush=True)
            log_db(schema, 'erro', str(e))

        # Sem espera entre ciclos — direto pro próximo


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--schema', required=True, help='Schema do usuário (ex: emp_1)')
    args = parser.parse_args()

    if not DATABASE_URL:
        print('ERRO: DATABASE_URL não configurado', flush=True)
        sys.exit(1)

    asyncio.run(main_loop(args.schema))
