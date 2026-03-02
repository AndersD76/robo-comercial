# -*- coding: utf-8 -*-
"""
Robôs Comerciais — Dashboard Unificado
Prisma (PrismaBiz) + Pili (Equipamentos para Grãos)
Um único serviço Railway, uma página, dois cards.
"""

import os
import psycopg2
import psycopg2.extras
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'robo-comercial-2024')

DATABASE_URL = os.environ.get('DATABASE_URL', '')


# =============================================================================
# HELPERS DE BANCO
# =============================================================================

def get_db(schema: str):
    """Abre conexão PostgreSQL com search_path no schema indicado."""
    conn = psycopg2.connect(
        DATABASE_URL,
        cursor_factory=psycopg2.extras.RealDictCursor
    )
    with conn.cursor() as c:
        c.execute(f"SET search_path TO {schema}, public")
    conn.commit()
    return conn


def get_stats(schema: str) -> dict:
    """Retorna métricas do robô (WhatsApp + LinkedIn)."""
    zero = {
        # WhatsApp
        'total_leads': 0, 'contactadas': 0, 'responderam': 0,
        'demos': 0, 'msgs_enviadas': 0, 'respostas': 0, 'msgs_hoje': 0,
        # LinkedIn
        'li_total': 0, 'li_conexoes': 0, 'li_responderam': 0, 'li_demos': 0,
    }
    if not DATABASE_URL:
        return zero
    try:
        conn = get_db(schema)
        c = conn.cursor()

        # WhatsApp / leads gerais
        c.execute('SELECT COUNT(*) AS n FROM empresas')
        zero['total_leads'] = c.fetchone()['n']

        c.execute(
            "SELECT COUNT(*) AS n FROM empresas WHERE status = 'contactada'"
        )
        zero['contactadas'] = c.fetchone()['n']

        c.execute(
            "SELECT COUNT(*) AS n FROM empresas WHERE status = 'respondeu'"
        )
        zero['responderam'] = c.fetchone()['n']

        c.execute(
            "SELECT COUNT(*) AS n FROM empresas "
            "WHERE demo_status = 'confirmado'"
        )
        zero['demos'] = c.fetchone()['n']

        c.execute(
            "SELECT COUNT(*) AS n FROM interacoes WHERE canal = 'whatsapp'"
        )
        zero['msgs_enviadas'] = c.fetchone()['n']

        c.execute(
            "SELECT COUNT(*) AS n FROM interacoes "
            "WHERE canal = 'whatsapp' AND respondeu = 1"
        )
        zero['respostas'] = c.fetchone()['n']

        c.execute(
            "SELECT quantidade FROM acoes_diarias "
            "WHERE data = CURRENT_DATE AND tipo = 'whatsapp_enviados'"
        )
        row = c.fetchone()
        zero['msgs_hoje'] = row['quantidade'] if row else 0

        # LinkedIn
        try:
            c.execute("SELECT COUNT(*) AS n FROM leads_linkedin")
            zero['li_total'] = c.fetchone()['n']
            c.execute(
                "SELECT COUNT(*) AS n FROM leads_linkedin "
                "WHERE status = 'conexao_enviada'"
            )
            zero['li_conexoes'] = c.fetchone()['n']
            c.execute(
                "SELECT COUNT(*) AS n FROM leads_linkedin WHERE respondeu = 1"
            )
            zero['li_responderam'] = c.fetchone()['n']
            c.execute(
                "SELECT COUNT(*) AS n FROM leads_linkedin "
                "WHERE demo_status = 'confirmado'"
            )
            zero['li_demos'] = c.fetchone()['n']
        except Exception:
            pass  # tabela pode não existir ainda

        conn.close()
    except Exception as e:
        print(f"[stats/{schema}] erro: {e}")
    return zero


def get_leads(schema: str, limite: int = 30) -> list:
    if not DATABASE_URL:
        return []
    try:
        conn = get_db(schema)
        c = conn.cursor()
        c.execute(
            """SELECT nome_fantasia, whatsapp, score, status, segmento,
                      demo_status, encontrado_em
               FROM empresas
               ORDER BY score DESC, encontrado_em DESC
               LIMIT %s""",
            (limite,)
        )
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        print(f"[leads/{schema}] erro: {e}")
        return []


