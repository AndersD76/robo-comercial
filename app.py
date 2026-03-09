# -*- coding: utf-8 -*-
"""
Robôs Comerciais — Dashboard Unificado
Prisma (PrismaBiz) + Pili (Equipamentos para Grãos)
Um único serviço Railway, uma página, dois cards.
"""

import json
import os
import subprocess
import sys
import psycopg2
import psycopg2.extras
from flask import Flask, jsonify, render_template, request, send_file

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'robo-comercial-2024')

def _norm_db_url(url):
    if url and url.startswith('psql://'):
        return 'postgresql://' + url[7:]
    if url and url.startswith('postgres://'):
        return 'postgresql://' + url[11:]
    return url

DATABASE_URL = _norm_db_url(os.environ.get('DATABASE_URL', ''))

# Processos em background — {bot: {'wa': Popen|None, 'li': Popen|None}}
_procs: dict = {
    'prisma': {'wa': None},
    'pili':   {'wa': None},
}


def _bot_dir(bot: str) -> str:
    base = os.path.dirname(os.path.abspath(__file__))
    # pasta em disco usa nome curto: prisma -> prima
    _map = {'prisma': 'prima', 'pili': 'pili'}
    folder = _map.get(bot, bot)
    return os.path.join(base, f'robo_{folder}')


def _is_running(proc) -> bool:
    return proc is not None and proc.poll() is None



