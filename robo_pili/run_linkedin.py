# -*- coding: utf-8 -*-
"""
Máquina de Vendas — Bot LinkedIn
Prospecta decisores no LinkedIn baseado na config do usuário.
Uso: python run_linkedin.py --schema emp_1
"""

import argparse
import asyncio
import json
import os
import sys

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from linkedin_bot import LinkedInBot  # noqa: E402


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


def get_linkedin_config(schema: str) -> dict:
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute("SELECT linkedin_email, linkedin_password, linkedin_cargos FROM bot_config LIMIT 1")
        row = c.fetchone()
        conn.close()
        if row:
            cargos = row['linkedin_cargos']
            if isinstance(cargos, str):
                cargos = json.loads(cargos)
            return {
                'email': row['linkedin_email'] or '',
                'password': row['linkedin_password'] or '',
                'cargos': cargos or []
            }
    except Exception as e:
        print(f'[linkedin] erro config: {e}', flush=True)
    return {}


def log_db(schema: str, tipo: str, mensagem: str):
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute("INSERT INTO logs (tipo, mensagem) VALUES (%s, %s)", (tipo, mensagem))
        conn.commit()
        conn.close()
    except Exception:
        pass


async def main_loop(schema: str):
    print(f'\n{"="*60}', flush=True)
    print(f'[LinkedIn] Iniciando bot LinkedIn — schema: {schema}', flush=True)
    print(f'{"="*60}\n', flush=True)

    cfg = get_linkedin_config(schema)
    if not cfg.get('email') or not cfg.get('password'):
        print('[LinkedIn] ERRO: Credenciais LinkedIn não configuradas. Acesse /configurar', flush=True)
        return

    if not cfg.get('cargos'):
        print('[LinkedIn] AVISO: Nenhum cargo-alvo configurado. Usando padrão.', flush=True)
        cfg['cargos'] = ['gerente de compras', 'diretor comercial', 'CEO', 'sócio proprietário']

    # Cria arquivo de credenciais temporário para o linkedin_bot.py
    creds_path = os.path.join(os.path.dirname(__file__), 'linkedin_creds.json')
    with open(creds_path, 'w', encoding='utf-8') as f:
        json.dump({'email': cfg['email'], 'password': cfg['password']}, f)

    # Patch: sobrescreve LINKEDIN_CARGOS_ALVO com os cargos do usuário
    import config as _cfg
    _cfg.LINKEDIN_CARGOS_ALVO = cfg['cargos']
    _cfg.LINKEDIN_TERMOS_BUSCA = [f'{c} site:linkedin.com/in' for c in cfg['cargos'][:5]]

    try:
        bot = LinkedInBot(schema=schema)
        await bot.run()
    except Exception as e:
        print(f'[LinkedIn] Erro fatal: {e}', flush=True)
        log_db(schema, 'erro', f'LinkedIn: {e}')
    finally:
        # Remove credenciais temporárias
        try:
            os.remove(creds_path)
        except Exception:
            pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--schema', required=True)
    args = parser.parse_args()

    if not DATABASE_URL:
        print('ERRO: DATABASE_URL não configurado', flush=True)
        sys.exit(1)

    asyncio.run(main_loop(args.schema))