def get_logs(schema: str, limite: int = 20) -> list:
    if not DATABASE_URL:
        return []
    try:
        conn = get_db(schema)
        c = conn.cursor()
        c.execute(
            "SELECT tipo, mensagem, timestamp FROM logs "
            "ORDER BY timestamp DESC LIMIT %s",
            (limite,)
        )
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        print(f"[logs/{schema}] erro: {e}")
        return []


def get_linkedin(schema: str, limite: int = 30) -> list:
    if not DATABASE_URL:
        return []
    try:
        conn = get_db(schema)
        c = conn.cursor()
        c.execute(
            "SELECT nome, cargo, empresa, url_perfil, status, demo_status, "
            "encontrado_em FROM leads_linkedin "
            "ORDER BY encontrado_em DESC LIMIT %s",
            (limite,)
        )
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        print(f"[linkedin/{schema}] erro: {e}")
        return []


# =============================================================================
# ROTAS — DASHBOARD
# =============================================================================

@app.route('/')
def index():
    prisma = get_stats('prisma')
    pili = get_stats('pili')
    return render_template('index.html', prisma=prisma, pili=pili)


# --- API Prisma ---
@app.route('/api/prisma/stats')
def api_prisma_stats():
    return jsonify(get_stats('prisma'))


@app.route('/api/prisma/leads')
def api_prisma_leads():
    limite = request.args.get('limite', 30, type=int)
    return jsonify(get_leads('prisma', limite))


@app.route('/api/prisma/logs')
def api_prisma_logs():
    return jsonify(get_logs('prisma'))


@app.route('/api/prisma/linkedin')
def api_prisma_linkedin():
    limite = request.args.get('limite', 30, type=int)
    return jsonify(get_linkedin('prisma', limite))


# --- API Pili ---
@app.route('/api/pili/stats')
def api_pili_stats():
    return jsonify(get_stats('pili'))


@app.route('/api/pili/leads')
def api_pili_leads():
    limite = request.args.get('limite', 30, type=int)
    return jsonify(get_leads('pili', limite))


@app.route('/api/pili/linkedin')
def api_pili_linkedin():
    limite = request.args.get('limite', 30, type=int)
    return jsonify(get_linkedin('pili', limite))


@app.route('/api/pili/logs')
def api_pili_logs():
    return jsonify(get_logs('pili'))


# --- Pipeline CRM ---
@app.route('/api/pipeline')
def api_pipeline():
    """Retorna leads de ambos os bots organizados por estágio."""
    bot = request.args.get('bot', 'all')  # all | prisma | pili
    schemas = []
    if bot in ('all', 'prisma'):
        schemas.append('prisma')
    if bot in ('all', 'pili'):
        schemas.append('pili')

    stages = {
        'novo': [], 'contactada': [], 'respondeu': [],
        'qualificado': [], 'demo': [], 'convertido': [],
    }
    if not DATABASE_URL:
        return jsonify(stages)

    for schema in schemas:
        try:
            conn = get_db(schema)
            c = conn.cursor()
            c.execute("""
                SELECT e.id, e.nome_fantasia, e.segmento, e.score,
                       e.status, e.demo_status, e.cidade, e.estado,
                       e.whatsapp, e.encontrado_em,
                       COUNT(i.id) AS msgs,
                       MAX(i.enviado_em) AS ultima_msg
                FROM empresas e
                LEFT JOIN interacoes i ON e.id = i.empresa_id
                  AND i.canal = 'whatsapp'
                GROUP BY e.id, e.nome_fantasia, e.segmento, e.score,
                         e.status, e.demo_status, e.cidade, e.estado,
                         e.whatsapp, e.encontrado_em
                ORDER BY e.score DESC, e.encontrado_em DESC
                LIMIT 200
            """)
            rows = c.fetchall()
            conn.close()
            for r in rows:
                d = dict(r)
                d['bot'] = schema
                if d.get('demo_status') == 'confirmado':
                    stages['demo'].append(d)
                elif d.get('status') == 'convertido':
                    stages['convertido'].append(d)
                elif d.get('status') == 'qualificado':
                    stages['qualificado'].append(d)
                elif d.get('status') == 'respondeu':
                    stages['respondeu'].append(d)
                elif d.get('status') == 'contactada':
                    stages['contactada'].append(d)
                else:
                    stages['novo'].append(d)
        except Exception as e:
            print(f"[pipeline/{schema}] erro: {e}")
    return jsonify(stages)


# --- Health check ---
@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'bots': ['prisma', 'pili']})


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