def _valid_schema(bot):
    return {'prisma': 'prisma', 'pili': 'pili'}.get(bot)

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
    """Retorna métricas do robô (WhatsApp)."""
    zero = {
        # WhatsApp
        'total_leads': 0, 'contactadas': 0, 'responderam': 0,
        'demos': 0, 'msgs_enviadas': 0, 'respostas': 0, 'msgs_hoje': 0,
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

        conn.close()
    except Exception as e:
        print(f"[stats/{schema}] erro: {e}")
    return zero


_migrated = {}
def _ensure_email_enviado(conn, schema):
    """Garante que a coluna email_enviado existe (roda 1x por schema)."""
    if schema in _migrated:
        return
    try:
        c = conn.cursor()
        c.execute("ALTER TABLE empresas ADD COLUMN IF NOT EXISTS email_enviado TIMESTAMP")
        conn.commit()
        _migrated[schema] = True
    except Exception:
        conn.rollback()


def get_leads(schema: str, limite: int = 500) -> list:
    if not DATABASE_URL:
        return []
    try:
        conn = get_db(schema)
        _ensure_email_enviado(conn, schema)
        c = conn.cursor()
        c.execute(
            """SELECT id, nome_fantasia, whatsapp, telefone, email, score,
                      status, segmento, demo_status, cidade, estado,
                      encontrado_em, cnpj, razao_social, website, linkedin, instagram, fonte, porte,
                      email_enviado
               FROM empresas
               ORDER BY encontrado_em DESC
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



# =============================================================================
# ROTAS — PÁGINAS
# =============================================================================

# Config por bot (cores CSS, labels)
_BOT_CFG = {
    'prisma': {
        'name': 'Prisma', 'label': 'PrismaBiz',
        'color': '#10b981',
        'color_dim': 'rgba(16,185,129,.08)',
        'color_bd': 'rgba(16,185,129,.18)',
    },
    'pili': {
        'name': 'Pili', 'label': 'Equipamentos',
        'color': '#f59e0b',
        'color_dim': 'rgba(245,158,11,.08)',
        'color_bd': 'rgba(245,158,11,.18)',
    },
}


@app.route('/')
def landing():
    prisma = get_stats('prisma')
    pili = get_stats('pili')
    return render_template('landing.html', prisma=prisma, pili=pili)


@app.route('/prisma')
def dashboard_prisma():
    stats = get_stats('prisma')
    return render_template('dashboard.html', bot='prisma',
                           stats=stats, **_BOT_CFG['prisma'])


@app.route('/pili')
def dashboard_pili():
    stats = get_stats('pili')
    return render_template('dashboard.html', bot='pili',
                           stats=stats, **_BOT_CFG['pili'])


# --- API Prisma ---
@app.route('/api/prisma/stats')
def api_prisma_stats():
    return jsonify(get_stats('prisma'))


@app.route('/api/prisma/leads')
def api_prisma_leads():
    limite = request.args.get('limite', 500, type=int)
    return jsonify(get_leads('prisma', limite))


@app.route('/api/prisma/logs')
def api_prisma_logs():
    return jsonify(get_logs('prisma'))



# --- API Pili ---
@app.route('/api/pili/stats')
def api_pili_stats():
    return jsonify(get_stats('pili'))


@app.route('/api/pili/leads')
def api_pili_leads():
    limite = request.args.get('limite', 500, type=int)
    return jsonify(get_leads('pili', limite))



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
            # — WhatsApp leads —
            c.execute("""
                SELECT e.id, e.nome_fantasia, e.segmento, e.score,
                       e.status, e.demo_status, e.cidade, e.estado,
                       e.whatsapp, e.telefone, e.email, e.encontrado_em,
                       COUNT(i.id) AS msgs,
                       MAX(i.enviado_em) AS ultima_msg,
                       MAX(CASE WHEN i.tipo = 'inicial' THEN i.mensagem END) AS msg_enviada,
                       MAX(CASE WHEN i.respondeu = 1 THEN i.resposta END) AS ultima_resposta,
                       MAX(i.respondido_em) AS respondido_em,
                       SUM(CASE WHEN i.respondeu = 1 THEN 1 ELSE 0 END) AS respostas,
                       'whatsapp' AS canal
                FROM empresas e
                LEFT JOIN interacoes i ON e.id = i.empresa_id
                  AND i.canal = 'whatsapp'
                GROUP BY e.id, e.nome_fantasia, e.segmento, e.score,
                         e.status, e.demo_status, e.cidade, e.estado,
                         e.whatsapp, e.telefone, e.email, e.encontrado_em
                ORDER BY e.score DESC, e.encontrado_em DESC
                LIMIT 200
            """)
            rows = c.fetchall()
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

            conn.close()
        except Exception as e:
            print(f"[pipeline/{schema}] erro: {e}")
    return jsonify(stages)


# --- Controle dos bots (start / stop / status) ---

@app.route('/api/<bot>/status')
def api_bot_status(bot):
    if bot not in _procs:
        return jsonify({'error': 'bot invalido'}), 400
    return jsonify({
        'wa': _is_running(_procs[bot]['wa']),
    })


@app.route('/api/<bot>/start', methods=['POST'])
def api_bot_start(bot):
    if bot not in _procs:
        return jsonify({'error': 'bot invalido'}), 400
    data = request.get_json(silent=True) or {}
    canal = data.get('canal', 'wa')
    if canal not in ('wa',):
        return jsonify({'error': 'canal invalido'}), 400
    if _is_running(_procs[bot][canal]):
        return jsonify({'status': 'already_running'})
    script = 'run_wa.py'
    bot_dir = _bot_dir(bot)
    log_path = os.path.join(bot_dir, f'{canal}.log')
    log_file = open(log_path, 'a', encoding='utf-8')
    proc = subprocess.Popen(
        [sys.executable, '-u', script],
        cwd=bot_dir,
        stdout=log_file,
        stderr=log_file,
    )
    _procs[bot][canal] = proc
    return jsonify({'status': 'started', 'pid': proc.pid})


@app.route('/api/<bot>/stop', methods=['POST'])
def api_bot_stop(bot):
    if bot not in _procs:
        return jsonify({'error': 'bot invalido'}), 400
    data = request.get_json(silent=True) or {}
    canal = data.get('canal', 'wa')
    proc = _procs[bot].get(canal)
    if not _is_running(proc):
        _procs[bot][canal] = None
        return jsonify({'status': 'not_running'})
    proc.terminate()
    _procs[bot][canal] = None
    return jsonify({'status': 'stopped'})


# --- Adicionar lead manualmente ---
@app.route('/api/<bot>/add-lead', methods=['POST'])
def api_add_lead(bot):
    schema = _valid_schema(bot)
    if not schema:
        return jsonify({'error': 'bot invalido'}), 400
    data = request.get_json(silent=True) or {}
    nome = (data.get('nome_fantasia') or '').strip()
    whatsapp = (data.get('whatsapp') or '').strip()
    email = (data.get('email') or '').strip()
    if not nome:
        return jsonify({'error': 'nome_fantasia obrigatorio'}), 400
    try:
        conn = get_db(schema)
        c = conn.cursor()
        # Verifica duplicata por whatsapp
        if whatsapp:
            c.execute(
                "SELECT id FROM empresas WHERE whatsapp = %s", (whatsapp,))
            ex = c.fetchone()
            if ex:
                conn.close()
                return jsonify({'ok': True, 'id': ex['id'],
                                'msg': 'lead ja existe'})
        c.execute("""INSERT INTO empresas (
            nome_fantasia, whatsapp, email, telefone, segmento,
            fonte, score, status
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""", (
            nome, whatsapp or None, email or None,
            data.get('telefone'), data.get('segmento', 'Teste'),
            'manual', data.get('score', 80), 'novo',
        ))
        new_id = c.fetchone()['id']
        conn.commit()
        conn.close()
        return jsonify({'ok': True, 'id': new_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500



# --- CRUD: Atualizar lead WA (empresa) ---
@app.route('/api/<bot>/lead/<int:lead_id>', methods=['PUT'])
def api_update_lead(bot, lead_id):
    schema = _valid_schema(bot)
    if not schema:
        return jsonify({'error': 'bot invalido'}), 400
    data = request.get_json(silent=True) or {}
    allowed = {
        'nome_fantasia', 'whatsapp', 'telefone', 'email', 'segmento',
        'status', 'score', 'cidade', 'estado', 'website', 'linkedin',
        'instagram', 'porte', 'demo_status',
    }
    fields = {k: v for k, v in data.items() if k in allowed}
    if not fields:
        return jsonify({'error': 'nenhum campo valido'}), 400
    try:
        conn = get_db(schema)
        c = conn.cursor()
        sets = ', '.join(f'{k} = %s' for k in fields)
        vals = list(fields.values()) + [lead_id]
        c.execute(f'UPDATE empresas SET {sets} WHERE id = %s', vals)
        conn.commit()
        conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# --- CRUD: Deletar lead WA (empresa) ---
@app.route('/api/<bot>/lead/<int:lead_id>', methods=['DELETE'])
def api_delete_lead(bot, lead_id):
    schema = _valid_schema(bot)
    if not schema:
        return jsonify({'error': 'bot invalido'}), 400
    try:
        conn = get_db(schema)
        c = conn.cursor()
        c.execute('DELETE FROM interacoes WHERE empresa_id = %s', (lead_id,))
        c.execute('DELETE FROM contatos WHERE empresa_id = %s', (lead_id,))
        c.execute('DELETE FROM empresas WHERE id = %s', (lead_id,))
        conn.commit()
        conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500



# --- Envio de email em massa (mala direta via Brevo API) ---
@app.route('/api/<bot>/send-emails', methods=['POST'])
def api_send_emails(bot):
    import requests as http
    schema = _valid_schema(bot)
    if not schema:
        return jsonify({'error': 'bot invalido'}), 400
    data = request.get_json(silent=True) or {}
    lead_ids = data.get('ids', [])
    if not lead_ids:
        return jsonify({'error': 'nenhum lead selecionado'}), 400

    api_key = os.environ.get('BREVO_API_KEY', '')
    sender_email = os.environ.get('EMAIL_FROM', 'contato@prismabiz.com.br')
    sender_name = os.environ.get('EMAIL_FROM_NAME', 'PrismaBiz')
    if not api_key:
        return jsonify({'error': 'BREVO_API_KEY nao configurado'}), 400

    tpl_path = os.path.join(
        os.path.dirname(__file__), 'templates', f'email_{bot}.html')
    try:
        with open(tpl_path, 'r', encoding='utf-8') as f:
            tpl_html = f.read()
    except FileNotFoundError:
        return jsonify({'error': f'template email_{bot}.html nao encontrado'}), 400

    conn = get_db(schema)
    c = conn.cursor()
    placeholders = ','.join(['%s'] * len(lead_ids))
    c.execute(
        f"SELECT id, nome_fantasia, email FROM empresas "
        f"WHERE id IN ({placeholders}) AND email IS NOT NULL",
        lead_ids)
    leads = c.fetchall()
    conn.close()

    if not leads:
        return jsonify({'error': 'nenhum lead com email'}), 400

    demo_link = os.environ.get(
        'DEMO_CAL_LINK', 'https://calendar.app.google/SEU_LINK_AQUI')
    wa_pili = os.environ.get('WHATSAPP_PILI', '')
    subjects = {
        'prisma': '{nome}, 11 ferramentas de qualidade grátis — PrismaBiz',
        'pili': '{nome}, reduza perdas na recepção de grãos'
                ' — Pili Equipamentos',
    }

    enviados = erros = 0
    for lead in leads:
        nome = lead['nome_fantasia'] or 'empresa'
        html = (tpl_html
                .replace('{{nome}}', nome)
                .replace('{{DEMO_CAL_LINK}}', demo_link)
                .replace('{{WHATSAPP_PILI}}', wa_pili))
        subject = subjects.get(bot, 'Contato Comercial').format(nome=nome)
        try:
            r = http.post(
                'https://api.brevo.com/v3/smtp/email',
                headers={'api-key': api_key,
                         'Content-Type': 'application/json'},
                json={
                    'sender': {'name': sender_name, 'email': sender_email},
                    'to': [{'email': lead['email'], 'name': nome}],
                    'subject': subject,
                    'htmlContent': html,
                },
                timeout=10,
            )
            if r.status_code in (200, 201):
                enviados += 1
                try:
                    conn2 = get_db(schema)
                    c2 = conn2.cursor()
                    c2.execute("UPDATE empresas SET email_enviado = NOW() WHERE id = %s", (lead['id'],))
                    conn2.commit()
                    conn2.close()
                except Exception:
                    pass
            else:
                print(f"[EMAIL] erro {lead['email']}: {r.text}", flush=True)
                erros += 1
        except Exception as e:
            print(f"[EMAIL] exception {lead['email']}: {e}", flush=True)
            erros += 1

    return jsonify({'ok': True, 'enviados': enviados, 'erros': erros})


# --- QR Code do WhatsApp (screenshot salvo pelo subprocess) ---
@app.route('/api/<bot>/qr')
def api_bot_qr(bot):
    if bot not in _procs:
        return ('', 404)
    qr_path = os.path.join(_bot_dir(bot), 'wa_qr.png')
    if os.path.exists(qr_path):
        return send_file(qr_path, mimetype='image/png',
                         max_age=0, conditional=False)
    return ('', 404)


# --- Console (últimas linhas do log) ---
@app.route('/api/<bot>/console')
def api_bot_console(bot):
    if bot not in _procs:
        return jsonify({'lines': [], 'error': 'bot invalido'}), 400
    canal = request.args.get('canal', 'wa')
    n = request.args.get('n', 60, type=int)
    bot_dir = _bot_dir(bot)
    log_path = os.path.join(bot_dir, f'{canal}.log')
    try:
        with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        return jsonify({'lines': [l.rstrip('\n') for l in lines[-n:]]})
    except FileNotFoundError:
        return jsonify({'lines': []})
    except Exception as e:
        return jsonify({'lines': [], 'error': str(e)})




@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'bots': ['prisma', 'pili']})


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
