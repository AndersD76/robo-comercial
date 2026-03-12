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


def get_termos(schema: str) -> list:
    """Lê termos de busca da tabela bot_config. Fallback para config.py."""
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
    for lead in resultados:
        if not lead.get('telefone') and not lead.get('whatsapp') and not lead.get('email'):
            continue
        empresa_id = salvar_empresa(schema, lead)
        if empresa_id:
            salvos += 1
            nome = lead.get('nome_fantasia') or lead.get('website') or 'Lead'
            score = lead.get('score', 0)
            tel_tipo = 'WA' if lead.get('whatsapp') else 'TEL' if lead.get('telefone') else 'EMAIL'
            print(f'[{schema}] ✓ [{tel_tipo}] score={score} | {nome}', flush=True)

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
        await buscador.init()
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

        # Intervalo entre ciclos: 3-7 min para não sobrecarregar
        wait = random.randint(180, 420)
        print(f'[{schema}] Aguardando {wait}s até o próximo ciclo...', flush=True)
        await asyncio.sleep(wait)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--schema', required=True, help='Schema do usuário (ex: emp_1)')
    args = parser.parse_args()

    if not DATABASE_URL:
        print('ERRO: DATABASE_URL não configurado', flush=True)
        sys.exit(1)

    asyncio.run(main_loop(args.schema))
