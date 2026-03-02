# -*- coding: utf-8 -*-
"""
Robô Comercial Prima — PrismaBiz
Dashboard web + controle do bot WhatsApp
Railway-ready: lê PORT do ambiente
"""

import os
import psycopg2
import psycopg2.extras
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'prima-secret-2024')

DATABASE_URL = os.environ.get('DATABASE_URL', '')
DB_SCHEMA = 'prima'


def get_db():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    with conn.cursor() as c:
        c.execute(f"SET search_path TO {DB_SCHEMA}, public")
    return conn


def get_stats():
    try:
        conn = get_db()
        c = conn.cursor()
        stats = {}

        c.execute('SELECT COUNT(*) as n FROM empresas')
        stats['total_leads'] = c.fetchone()['n']

        c.execute("SELECT COUNT(*) as n FROM empresas WHERE status = 'contactada'")
        stats['contactadas'] = c.fetchone()['n']

        c.execute("SELECT COUNT(*) as n FROM empresas WHERE status = 'respondeu'")
        stats['responderam'] = c.fetchone()['n']

        c.execute("SELECT COUNT(*) as n FROM empresas WHERE demo_status = 'confirmado'")
        stats['demos'] = c.fetchone()['n']

        c.execute("SELECT COUNT(*) as n FROM interacoes WHERE canal = 'whatsapp'")
        stats['msgs_enviadas'] = c.fetchone()['n']

        c.execute("SELECT COUNT(*) as n FROM interacoes WHERE canal = 'whatsapp' AND respondeu = 1")
        stats['respostas'] = c.fetchone()['n']

        c.execute(
            "SELECT quantidade FROM acoes_diarias WHERE data = CURRENT_DATE AND tipo = 'whatsapp_enviados'"
        )
        row = c.fetchone()
        stats['msgs_hoje'] = row['quantidade'] if row else 0

        conn.close()
        return stats
    except Exception:
        return {
            'total_leads': 0, 'contactadas': 0, 'responderam': 0,
            'demos': 0, 'msgs_enviadas': 0, 'respostas': 0, 'msgs_hoje': 0
        }


def get_leads(limite=50):
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("""SELECT nome_fantasia, whatsapp, score, status, segmento,
                   demo_status, encontrado_em
            FROM empresas ORDER BY score DESC, encontrado_em DESC LIMIT %s""", (limite,))
        leads = [dict(row) for row in c.fetchall()]
        conn.close()
        return leads
    except Exception:
        return []


def get_logs(limite=30):
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("""SELECT tipo, mensagem, timestamp FROM logs
            ORDER BY timestamp DESC LIMIT %s""", (limite,))
        logs = [dict(row) for row in c.fetchall()]
        conn.close()
        return logs
    except Exception:
        return []


# =============================================================================
# ROTAS
# =============================================================================

@app.route('/')
def index():
    stats = get_stats()
    return render_template('index.html', stats=stats)


@app.route('/api/stats')
def api_stats():
    return jsonify(get_stats())


@app.route('/api/leads')
def api_leads():
    limite = request.args.get('limite', 50, type=int)
    return jsonify(get_leads(limite))


@app.route('/api/logs')
def api_logs():
    return jsonify(get_logs())


@app.route('/api/status')
def api_status():
    return jsonify({'status': 'online', 'bot': 'prima', 'version': '2.0'})


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    debug = os.environ.get('FLASK_ENV', 'production') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)
