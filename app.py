# -*- coding: utf-8 -*-
"""
Máquina de Vendas — SaaS multi-tenant
Landing page + cadastro + dashboard por empresa + LinkedIn + busca IA
"""

import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import psycopg2
import psycopg2.extras
from functools import wraps
from flask import (Flask, jsonify, redirect, render_template,
                   request, send_file, session, url_for)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'mv-saas-2025-change-in-prod')

DATABASE_URL = os.environ.get('DATABASE_URL', '')
if DATABASE_URL.startswith('psql://'):
    DATABASE_URL = 'postgresql://' + DATABASE_URL[7:]
elif DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = 'postgresql://' + DATABASE_URL[11:]

# Processos em background: {schema: {'busca': Popen, 'linkedin': Popen}}
_procs: dict = {}


# =============================================================================
# DB HELPERS
# =============================================================================

def _conn(schema: str | None = None):
    conn = psycopg2.connect(DATABASE_URL,
                            cursor_factory=psycopg2.extras.RealDictCursor)
    if schema:
        with conn.cursor() as c:
            c.execute('SET search_path TO %s, public', (schema,))
        conn.commit()
    return conn


def _init_public_schema():
    if not DATABASE_URL:
        return
    try:
        conn = _conn()
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS users (
            id            BIGSERIAL PRIMARY KEY,
            email         TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            empresa_nome  TEXT,
            website       TEXT,
            descricao     TEXT,
            schema_name   TEXT UNIQUE,
            plano         TEXT DEFAULT 'trial',
            ativo         BOOLEAN DEFAULT TRUE,
            criado_em     TIMESTAMP DEFAULT NOW()
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS api_tokens (
            id        BIGSERIAL PRIMARY KEY,
            user_id   BIGINT REFERENCES users(id) ON DELETE CASCADE,
            token     TEXT UNIQUE NOT NULL,
            label     TEXT,
            ativo     BOOLEAN DEFAULT TRUE,
            criado_em TIMESTAMP DEFAULT NOW()
        )""")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f'[init_public] erro: {e}')


def _init_user_schema(schema: str):
    conn = _conn()
    c = conn.cursor()
    c.execute('CREATE SCHEMA IF NOT EXISTS ' + schema)
    c.execute('SET search_path TO %s, public', (schema,))
    conn.commit()
    c.execute("""CREATE TABLE IF NOT EXISTS empresas (
        id BIGSERIAL PRIMARY KEY, cnpj TEXT UNIQUE,
        razao_social TEXT, nome_fantasia TEXT, segmento TEXT,
        porte TEXT, funcionarios TEXT, endereco TEXT, cidade TEXT, estado TEXT,
        telefone TEXT, telefone2 TEXT, whatsapp TEXT, email TEXT,
        website TEXT, linkedin TEXT, instagram TEXT, fonte TEXT,
        score INTEGER DEFAULT 0, encontrado_em TIMESTAMP DEFAULT NOW(),
        status TEXT DEFAULT 'novo', demo_agendado TIMESTAMP,
        demo_status TEXT, email_enviado TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS contatos (
        id BIGSERIAL PRIMARY KEY, empresa_id BIGINT REFERENCES empresas(id),
        nome TEXT, cargo TEXT, telefone TEXT, whatsapp TEXT,
        email TEXT, linkedin TEXT, decisor INTEGER DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS interacoes (
        id BIGSERIAL PRIMARY KEY, empresa_id BIGINT REFERENCES empresas(id),
        contato_id BIGINT REFERENCES contatos(id),
        canal TEXT, tipo TEXT, mensagem TEXT,
        enviado_em TIMESTAMP DEFAULT NOW(),
        respondeu INTEGER DEFAULT 0, resposta TEXT, respondido_em TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS leads_linkedin (
        id BIGSERIAL PRIMARY KEY, nome TEXT, cargo TEXT, empresa TEXT,
        url_perfil TEXT UNIQUE, termo_busca TEXT,
        status TEXT DEFAULT 'encontrado', encontrado_em TIMESTAMP DEFAULT NOW(),
        conexao_em TIMESTAMP, dm_enviada_em TIMESTAMP,
        respondeu INTEGER DEFAULT 0, ultima_resposta TEXT, demo_status TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS buscas (
        id BIGSERIAL PRIMARY KEY, termo TEXT, fonte TEXT,
        resultados INTEGER DEFAULT 0, executado_em TIMESTAMP DEFAULT NOW()
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS acoes_diarias (
        id BIGSERIAL PRIMARY KEY, data DATE DEFAULT CURRENT_DATE,
        tipo TEXT, quantidade INTEGER DEFAULT 0, UNIQUE(data, tipo)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS logs (
        id BIGSERIAL PRIMARY KEY, timestamp TIMESTAMP DEFAULT NOW(),
        tipo TEXT, mensagem TEXT, detalhes TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS execucao (
        id INTEGER PRIMARY KEY, status TEXT DEFAULT 'parado',
        ultima_execucao TIMESTAMP, modo TEXT DEFAULT 'busca'
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS bot_config (
        id           SERIAL PRIMARY KEY,
        empresa_nome TEXT, website TEXT, descricao TEXT,
        termos_busca JSONB DEFAULT '[]',
        linkedin_email TEXT, linkedin_password TEXT,
        linkedin_cargos JSONB DEFAULT '[]',
        atualizado_em TIMESTAMP DEFAULT NOW()
    )""")
    c.execute("INSERT INTO execucao (id) VALUES (1) ON CONFLICT DO NOTHING")
    conn.commit()
    conn.close()


# =============================================================================
# AUTH HELPERS
# =============================================================================

def _hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            if request.path.startswith('/api/'):
                return jsonify({'error': 'não autenticado'}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def get_current_user():
    uid = session.get('user_id')
    if not uid:
        return None
    try:
        conn = _conn()
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE id = %s AND ativo = TRUE', (uid,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception:
        return None


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer '):
            return jsonify({'error': 'Bearer token obrigatório'}), 401
        token = auth[7:]
        try:
            conn = _conn()
            c = conn.cursor()
            c.execute("""SELECT t.*, u.schema_name FROM api_tokens t
                         JOIN users u ON t.user_id = u.id
                         WHERE t.token = %s AND t.ativo = TRUE AND u.ativo = TRUE""",
                      (token,))
            row = c.fetchone()
            conn.close()
            if not row:
                return jsonify({'error': 'token inválido'}), 401
            request.token_user = dict(row)
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        return f(*args, **kwargs)
    return decorated


# =============================================================================
# DB QUERIES
# =============================================================================

def get_stats(schema: str) -> dict:
    z = {'total_leads': 0, 'contactadas': 0, 'responderam': 0,
         'demos': 0, 'buscas_hoje': 0, 'emails_enviados': 0,
         'linkedin_total': 0}
    if not DATABASE_URL or not schema:
        return z
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute('SELECT COUNT(*) AS n FROM empresas')
        z['total_leads'] = c.fetchone()['n']
        c.execute("SELECT COUNT(*) AS n FROM empresas WHERE status = 'contactada'")
        z['contactadas'] = c.fetchone()['n']
        c.execute("SELECT COUNT(*) AS n FROM empresas WHERE status = 'respondeu'")
        z['responderam'] = c.fetchone()['n']
        c.execute("SELECT COUNT(*) AS n FROM empresas WHERE demo_status = 'confirmado'")
        z['demos'] = c.fetchone()['n']
        c.execute("SELECT quantidade FROM acoes_diarias WHERE data = CURRENT_DATE AND tipo = 'buscas'")
        r = c.fetchone()
        z['buscas_hoje'] = r['quantidade'] if r else 0
        c.execute("SELECT COUNT(*) AS n FROM empresas WHERE email_enviado IS NOT NULL")
        z['emails_enviados'] = c.fetchone()['n']
        try:
            c.execute('SELECT COUNT(*) AS n FROM leads_linkedin')
            z['linkedin_total'] = c.fetchone()['n']
        except Exception:
            pass
        conn.close()
    except Exception as e:
        print(f'[stats/{schema}] {e}')
    return z


def get_leads(schema: str, limite: int = 500) -> list:
    if not DATABASE_URL or not schema:
        return []
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute("""SELECT id, nome_fantasia, whatsapp, telefone, email, score,
                            status, segmento, demo_status, cidade, estado,
                            encontrado_em, cnpj, razao_social, website,
                            linkedin, instagram, fonte, porte, email_enviado
                     FROM empresas ORDER BY encontrado_em DESC LIMIT %s""", (limite,))
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        print(f'[leads/{schema}] {e}')
        return []


def get_logs(schema: str, limite: int = 60) -> list:
    if not DATABASE_URL or not schema:
        return []
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute("SELECT tipo, mensagem, timestamp FROM logs ORDER BY timestamp DESC LIMIT %s", (limite,))
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        return []


def get_bot_config(schema: str) -> dict:
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute('SELECT * FROM bot_config ORDER BY id DESC LIMIT 1')
        row = c.fetchone()
        conn.close()
        return dict(row) if row else {}
    except Exception:
        return {}


def _get_schema():
    user = get_current_user()
    return user['schema_name'] if user and user.get('schema_name') else None


def _proc_running(schema: str, canal: str) -> bool:
    p = _procs.get(schema, {}).get(canal)
    return p is not None and p.poll() is None


# =============================================================================
# ROUTES — AUTH
# =============================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_id'):
        return redirect(url_for('dashboard'))
    error = None
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        pw = request.form.get('senha', '')
        try:
            conn = _conn()
            c = conn.cursor()
            c.execute('SELECT * FROM users WHERE email = %s AND ativo = TRUE', (email,))
            user = c.fetchone()
            conn.close()
            if user and user['password_hash'] == _hash_pw(pw):
                session['user_id'] = user['id']
                return redirect(url_for('dashboard'))
            error = 'Email ou senha incorretos'
        except Exception as e:
            error = f'Erro: {e}'
    return render_template('login.html', error=error)


@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if session.get('user_id'):
        return redirect(url_for('dashboard'))
    error = None
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        pw = request.form.get('senha', '')
        empresa = request.form.get('empresa_nome', '').strip()
        website = request.form.get('website', '').strip()
        if not email or not pw or not empresa:
            error = 'Preencha todos os campos obrigatórios'
        elif len(pw) < 6:
            error = 'Senha mínimo 6 caracteres'
        else:
            try:
                conn = _conn()
                c = conn.cursor()
                c.execute('SELECT id FROM users WHERE email = %s', (email,))
                if c.fetchone():
                    error = 'Email já cadastrado'
                else:
                    c.execute("""INSERT INTO users (email, password_hash, empresa_nome, website)
                                 VALUES (%s,%s,%s,%s) RETURNING id""",
                              (email, _hash_pw(pw), empresa, website or None))
                    uid = c.fetchone()['id']
                    schema = f'emp_{uid}'
                    c.execute('UPDATE users SET schema_name=%s WHERE id=%s', (schema, uid))
                    conn.commit()
                    conn.close()
                    _init_user_schema(schema)
                    conn2 = _conn(schema)
                    c2 = conn2.cursor()
                    c2.execute('INSERT INTO bot_config (empresa_nome, website) VALUES (%s,%s)',
                               (empresa, website or None))
                    conn2.commit()
                    conn2.close()
                    session['user_id'] = uid
                    return redirect(url_for('config_page'))
            except Exception as e:
                error = f'Erro: {e}'
    return render_template('register.html', error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('landing'))


# =============================================================================
# ROUTES — PÁGINAS
# =============================================================================

@app.route('/')
def landing():
    return render_template('landing.html')


@app.route('/dashboard')
@login_required
def dashboard():
    user = get_current_user()
    if not user or not user.get('schema_name'):
        return redirect(url_for('config_page'))
    schema = user['schema_name']
    stats = get_stats(schema)
    return render_template('dashboard.html',
                           bot=schema,
                           user=user,
                           stats=stats,
                           name=user['empresa_nome'] or 'Minha Empresa',
                           label='Leads',
                           color='#6366f1',
                           color_dim='rgba(99,102,241,.08)',
                           color_bd='rgba(99,102,241,.18)')


@app.route('/configurar')
@login_required
def config_page():
    user = get_current_user()
    schema = user.get('schema_name') if user else None
    cfg = get_bot_config(schema) if schema else {}
    return render_template('config.html', user=user, cfg=cfg)


# =============================================================================
# ROUTES — API (requer sessão ou token)
# =============================================================================

@app.route('/api/<bot>/stats')
@login_required
def api_stats(bot):
    return jsonify(get_stats(_get_schema() or bot))


@app.route('/api/<bot>/leads')
@login_required
def api_leads(bot):
    schema = _get_schema() or bot
    limite = request.args.get('limite', 500, type=int)
    return jsonify(get_leads(schema, limite))


@app.route('/api/<bot>/logs')
@login_required
def api_logs(bot):
    return jsonify(get_logs(_get_schema() or bot))


@app.route('/api/<bot>/status')
@login_required
def api_bot_status(bot):
    schema = _get_schema() or bot
    return jsonify({
        'busca':    _proc_running(schema, 'busca'),
        'linkedin': _proc_running(schema, 'linkedin'),
    })


@app.route('/api/<bot>/start', methods=['POST'])
@login_required
def api_bot_start(bot):
    schema = _get_schema() or bot
    data = request.get_json(silent=True) or {}
    canal = data.get('canal', 'busca')
    if canal not in ('busca', 'linkedin'):
        return jsonify({'error': 'canal inválido (busca|linkedin)'}), 400
    if _proc_running(schema, canal):
        return jsonify({'status': 'already_running'})

    base = os.path.dirname(os.path.abspath(__file__))
    bot_dir = os.path.join(base, 'robo_pili')
    script = 'run_busca.py' if canal == 'busca' else 'run_linkedin.py'
    log_path = os.path.join(bot_dir, f'{canal}.log')
    log_file = open(log_path, 'a', encoding='utf-8')
    proc = subprocess.Popen(
        [sys.executable, '-u', script, '--schema', schema],
        cwd=bot_dir, stdout=log_file, stderr=log_file,
    )
    _procs.setdefault(schema, {})
    _procs[schema][canal] = proc
    return jsonify({'status': 'started', 'pid': proc.pid, 'canal': canal})


@app.route('/api/<bot>/stop', methods=['POST'])
@login_required
def api_bot_stop(bot):
    schema = _get_schema() or bot
    data = request.get_json(silent=True) or {}
    canal = data.get('canal', 'busca')
    proc = _procs.get(schema, {}).get(canal)
    if proc and proc.poll() is None:
        proc.terminate()
    _procs.setdefault(schema, {})[canal] = None
    return jsonify({'status': 'stopped', 'canal': canal})


@app.route('/api/<bot>/console')
@login_required
def api_bot_console(bot):
    schema = _get_schema() or bot
    canal = request.args.get('canal', 'busca')
    n = request.args.get('n', 60, type=int)
    base = os.path.dirname(os.path.abspath(__file__))
    log_path = os.path.join(base, 'robo_pili', f'{canal}.log')
    try:
        with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        return jsonify({'lines': [l.rstrip('\n') for l in lines[-n:]]})
    except FileNotFoundError:
        return jsonify({'lines': []})
    except Exception as e:
        return jsonify({'lines': [], 'error': str(e)})


# --- Lead CRUD ---

@app.route('/api/<bot>/add-lead', methods=['POST'])
@login_required
def api_add_lead(bot):
    schema = _get_schema() or bot
    data = request.get_json(silent=True) or {}
    nome = (data.get('nome_fantasia') or '').strip()
    if not nome:
        return jsonify({'error': 'nome_fantasia obrigatorio'}), 400
    try:
        conn = _conn(schema)
        c = conn.cursor()
        wa = (data.get('whatsapp') or '').strip() or None
        if wa:
            c.execute('SELECT id FROM empresas WHERE whatsapp = %s', (wa,))
            ex = c.fetchone()
            if ex:
                conn.close()
                return jsonify({'ok': True, 'id': ex['id'], 'msg': 'ja existe'})
        c.execute("""INSERT INTO empresas
            (nome_fantasia, whatsapp, email, telefone, segmento, fonte, score, status)
            VALUES (%s,%s,%s,%s,%s,'manual',%s,'novo') RETURNING id""",
                  (nome, wa, data.get('email') or None,
                   data.get('telefone'), data.get('segmento', ''), data.get('score', 50)))
        new_id = c.fetchone()['id']
        conn.commit()
        conn.close()
        return jsonify({'ok': True, 'id': new_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/<bot>/lead/<int:lead_id>', methods=['PUT'])
@login_required
def api_update_lead(bot, lead_id):
    schema = _get_schema() or bot
    data = request.get_json(silent=True) or {}
    allowed = {'nome_fantasia', 'whatsapp', 'telefone', 'email', 'segmento',
               'status', 'score', 'cidade', 'estado', 'website', 'linkedin',
               'instagram', 'porte', 'demo_status'}
    fields = {k: v for k, v in data.items() if k in allowed}
    if not fields:
        return jsonify({'error': 'nenhum campo valido'}), 400
    try:
        conn = _conn(schema)
        c = conn.cursor()
        sets = ', '.join(f'{k} = %s' for k in fields)
        c.execute(f'UPDATE empresas SET {sets} WHERE id = %s', list(fields.values()) + [lead_id])
        conn.commit()
        conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/<bot>/lead/<int:lead_id>', methods=['DELETE'])
@login_required
def api_delete_lead(bot, lead_id):
    schema = _get_schema() or bot
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute('DELETE FROM interacoes WHERE empresa_id = %s', (lead_id,))
        c.execute('DELETE FROM contatos WHERE empresa_id = %s', (lead_id,))
        c.execute('DELETE FROM empresas WHERE id = %s', (lead_id,))
        conn.commit()
        conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# --- Email em massa ---

@app.route('/api/<bot>/send-emails', methods=['POST'])
@login_required
def api_send_emails(bot):
    import requests as http
    schema = _get_schema() or bot
    data = request.get_json(silent=True) or {}
    lead_ids = data.get('ids', [])
    if not lead_ids:
        return jsonify({'error': 'nenhum lead selecionado'}), 400
    api_key = os.environ.get('BREVO_API_KEY', '')
    if not api_key:
        return jsonify({'error': 'BREVO_API_KEY nao configurado'}), 400
    sender_email = os.environ.get('EMAIL_FROM', '')
    sender_name = os.environ.get('EMAIL_FROM_NAME', 'Máquina de Vendas')
    if not sender_email:
        return jsonify({'error': 'EMAIL_FROM nao configurado'}), 400

    tpl_path = os.path.join(os.path.dirname(__file__), 'templates', 'email_custom.html')
    if not os.path.exists(tpl_path):
        tpl_path = os.path.join(os.path.dirname(__file__), 'templates', 'email_pili.html')
    try:
        with open(tpl_path, 'r', encoding='utf-8') as f:
            tpl_html = f.read()
    except FileNotFoundError:
        return jsonify({'error': 'template de email nao encontrado'}), 400

    user = get_current_user()
    conn = _conn(schema)
    c = conn.cursor()
    ph = ','.join(['%s'] * len(lead_ids))
    c.execute(f"SELECT id, nome_fantasia, email FROM empresas WHERE id IN ({ph}) AND email IS NOT NULL",
              lead_ids)
    leads = c.fetchall()
    conn.close()
    if not leads:
        return jsonify({'error': 'nenhum lead com email'}), 400

    demo_link = os.environ.get('DEMO_CAL_LINK', '')
    empresa_nome = user['empresa_nome'] if user else ''
    enviados = erros = 0
    for lead in leads:
        nome = lead['nome_fantasia'] or 'empresa'
        html = (tpl_html.replace('{{nome}}', nome)
                        .replace('{{DEMO_CAL_LINK}}', demo_link)
                        .replace('{{EMPRESA}}', empresa_nome))
        try:
            r = http.post('https://api.brevo.com/v3/smtp/email',
                          headers={'api-key': api_key, 'Content-Type': 'application/json'},
                          json={'sender': {'name': sender_name, 'email': sender_email},
                                'to': [{'email': lead['email'], 'name': nome}],
                                'subject': f'{nome}, conheça {empresa_nome}',
                                'htmlContent': html},
                          timeout=10)
            if r.status_code in (200, 201):
                enviados += 1
                conn2 = _conn(schema)
                c2 = conn2.cursor()
                c2.execute("UPDATE empresas SET email_enviado = NOW() WHERE id = %s", (lead['id'],))
                conn2.commit()
                conn2.close()
            else:
                erros += 1
        except Exception:
            erros += 1
    return jsonify({'ok': True, 'enviados': enviados, 'erros': erros})


# --- Config do bot ---

@app.route('/api/<bot>/config', methods=['GET'])
@login_required
def api_get_config(bot):
    schema = _get_schema() or bot
    cfg = get_bot_config(schema)
    # Não retorna senha do LinkedIn
    cfg.pop('linkedin_password', None)
    return jsonify(cfg)


@app.route('/api/<bot>/config', methods=['POST'])
@login_required
def api_save_config(bot):
    schema = _get_schema() or bot
    data = request.get_json(silent=True) or {}
    empresa_nome = data.get('empresa_nome', '')
    website = data.get('website', '')
    descricao = data.get('descricao', '')
    termos = data.get('termos_busca') or []
    li_email = data.get('linkedin_email', '')
    li_password = data.get('linkedin_password', '')
    li_cargos = data.get('linkedin_cargos') or []

    if not termos and descricao:
        termos = _gerar_termos_ia(empresa_nome, descricao, website)

    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute('SELECT id FROM bot_config LIMIT 1')
        exists = c.fetchone()
        if exists:
            c.execute("""UPDATE bot_config SET empresa_nome=%s, website=%s, descricao=%s,
                         termos_busca=%s, linkedin_email=%s, linkedin_cargos=%s,
                         atualizado_em=NOW()
                         """ + (", linkedin_password=%s" if li_password else ""),
                      ([empresa_nome, website, descricao, json.dumps(termos),
                        li_email or None, json.dumps(li_cargos)] +
                       ([li_password] if li_password else [])))
        else:
            c.execute("""INSERT INTO bot_config
                (empresa_nome, website, descricao, termos_busca, linkedin_email,
                 linkedin_password, linkedin_cargos)
                VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                      (empresa_nome, website, descricao, json.dumps(termos),
                       li_email or None, li_password or None, json.dumps(li_cargos)))
        uid = session.get('user_id')
        if uid:
            conn2 = _conn()
            c2 = conn2.cursor()
            c2.execute('UPDATE users SET empresa_nome=%s, website=%s, descricao=%s WHERE id=%s',
                       (empresa_nome, website, descricao, uid))
            conn2.commit()
            conn2.close()
        conn.commit()
        conn.close()
        return jsonify({'ok': True, 'termos': termos})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/<bot>/config/generate-terms', methods=['POST'])
@login_required
def api_generate_terms(bot):
    data = request.get_json(silent=True) or {}
    termos = _gerar_termos_ia(
        data.get('empresa_nome', ''),
        data.get('descricao', ''),
        data.get('website', '')
    )
    return jsonify({'ok': True, 'termos': termos})


def _gerar_termos_ia(empresa_nome: str, descricao: str, website: str) -> list:
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        return _termos_fallback(descricao)
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=500,
            messages=[{'role': 'user', 'content': f"""Você é especialista em prospecção B2B no Brasil.

Empresa: {empresa_nome}
Site: {website}
Descrição: {descricao}

Gere 15 termos de busca Google para encontrar potenciais clientes B2B que precisam deste produto/serviço.
Use variações com estados brasileiros (SP, MG, RJ, PR, RS, GO, MT, SC, BA, PE),
palavras do segmento-alvo e "site:.com.br contato" ou "telefone".

Responda SOMENTE com JSON array de strings. Exemplo: ["termo 1", "termo 2"]"""}]
        )
        text = msg.content[0].text.strip()
        match = re.search(r'\[.*?\]', text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        print(f'[gerar_termos] {e}')
    return _termos_fallback(descricao)


def _termos_fallback(descricao: str) -> list:
    palavras = [w for w in descricao.lower().split() if len(w) > 4][:3]
    estados = ['SP', 'MG', 'PR', 'RS', 'GO', 'SC', 'MT']
    termos = []
    for p in palavras:
        for e in estados[:4]:
            termos.append(f'{p} {e} site:.com.br contato')
    return termos or ['empresa industria site:.com.br contato']


# --- API Tokens ---

@app.route('/api/<bot>/tokens', methods=['GET'])
@login_required
def api_list_tokens(bot):
    uid = session.get('user_id')
    try:
        conn = _conn()
        c = conn.cursor()
        c.execute("""SELECT id, label, ativo, criado_em,
                            '••••' || RIGHT(token, 6) AS token_preview
                     FROM api_tokens WHERE user_id = %s ORDER BY criado_em DESC""", (uid,))
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/<bot>/tokens', methods=['POST'])
@login_required
def api_create_token(bot):
    uid = session.get('user_id')
    data = request.get_json(silent=True) or {}
    label = data.get('label', 'Token API')
    token = secrets.token_urlsafe(32)
    try:
        conn = _conn()
        c = conn.cursor()
        c.execute('INSERT INTO api_tokens (user_id, token, label) VALUES (%s,%s,%s) RETURNING id',
                  (uid, token, label))
        tid = c.fetchone()['id']
        conn.commit()
        conn.close()
        return jsonify({'ok': True, 'id': tid, 'token': token,
                        'aviso': 'Salve este token — não será exibido novamente'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/<bot>/tokens/<int:token_id>', methods=['DELETE'])
@login_required
def api_revoke_token(bot, token_id):
    uid = session.get('user_id')
    try:
        conn = _conn()
        c = conn.cursor()
        c.execute('UPDATE api_tokens SET ativo=FALSE WHERE id=%s AND user_id=%s', (token_id, uid))
        conn.commit()
        conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# =============================================================================
# API PÚBLICA — Bearer token
# =============================================================================

@app.route('/api/v1/leads', methods=['GET'])
@token_required
def public_list_leads():
    schema = request.token_user['schema_name']
    limite = request.args.get('limite', 100, type=int)
    status = request.args.get('status')
    try:
        conn = _conn(schema)
        c = conn.cursor()
        sql = """SELECT id, nome_fantasia, telefone, email, whatsapp, segmento,
                        status, score, cidade, estado, encontrado_em, email_enviado
                 FROM empresas"""
        params = []
        if status:
            sql += ' WHERE status = %s'
            params.append(status)
        sql += ' ORDER BY encontrado_em DESC LIMIT %s'
        params.append(limite)
        c.execute(sql, params)
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return jsonify({'leads': rows, 'total': len(rows)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/v1/leads', methods=['POST'])
@token_required
def public_create_lead():
    schema = request.token_user['schema_name']
    data = request.get_json(silent=True) or {}
    nome = (data.get('nome_fantasia') or '').strip()
    if not nome:
        return jsonify({'error': 'nome_fantasia obrigatorio'}), 400
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute("""INSERT INTO empresas
            (nome_fantasia, email, telefone, whatsapp, segmento, fonte, score, status)
            VALUES (%s,%s,%s,%s,%s,'api',%s,'novo') RETURNING id""",
                  (nome, data.get('email'), data.get('telefone'),
                   data.get('whatsapp'), data.get('segmento', ''), data.get('score', 50)))
        new_id = c.fetchone()['id']
        conn.commit()
        conn.close()
        return jsonify({'ok': True, 'id': new_id}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/v1/leads/<int:lead_id>', methods=['PUT'])
@token_required
def public_update_lead(lead_id):
    schema = request.token_user['schema_name']
    data = request.get_json(silent=True) or {}
    allowed = {'status', 'score', 'segmento', 'demo_status', 'email', 'telefone'}
    fields = {k: v for k, v in data.items() if k in allowed}
    if not fields:
        return jsonify({'error': 'nenhum campo valido'}), 400
    try:
        conn = _conn(schema)
        c = conn.cursor()
        sets = ', '.join(f'{k} = %s' for k in fields)
        c.execute(f'UPDATE empresas SET {sets} WHERE id = %s', list(fields.values()) + [lead_id])
        conn.commit()
        conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# =============================================================================
# HEALTH
# =============================================================================

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'version': '2.0'})


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == '__main__':
    _init_public_schema()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
