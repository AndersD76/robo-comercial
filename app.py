# -*- coding: utf-8 -*-
"""
TurboVenda — SaaS CRM multi-tenant
Prospecção IA + CRM + Email + WhatsApp + Agendamento
"""

import hashlib
import json
import os
import random
import re
import secrets
import subprocess
import sys
import psycopg2
import psycopg2.extras
from functools import wraps
from flask import (Flask, jsonify, redirect, render_template,
                   request, session, url_for)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'mv-saas-2025-change-in-prod')
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

DATABASE_URL = os.environ.get('DATABASE_URL', '')
if not DATABASE_URL:
    print('[FATAL] DATABASE_URL não configurado — defina a variável de ambiente')
if DATABASE_URL.startswith('psql://'):
    DATABASE_URL = 'postgresql://' + DATABASE_URL[7:]
elif DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = 'postgresql://' + DATABASE_URL[11:]

# Processos em background: {schema: {'busca': Popen, 'linkedin': Popen}}
_procs: dict = {}

# Inicializa tabelas globais ao importar (gunicorn não chama __main__)
def _init_public_schema_safe():
    if not DATABASE_URL:
        return
    try:
        conn = psycopg2.connect(DATABASE_URL,
                                cursor_factory=psycopg2.extras.RealDictCursor)
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
        # Migrations planos/pagamentos
        for stmt in [
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
            "plano_expira TIMESTAMP",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
            "mp_customer_id TEXT",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
            "mp_subscription_id TEXT",
            """CREATE TABLE IF NOT EXISTS pagamentos (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(id),
                mp_payment_id TEXT,
                status TEXT,
                valor DECIMAL(10,2),
                plano TEXT,
                criado_em TIMESTAMP DEFAULT NOW()
            )""",
        ]:
            try:
                c.execute(stmt)
            except Exception:
                conn.rollback()
        conn.commit()
        conn.close()
    except Exception as e:
        print(f'[startup] init_public_schema: {e}')

_init_public_schema_safe()


# =============================================================================
# DB HELPERS
# =============================================================================

def _serialize_row(row: dict) -> dict:
    """Converte datetime e outros tipos não-serializáveis para string."""
    for k, v in row.items():
        if v is not None and not isinstance(v, (str, int, float, bool, list, dict)):
            row[k] = str(v)
    return row


def _conn(schema=None):
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
        demo_status TEXT, email_enviado TIMESTAMP,
        observacoes TEXT
    )""")
    # Migrations
    for stmt in [
        "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS observacoes TEXT",
        "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS msg_inicial TEXT",
        "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS email_assunto_padrao TEXT",
        "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS email_html_template TEXT",
        "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS email_remetente TEXT",
        "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS email_remetente_nome TEXT",
        "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS resend_api_key TEXT",
        "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS smtp_host TEXT",
        "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS smtp_port INTEGER DEFAULT 587",
        "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS smtp_user TEXT",
        "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS smtp_password TEXT",
        "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS serper_api_key TEXT",
        "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS wa_enviado TIMESTAMP",
        "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS agenda_token TEXT",
        "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS horario_inicio INTEGER DEFAULT 9",
        "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS horario_fim INTEGER DEFAULT 18",
        "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS duracao_reuniao INTEGER DEFAULT 30",
        "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS dias_semana TEXT DEFAULT '1,2,3,4,5'",
        """CREATE TABLE IF NOT EXISTS agenda (
            id BIGSERIAL PRIMARY KEY,
            empresa_id BIGINT REFERENCES empresas(id) ON DELETE SET NULL,
            titulo TEXT NOT NULL,
            descricao TEXT,
            data_inicio TIMESTAMP NOT NULL,
            data_fim TIMESTAMP,
            tipo TEXT DEFAULT 'reuniao',
            local TEXT,
            concluido BOOLEAN DEFAULT FALSE,
            criado_em TIMESTAMP DEFAULT NOW()
        )""",
        # Enriquecimento
        "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS enriquecido BOOLEAN DEFAULT FALSE",
        "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS enriquecido_em TIMESTAMP",
        "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS natureza_juridica TEXT",
        "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS situacao_cadastral TEXT",
        # Sequencias
        """CREATE TABLE IF NOT EXISTS sequencias (
            id BIGSERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            passos JSONB DEFAULT '[]',
            ativo BOOLEAN DEFAULT TRUE,
            criado_em TIMESTAMP DEFAULT NOW(),
            atualizado_em TIMESTAMP DEFAULT NOW()
        )""",
        """CREATE TABLE IF NOT EXISTS sequencia_leads (
            id BIGSERIAL PRIMARY KEY,
            sequencia_id BIGINT REFERENCES sequencias(id) ON DELETE CASCADE,
            empresa_id BIGINT REFERENCES empresas(id) ON DELETE CASCADE,
            passo_atual INTEGER DEFAULT 0,
            proximo_envio TIMESTAMP,
            status TEXT DEFAULT 'ativo',
            iniciado_em TIMESTAMP DEFAULT NOW(),
            atualizado_em TIMESTAMP DEFAULT NOW(),
            UNIQUE(sequencia_id, empresa_id)
        )""",
    ]:
        try:
            c.execute(stmt)
        except Exception:
            conn.rollback()
    conn.commit()
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
    c.execute("""CREATE TABLE IF NOT EXISTS atividades (
        id BIGSERIAL PRIMARY KEY,
        empresa_id BIGINT REFERENCES empresas(id) ON DELETE CASCADE,
        tipo TEXT,
        descricao TEXT,
        dados JSONB,
        criado_em TIMESTAMP DEFAULT NOW()
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS tarefas (
        id BIGSERIAL PRIMARY KEY,
        empresa_id BIGINT REFERENCES empresas(id) ON DELETE CASCADE,
        tipo TEXT,
        descricao TEXT,
        data_vencimento TIMESTAMP,
        concluida BOOLEAN DEFAULT FALSE,
        concluida_em TIMESTAMP,
        criado_em TIMESTAMP DEFAULT NOW()
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
        msg_inicial TEXT,
        email_assunto_padrao TEXT,
        email_html_template TEXT,
        atualizado_em TIMESTAMP DEFAULT NOW()
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS agenda (
        id BIGSERIAL PRIMARY KEY,
        empresa_id BIGINT REFERENCES empresas(id) ON DELETE SET NULL,
        titulo TEXT NOT NULL,
        descricao TEXT,
        data_inicio TIMESTAMP NOT NULL,
        data_fim TIMESTAMP,
        tipo TEXT DEFAULT 'reuniao',
        local TEXT,
        concluido BOOLEAN DEFAULT FALSE,
        criado_em TIMESTAMP DEFAULT NOW()
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
         'linkedin_total': 0, 'msgs_hoje': 0, 'qualificados': 0}
    if not DATABASE_URL or not schema:
        return z
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute('SELECT COUNT(*) AS n FROM empresas')
        z['total_leads'] = c.fetchone()['n']
        c.execute("SELECT COUNT(*) AS n FROM empresas "
                  "WHERE status IN ('contactada','respondeu','qualificado','convertido')")
        z['contactadas'] = c.fetchone()['n']
        c.execute("SELECT COUNT(*) AS n FROM empresas "
                  "WHERE status IN ('respondeu','qualificado','convertido')")
        z['responderam'] = c.fetchone()['n']
        c.execute("SELECT COUNT(*) AS n FROM empresas "
                  "WHERE status = 'qualificado' OR demo_status = 'confirmado'")
        z['demos'] = c.fetchone()['n']
        c.execute("SELECT COUNT(*) AS n FROM empresas "
                  "WHERE status = 'qualificado'")
        z['qualificados'] = c.fetchone()['n']
        c.execute("SELECT quantidade FROM acoes_diarias "
                  "WHERE data = CURRENT_DATE AND tipo = 'buscas'")
        r = c.fetchone()
        z['buscas_hoje'] = r['quantidade'] if r else 0
        c.execute("SELECT COUNT(*) AS n FROM empresas "
                  "WHERE email_enviado IS NOT NULL")
        z['emails_enviados'] = c.fetchone()['n']
        c.execute("SELECT COUNT(*) AS n FROM empresas "
                  "WHERE email_enviado::date = CURRENT_DATE")
        z['msgs_hoje'] = c.fetchone()['n']
        try:
            c.execute('SELECT COUNT(*) AS n FROM leads_linkedin')
            z['linkedin_total'] = c.fetchone()['n']
        except Exception as e:
            print(f'[stats/{schema}] linkedin_total: {e}')
        conn.close()
    except Exception as e:
        print(f'[stats/{schema}] {e}')
    return z


def get_leads(schema: str, limite: int = 5000) -> list:
    if not DATABASE_URL or not schema:
        return []
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute("""SELECT e.id, e.nome_fantasia, e.whatsapp, e.telefone, e.email, e.score,
                            e.status, e.segmento, e.demo_status, e.cidade, e.estado,
                            e.encontrado_em, e.cnpj, e.razao_social, e.website,
                            e.linkedin, e.instagram, e.fonte, e.porte,
                            e.email_enviado, e.wa_enviado, e.observacoes,
                            (SELECT ct.nome || ' - ' || ct.cargo
                             FROM contatos ct WHERE ct.empresa_id = e.id AND ct.decisor = 1
                             LIMIT 1) AS _decisor
                     FROM empresas e ORDER BY e.encontrado_em DESC LIMIT %s""", (limite,))
        rows = [_serialize_row(dict(r)) for r in c.fetchall()]
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
        rows = [_serialize_row(dict(r)) for r in c.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        print(f'[logs/{schema}] {e}')
        return []


def get_bot_config(schema: str) -> dict:
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute('SELECT * FROM bot_config ORDER BY id DESC LIMIT 1')
        row = c.fetchone()
        conn.close()
        return _serialize_row(dict(row)) if row else {}
    except Exception as e:
        print(f'[bot_config/{schema}] {e}')
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
                # Rodar migrations no schema do usuário
                if user.get('schema_name'):
                    try:
                        _init_user_schema(user['schema_name'])
                    except Exception:
                        pass
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


@app.route('/admin/users')
def admin_users():
    secret = request.args.get('key', '')
    admin_key = os.environ.get('ADMIN_KEY', 'trocar123')
    if secret != admin_key:
        return jsonify({'error': 'unauthorized'}), 401
    try:
        conn = _conn()
        c = conn.cursor()
        c.execute('SELECT id, email, empresa_nome, plano, ativo, criado_em FROM users ORDER BY id')
        users = c.fetchall()
        conn.close()
        for u in users:
            if u.get('criado_em'):
                u['criado_em'] = str(u['criado_em'])
        return jsonify(users)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


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
    print(f'[dashboard] user_id={session.get("user_id")} schema={user.get("schema_name") if user else "NO_USER"}', flush=True)
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


@app.route('/api/pipeline')
@login_required
def api_pipeline():
    schema = _get_schema()
    if not schema:
        return jsonify({})
    stages = ['novo', 'contactada', 'respondeu', 'qualificado', 'demo', 'convertido']
    per_page = request.args.get('per_page', 50, type=int)
    try:
        conn = _conn(schema)
        c = conn.cursor()
        result = {}
        for st in stages:
            page = request.args.get(f'page_{st}', 1, type=int)
            offset = (page - 1) * per_page
            c.execute("SELECT COUNT(*) AS total FROM empresas WHERE status=%s", (st,))
            total = c.fetchone()['total']
            c.execute("""SELECT e.id, e.nome_fantasia, e.segmento, e.cidade, e.estado,
                                e.telefone, e.whatsapp, e.email, e.score, e.status,
                                e.email_enviado, e.wa_enviado,
                                e.encontrado_em, e.cnpj, e.observacoes,
                                e.website,
                                (SELECT ct.nome || ' - ' || ct.cargo
                                 FROM contatos ct WHERE ct.empresa_id = e.id AND ct.decisor = 1
                                 LIMIT 1) AS _decisor
                         FROM empresas e WHERE e.status=%s
                         ORDER BY e.score DESC, e.encontrado_em DESC
                         LIMIT %s OFFSET %s""", (st, per_page, offset))
            result[st] = {
                'leads': [_serialize_row(dict(r)) for r in c.fetchall()],
                'total': total,
                'page': page,
                'pages': max(1, (total + per_page - 1) // per_page)
            }
        conn.close()
        return jsonify(result)
    except Exception as e:
        print(f'[pipeline/{schema}] {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/api/<bot>/leads')
@login_required
def api_leads(bot):
    schema = _get_schema() or bot
    limite = request.args.get('limite', 5000, type=int)
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
        'busca': _proc_running(schema, 'busca'),
    })


@app.route('/api/<bot>/start', methods=['POST'])
@login_required
def api_bot_start(bot):
    schema = _get_schema() or bot
    data = request.get_json(silent=True) or {}
    canal = data.get('canal', 'busca')
    if canal not in ('busca', 'linkedin', 'wa'):
        return jsonify({'error': 'canal inválido (busca|linkedin|wa)'}), 400
    if _proc_running(schema, canal):
        return jsonify({'status': 'already_running'})

    base = os.path.dirname(os.path.abspath(__file__))
    bot_dir = os.path.join(base, 'robo_pili')
    scripts = {'busca': 'run_busca.py', 'linkedin': 'run_linkedin.py', 'wa': 'run_full.py'}
    script = scripts[canal]
    log_path = os.path.join(bot_dir, f'{canal}.log')
    log_file = open(log_path, 'a', encoding='utf-8')
    try:
        proc = subprocess.Popen(
            [sys.executable, '-u', script, '--schema', schema],
            cwd=bot_dir, stdout=log_file, stderr=subprocess.STDOUT,
        )
    except Exception as e:
        log_file.close()
        return jsonify({'error': str(e)}), 500
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
    canal = request.args.get('canal', 'busca')
    n = request.args.get('n', 60, type=int)
    base = os.path.dirname(os.path.abspath(__file__))
    log_path = os.path.join(base, 'robo_pili', f'{canal}.log')
    try:
        with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        return jsonify({'lines': [ln.rstrip('\n') for ln in lines[-n:]]})
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
            (nome_fantasia, whatsapp, email, telefone, segmento, fonte, score, status,
             cnpj, observacoes, website, cidade, estado)
            VALUES (%s,%s,%s,%s,%s,'manual',%s,'novo',%s,%s,%s,%s,%s) RETURNING id""",
                  (nome, wa, data.get('email') or None,
                   data.get('telefone'), data.get('segmento', ''), data.get('score', 50),
                   data.get('cnpj') or None, data.get('observacoes') or None,
                   data.get('website') or None, data.get('cidade') or None,
                   data.get('estado') or None))
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
               'instagram', 'porte', 'demo_status', 'cnpj', 'observacoes'}
    fields = {k: v for k, v in data.items() if k in allowed}
    if not fields:
        return jsonify({'error': 'nenhum campo valido'}), 400
    try:
        conn = _conn(schema)
        c = conn.cursor()
        # Auto-log status change as atividade
        if 'status' in fields:
            c.execute('SELECT status FROM empresas WHERE id = %s', (lead_id,))
            old = c.fetchone()
            old_st = old['status'] if old else '?'
            new_st = fields['status']
            if old_st != new_st:
                c.execute("""INSERT INTO atividades
                    (empresa_id, tipo, descricao, dados)
                    VALUES (%s, 'status_change', %s, %s)""",
                    (lead_id, f'{old_st} -> {new_st}',
                     json.dumps({'de': old_st, 'para': new_st})))
                # Auto-enroll em sequências ativas
                if new_st == 'contactada':
                    c.execute("""SELECT id, passos
                        FROM sequencias WHERE ativo = TRUE""")
                    for seq in c.fetchall():
                        ps = seq['passos']
                        if isinstance(ps, str):
                            ps = json.loads(ps)
                        if ps:
                            d0 = ps[0].get('dia', 0)
                            try:
                                c.execute("""INSERT INTO
                                    sequencia_leads
                                    (sequencia_id, empresa_id,
                                     passo_atual, proximo_envio)
                                    VALUES (%s, %s, 0,
                                        NOW() + INTERVAL '%s days')
                                    ON CONFLICT
                                    (sequencia_id, empresa_id)
                                    DO NOTHING""",
                                    (seq['id'], lead_id, d0))
                            except Exception:
                                pass
        # Auto-log observacoes as note
        if 'observacoes' in fields and fields['observacoes']:
            c.execute("""INSERT INTO atividades (empresa_id, tipo, descricao)
                         VALUES (%s, 'nota', %s)""",
                      (lead_id, fields['observacoes']))
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


@app.route('/api/<bot>/clear-all', methods=['POST'])
@login_required
def api_clear_all(bot):
    """Limpa todos os leads, contatos, interações, buscas, logs e contadores."""
    schema = _get_schema() or bot
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute('DELETE FROM atividades')
        c.execute('DELETE FROM tarefas')
        c.execute('DELETE FROM interacoes')
        c.execute('DELETE FROM contatos')
        c.execute('DELETE FROM leads_linkedin')
        c.execute('DELETE FROM empresas')
        c.execute('DELETE FROM buscas')
        c.execute('DELETE FROM logs')
        c.execute('DELETE FROM acoes_diarias')
        conn.commit()
        conn.close()
        return jsonify({'ok': True, 'msg': 'Tudo limpo'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# --- Atividades (Timeline) ---

@app.route('/api/<bot>/lead/<int:lead_id>/atividades')
@login_required
def api_lead_atividades(bot, lead_id):
    schema = _get_schema() or bot
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute("""SELECT id, tipo, descricao, dados, criado_em
                     FROM atividades WHERE empresa_id = %s
                     ORDER BY criado_em DESC LIMIT 50""", (lead_id,))
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/<bot>/lead/<int:lead_id>/atividade', methods=['POST'])
@login_required
def api_add_atividade(bot, lead_id):
    schema = _get_schema() or bot
    data = request.get_json(silent=True) or {}
    tipo = data.get('tipo', 'nota')
    descricao = (data.get('descricao') or '').strip()
    if not descricao:
        return jsonify({'error': 'descricao obrigatória'}), 400
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute("""INSERT INTO atividades (empresa_id, tipo, descricao, dados)
                     VALUES (%s, %s, %s, %s) RETURNING id""",
                  (lead_id, tipo, descricao, json.dumps(data.get('dados') or {})))
        aid = c.fetchone()['id']
        conn.commit()
        conn.close()
        return jsonify({'ok': True, 'id': aid})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# --- Tarefas ---

@app.route('/api/<bot>/lead/<int:lead_id>/tarefas')
@login_required
def api_lead_tarefas(bot, lead_id):
    schema = _get_schema() or bot
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute("""SELECT id, tipo, descricao, data_vencimento, concluida, criado_em
                     FROM tarefas WHERE empresa_id = %s
                     ORDER BY concluida ASC, data_vencimento ASC NULLS LAST""", (lead_id,))
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/<bot>/lead/<int:lead_id>/tarefa', methods=['POST'])
@login_required
def api_add_tarefa(bot, lead_id):
    schema = _get_schema() or bot
    data = request.get_json(silent=True) or {}
    descricao = (data.get('descricao') or '').strip()
    if not descricao:
        return jsonify({'error': 'descricao obrigatória'}), 400
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute("""INSERT INTO tarefas (empresa_id, tipo, descricao, data_vencimento)
                     VALUES (%s, %s, %s, %s) RETURNING id""",
                  (lead_id, data.get('tipo', 'outro'), descricao,
                   data.get('data_vencimento') or None))
        tid = c.fetchone()['id']
        conn.commit()
        conn.close()
        return jsonify({'ok': True, 'id': tid})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/<bot>/tarefa/<int:tarefa_id>', methods=['PUT'])
@login_required
def api_update_tarefa(bot, tarefa_id):
    schema = _get_schema() or bot
    data = request.get_json(silent=True) or {}
    try:
        conn = _conn(schema)
        c = conn.cursor()
        if 'concluida' in data:
            c.execute("""UPDATE tarefas SET concluida = %s,
                         concluida_em = CASE WHEN %s THEN NOW() ELSE NULL END
                         WHERE id = %s""",
                      (data['concluida'], data['concluida'], tarefa_id))
        if 'descricao' in data:
            c.execute('UPDATE tarefas SET descricao = %s WHERE id = %s',
                      (data['descricao'], tarefa_id))
        conn.commit()
        conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/<bot>/tarefa/<int:tarefa_id>', methods=['DELETE'])
@login_required
def api_delete_tarefa(bot, tarefa_id):
    schema = _get_schema() or bot
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute('DELETE FROM tarefas WHERE id = %s', (tarefa_id,))
        conn.commit()
        conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/<bot>/tarefas/pendentes')
@login_required
def api_tarefas_pendentes(bot):
    schema = _get_schema() or bot
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute("""SELECT t.id, t.tipo, t.descricao, t.data_vencimento, t.criado_em,
                            e.nome_fantasia, e.id AS empresa_id
                     FROM tarefas t JOIN empresas e ON t.empresa_id = e.id
                     WHERE t.concluida = FALSE
                     ORDER BY t.data_vencimento ASC NULLS LAST LIMIT 50""")
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# --- Enriquecimento CNPJ ---

@app.route('/api/<bot>/lead/<int:lead_id>/enriquecer', methods=['POST'])
@login_required
def api_enriquecer_lead(bot, lead_id):
    schema = _get_schema() or bot
    result = _enriquecer_cnpj(schema, lead_id)
    if result.get('ok'):
        return jsonify(result)
    return jsonify(result), 400


# --- Relatórios ---

@app.route('/api/<bot>/relatorios')
@login_required
def api_relatorios(bot):
    schema = _get_schema() or bot
    try:
        conn = _conn(schema)
        c = conn.cursor()
        # Funil
        c.execute("""SELECT status, COUNT(*) as total
            FROM empresas GROUP BY status""")
        funil_raw = {r['status']: r['total'] for r in c.fetchall()}
        etapas = ['novo', 'contactada', 'respondeu',
                  'qualificado', 'demo', 'convertido']
        funil = []
        for et in etapas:
            funil.append({'etapa': et, 'total': funil_raw.get(et, 0)})

        # Leads por fonte
        c.execute("""SELECT COALESCE(fonte, 'desconhecido') AS fonte,
            COUNT(*) AS total FROM empresas
            GROUP BY fonte ORDER BY total DESC LIMIT 10""")
        por_fonte = [dict(r) for r in c.fetchall()]

        # Leads por dia (ultimos 30 dias)
        c.execute("""SELECT DATE(encontrado_em) AS data,
            COUNT(*) AS total FROM empresas
            WHERE encontrado_em >= NOW() - INTERVAL '30 days'
            GROUP BY DATE(encontrado_em)
            ORDER BY data""")
        por_dia = [{'data': str(r['data']), 'total': r['total']}
                   for r in c.fetchall()]

        # Métricas email
        c.execute("""SELECT
            COUNT(*) FILTER (WHERE email_enviado IS NOT NULL)
                AS emails_enviados,
            COUNT(*) FILTER (WHERE email_enviado IS NOT NULL
                AND status IN ('respondeu','qualificado',
                    'demo','convertido'))
                AS emails_respondidos
            FROM empresas""")
        em = dict(c.fetchone())

        # Métricas WhatsApp
        c.execute("""SELECT
            COUNT(*) FILTER (WHERE wa_enviado IS NOT NULL)
                AS wa_enviados,
            COUNT(*) FILTER (WHERE wa_enviado IS NOT NULL
                AND status IN ('respondeu','qualificado',
                    'demo','convertido'))
                AS wa_respondidos
            FROM empresas""")
        wm = dict(c.fetchone())

        # Top termos de busca
        c.execute("""SELECT termo,
            SUM(resultados) AS total_resultados,
            COUNT(*) AS vezes_buscado
            FROM buscas GROUP BY termo
            ORDER BY total_resultados DESC LIMIT 15""")
        top_termos = [dict(r) for r in c.fetchall()]

        # Tempo médio por etapa (via atividades)
        c.execute("""WITH diffs AS (
            SELECT dados->>'de' AS de_st,
                   dados->>'para' AS para_st,
                   criado_em - LAG(criado_em) OVER
                       (PARTITION BY empresa_id
                        ORDER BY criado_em) AS diff
            FROM atividades WHERE tipo = 'status_change'
        )
        SELECT de_st, para_st,
            AVG(EXTRACT(EPOCH FROM diff)) / 3600.0
                AS avg_horas
        FROM diffs WHERE diff IS NOT NULL
        GROUP BY de_st, para_st
        ORDER BY avg_horas""")
        tempo_etapas = [{'de': r['de_st'],
                         'para': r['para_st'],
                         'horas': round(r['avg_horas'] or 0, 1)}
                        for r in c.fetchall()]

        # Enriquecimento
        c.execute("""SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE enriquecido = TRUE)
                AS enriquecidos
            FROM empresas""")
        enr = dict(c.fetchone())

        # Sequências
        c.execute("""SELECT
            COUNT(*) AS total_sequencias,
            (SELECT COUNT(*) FROM sequencia_leads
                WHERE status = 'ativo') AS leads_ativos,
            (SELECT COUNT(*) FROM sequencia_leads
                WHERE status = 'concluido') AS leads_concluidos
            FROM sequencias WHERE ativo = TRUE""")
        seq_row = c.fetchone()
        seq_metrics = dict(seq_row) if seq_row else {
            'total_sequencias': 0,
            'leads_ativos': 0,
            'leads_concluidos': 0}

        conn.close()
        total = sum(f['total'] for f in funil)
        return jsonify({
            'funil': funil, 'total_leads': total,
            'por_fonte': por_fonte, 'por_dia': por_dia,
            'email': em, 'whatsapp': wm,
            'top_termos': top_termos,
            'tempo_etapas': tempo_etapas,
            'enriquecimento': enr,
            'sequencias': seq_metrics,
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# --- Sequências de Email ---

@app.route('/api/<bot>/sequencias')
@login_required
def api_list_sequencias(bot):
    schema = _get_schema() or bot
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute("""SELECT s.*,
            (SELECT COUNT(*) FROM sequencia_leads sl
             WHERE sl.sequencia_id = s.id
             AND sl.status = 'ativo') AS leads_ativos,
            (SELECT COUNT(*) FROM sequencia_leads sl
             WHERE sl.sequencia_id = s.id) AS leads_total
            FROM sequencias s ORDER BY s.criado_em DESC""")
        rows = [_serialize_row(dict(r)) for r in c.fetchall()]
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/<bot>/sequencias', methods=['POST'])
@login_required
def api_create_sequencia(bot):
    schema = _get_schema() or bot
    data = request.get_json(silent=True) or {}
    nome = data.get('nome', '').strip()
    passos = data.get('passos', [])
    if not nome:
        return jsonify({'error': 'nome obrigatorio'}), 400
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute("""INSERT INTO sequencias (nome, passos)
            VALUES (%s, %s) RETURNING id""",
            (nome, json.dumps(passos)))
        seq_id = c.fetchone()['id']
        conn.commit()
        conn.close()
        return jsonify({'ok': True, 'id': seq_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/<bot>/sequencia/<int:seq_id>', methods=['PUT'])
@login_required
def api_update_sequencia(bot, seq_id):
    schema = _get_schema() or bot
    data = request.get_json(silent=True) or {}
    try:
        conn = _conn(schema)
        c = conn.cursor()
        sets, vals = [], []
        if 'nome' in data:
            sets.append('nome = %s')
            vals.append(data['nome'])
        if 'passos' in data:
            sets.append('passos = %s')
            vals.append(json.dumps(data['passos']))
        if 'ativo' in data:
            sets.append('ativo = %s')
            vals.append(data['ativo'])
        sets.append('atualizado_em = NOW()')
        vals.append(seq_id)
        c.execute(f"UPDATE sequencias SET {', '.join(sets)}"
                  f" WHERE id = %s", vals)
        conn.commit()
        conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/<bot>/sequencia/<int:seq_id>', methods=['DELETE'])
@login_required
def api_delete_sequencia(bot, seq_id):
    schema = _get_schema() or bot
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute('DELETE FROM sequencias WHERE id = %s', (seq_id,))
        conn.commit()
        conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/<bot>/sequencia/<int:seq_id>/enroll',
           methods=['POST'])
@login_required
def api_enroll_leads(bot, seq_id):
    schema = _get_schema() or bot
    data = request.get_json(silent=True) or {}
    lead_ids = data.get('lead_ids', [])
    if not lead_ids:
        return jsonify({'error': 'nenhum lead'}), 400
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute('SELECT passos FROM sequencias WHERE id = %s',
                  (seq_id,))
        seq = c.fetchone()
        if not seq:
            conn.close()
            return jsonify({'error': 'sequencia nao encontrada'}), 404
        passos = seq['passos']
        if isinstance(passos, str):
            passos = json.loads(passos)
        dia_0 = passos[0].get('dia', 0) if passos else 0
        enrolled = 0
        for lid in lead_ids:
            try:
                c.execute("""INSERT INTO sequencia_leads
                    (sequencia_id, empresa_id, passo_atual,
                     proximo_envio)
                    VALUES (%s, %s, 0,
                        NOW() + INTERVAL '%s days')
                    ON CONFLICT (sequencia_id, empresa_id)
                    DO NOTHING""",
                    (seq_id, lid, dia_0))
                enrolled += 1
            except Exception:
                conn.rollback()
        conn.commit()
        conn.close()
        return jsonify({'ok': True, 'enrolled': enrolled})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/<bot>/sequencia/<int:seq_id>/leads')
@login_required
def api_sequencia_leads(bot, seq_id):
    schema = _get_schema() or bot
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute("""SELECT sl.*, e.nome_fantasia, e.email
            FROM sequencia_leads sl
            JOIN empresas e ON sl.empresa_id = e.id
            WHERE sl.sequencia_id = %s
            ORDER BY sl.proximo_envio ASC""", (seq_id,))
        rows = [_serialize_row(dict(r)) for r in c.fetchall()]
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/<bot>/sequencias/processar', methods=['POST'])
@login_required
def api_processar_sequencias(bot):
    schema = _get_schema() or bot
    return _processar_sequencias_schema(schema)


def _processar_sequencias_schema(schema):
    """Processa envios pendentes de sequencias."""
    ecfg = _get_email_config(schema)
    has_smtp = ecfg.get('smtp_host') and ecfg.get('smtp_user')
    has_resend = bool(ecfg.get('resend_api_key'))
    if not has_smtp and not has_resend:
        return jsonify({'error': 'Email nao configurado'}), 400
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute("""SELECT sl.id, sl.sequencia_id, sl.empresa_id,
            sl.passo_atual, s.passos, s.nome AS seq_nome,
            e.nome_fantasia, e.email
            FROM sequencia_leads sl
            JOIN sequencias s ON sl.sequencia_id = s.id
            JOIN empresas e ON sl.empresa_id = e.id
            WHERE sl.status = 'ativo'
            AND sl.proximo_envio <= NOW()
            AND e.email IS NOT NULL
            AND s.ativo = TRUE
            ORDER BY sl.proximo_envio ASC
            LIMIT 50""")
        pendentes = c.fetchall()
        enviados = erros = 0
        for p in pendentes:
            passos = p['passos']
            if isinstance(passos, str):
                passos = json.loads(passos)
            idx = p['passo_atual']
            if idx >= len(passos):
                c.execute("""UPDATE sequencia_leads
                    SET status = 'concluido',
                    atualizado_em = NOW()
                    WHERE id = %s""", (p['id'],))
                continue
            passo = passos[idx]
            nome = p['nome_fantasia'] or 'empresa'
            link_agenda = _get_link_agenda(schema, p['empresa_id'])
            assunto = (passo.get('assunto', '')
                .replace('{{nome}}', nome)
                .replace('{{link_agenda}}', link_agenda))
            html = (passo.get('html_template', '')
                .replace('{{nome}}', nome)
                .replace('{{link_agenda}}', link_agenda))
            try:
                ok = _send_email(ecfg, p['email'], nome,
                                 assunto, html)
                if ok:
                    enviados += 1
                    next_idx = idx + 1
                    if next_idx >= len(passos):
                        c.execute("""UPDATE sequencia_leads
                            SET passo_atual = %s,
                            status = 'concluido',
                            atualizado_em = NOW()
                            WHERE id = %s""",
                            (next_idx, p['id']))
                    else:
                        next_dia = passos[next_idx].get('dia', 0)
                        dias_diff = next_dia - passo.get('dia', 0)
                        c.execute("""UPDATE sequencia_leads
                            SET passo_atual = %s,
                            proximo_envio = NOW()
                                + INTERVAL '%s days',
                            atualizado_em = NOW()
                            WHERE id = %s""",
                            (next_idx, dias_diff, p['id']))
                    c.execute("""UPDATE empresas
                        SET email_enviado = NOW(),
                        status = CASE WHEN status = 'novo'
                            THEN 'contactada' ELSE status END
                        WHERE id = %s""", (p['empresa_id'],))
                    c.execute("""INSERT INTO atividades
                        (empresa_id, tipo, descricao) VALUES
                        (%s, 'sequencia', %s)""",
                        (p['empresa_id'],
                         f"Seq '{p['seq_nome']}' passo "
                         f"{idx+1}: {assunto}"))
                else:
                    erros += 1
            except Exception as e:
                print(f'[seq] erro: {e}', flush=True)
                erros += 1
        conn.commit()
        conn.close()
        return jsonify({'ok': True,
                        'enviados': enviados, 'erros': erros})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# --- CSV Export ---

@app.route('/api/<bot>/leads/export')
@login_required
def api_export_leads(bot):
    import io
    import csv
    schema = _get_schema() or bot
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute("""SELECT e.nome_fantasia, e.cnpj, e.telefone, e.whatsapp, e.email,
                            e.website, e.cidade, e.estado, e.segmento, e.score, e.status,
                            e.observacoes, e.encontrado_em, e.email_enviado,
                            (SELECT ct.nome || ' - ' || ct.cargo
                             FROM contatos ct WHERE ct.empresa_id = e.id AND ct.decisor = 1
                             LIMIT 1) AS decisor
                     FROM empresas e ORDER BY e.encontrado_em DESC""")
        rows = c.fetchall()
        conn.close()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Empresa', 'CNPJ', 'Telefone', 'WhatsApp', 'Email',
                         'Website', 'Cidade', 'Estado', 'Segmento', 'Score', 'Status',
                         'Observações', 'Encontrado em', 'Email enviado', 'Decisor'])
        for r in rows:
            writer.writerow([r.get('nome_fantasia', ''), r.get('cnpj', ''),
                             r.get('telefone', ''), r.get('whatsapp', ''),
                             r.get('email', ''), r.get('website', ''),
                             r.get('cidade', ''), r.get('estado', ''),
                             r.get('segmento', ''), r.get('score', ''),
                             r.get('status', ''), r.get('observacoes', ''),
                             str(r.get('encontrado_em') or ''),
                             str(r.get('email_enviado') or ''),
                             r.get('decisor', '')])
        from flask import Response
        return Response(output.getvalue(),
                        mimetype='text/csv',
                        headers={'Content-Disposition': 'attachment;filename=leads.csv'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# --- Bulk Actions ---

@app.route('/api/<bot>/leads/bulk', methods=['POST'])
@login_required
def api_bulk_action(bot):
    schema = _get_schema() or bot
    data = request.get_json(silent=True) or {}
    ids = data.get('ids', [])
    action = data.get('action', '')
    if not ids:
        return jsonify({'error': 'nenhum lead selecionado'}), 400
    try:
        conn = _conn(schema)
        c = conn.cursor()
        ph = ','.join(['%s'] * len(ids))
        if action == 'delete':
            c.execute(f'DELETE FROM atividades WHERE empresa_id IN ({ph})', ids)
            c.execute(f'DELETE FROM tarefas WHERE empresa_id IN ({ph})', ids)
            c.execute(f'DELETE FROM interacoes WHERE empresa_id IN ({ph})', ids)
            c.execute(f'DELETE FROM contatos WHERE empresa_id IN ({ph})', ids)
            c.execute(f'DELETE FROM empresas WHERE id IN ({ph})', ids)
            conn.commit()
            conn.close()
            return jsonify({'ok': True, 'msg': f'{len(ids)} leads excluídos'})
        elif action == 'status' and data.get('status'):
            new_st = data['status']
            for lid in ids:
                c.execute('SELECT status FROM empresas WHERE id = %s', (lid,))
                old = c.fetchone()
                if old and old['status'] != new_st:
                    c.execute("""INSERT INTO atividades (empresa_id, tipo, descricao, dados)
                                 VALUES (%s, 'status_change', %s, %s)""",
                              (lid, f'{old["status"]} → {new_st}',
                               json.dumps({'de': old['status'], 'para': new_st})))
            c.execute(f'UPDATE empresas SET status = %s WHERE id IN ({ph})',
                      [new_st] + ids)
            conn.commit()
            conn.close()
            return jsonify({'ok': True, 'msg': f'{len(ids)} leads → {new_st}'})
        else:
            conn.close()
            return jsonify({'error': 'action inválida'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# --- Email em massa ---

def _get_email_config(schema: str) -> dict:
    """Lê config de email do user (bot_config)."""
    cfg = get_bot_config(schema) if schema else {}
    return {
        'sender_email': (cfg.get('email_remetente') or
                         os.environ.get('EMAIL_FROM', '')),
        'sender_name': (cfg.get('email_remetente_nome') or
                        cfg.get('empresa_nome') or ''),
        'smtp_host': cfg.get('smtp_host') or '',
        'smtp_port': cfg.get('smtp_port') or 587,
        'smtp_user': cfg.get('smtp_user') or '',
        'smtp_password': cfg.get('smtp_password') or '',
        'resend_api_key': os.environ.get('RESEND_API_KEY', '') or cfg.get('resend_api_key') or '',
    }


def _send_email(ecfg, to_email, to_name, subject, html):
    """Envia email via Resend API (prioridade) ou SMTP direto."""
    sender_email = ecfg.get('sender_email', '')
    sender_name = ecfg.get('sender_name', '')
    print(f'[EMAIL] to={to_email} from={sender_email}', flush=True)
    if not sender_email:
        return False

    # Opção 1: Resend API (prioridade — SMTP bloqueado no Railway)
    resend_key = ecfg.get('resend_api_key', '')
    if resend_key:
        try:
            import requests as http
            r = http.post('https://api.resend.com/emails',
                          headers={'Authorization': f'Bearer {resend_key}',
                                   'Content-Type': 'application/json'},
                          json={'from': f'{sender_name} <{sender_email}>',
                                'to': [to_email],
                                'subject': subject,
                                'html': html},
                          timeout=15)
            if r.status_code in (200, 201):
                print(f'[RESEND] OK enviado para {to_email}', flush=True)
                return True
            else:
                print(f'[RESEND] erro {r.status_code}: {r.text}', flush=True)
        except Exception as e:
            print(f'[RESEND] erro: {e}', flush=True)

    # Opção 2: SMTP direto (fallback — funciona fora do Railway)
    smtp_host = ecfg.get('smtp_host', '')
    smtp_user = ecfg.get('smtp_user', '')
    smtp_pass = ecfg.get('smtp_password', '')
    if smtp_host and smtp_user and smtp_pass:
        try:
            import smtplib
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText
            msg = MIMEMultipart('alternative')
            msg['From'] = f'{sender_name} <{sender_email}>'
            msg['To'] = to_email
            msg['Subject'] = subject
            msg.attach(MIMEText(html, 'html', 'utf-8'))
            port = int(ecfg.get('smtp_port', 587))
            ports_to_try = [port]
            if port == 465:
                ports_to_try.append(587)
            for p in ports_to_try:
                try:
                    if p == 465:
                        with smtplib.SMTP_SSL(smtp_host, p, timeout=15) as s:
                            s.login(smtp_user, smtp_pass)
                            s.sendmail(sender_email, to_email, msg.as_string())
                    else:
                        with smtplib.SMTP(smtp_host, p, timeout=15) as s:
                            s.ehlo()
                            s.starttls()
                            s.login(smtp_user, smtp_pass)
                            s.sendmail(sender_email, to_email, msg.as_string())
                    print(f'[SMTP] OK porta {p}', flush=True)
                    return True
                except Exception as e:
                    print(f'[SMTP] porta {p} erro: {e}', flush=True)
                    continue
        except Exception as e:
            print(f'[SMTP] erro geral: {e}', flush=True)

    print('[EMAIL] nenhum método de envio disponível', flush=True)
    return False


@app.route('/api/<bot>/send-emails', methods=['POST'])
@login_required
def api_send_emails(bot):
    schema = _get_schema() or bot
    data = request.get_json(silent=True) or {}
    lead_ids = data.get('ids', [])
    if not lead_ids:
        return jsonify({'error': 'nenhum lead selecionado'}), 400
    ecfg = _get_email_config(schema)
    has_smtp = ecfg.get('smtp_host') and ecfg.get('smtp_user')
    has_resend = bool(ecfg.get('resend_api_key'))
    if not has_smtp and not has_resend:
        return jsonify({'error': 'Email não configurado. Verifique a variável RESEND_API_KEY ou configure SMTP.'}), 400
    if not ecfg['sender_email']:
        return jsonify({'error': 'Configure seu email remetente em Configurações'}), 400

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

    empresa_nome = user['empresa_nome'] if user else ''
    enviados = erros = 0
    for lead in leads:
        nome = lead['nome_fantasia'] or 'empresa'
        link_agenda = _get_link_agenda(schema, lead['id'])
        html = (tpl_html.replace('{{nome}}', nome)
                        .replace('{{DEMO_CAL_LINK}}', link_agenda)
                        .replace('{{cal_link}}', link_agenda)
                        .replace('{{link_agenda}}', link_agenda)
                        .replace('{{EMPRESA}}', empresa_nome))
        try:
            ok = _send_email(ecfg, lead['email'], nome,
                             f'{nome}, conheça {empresa_nome}', html)
            if ok:
                enviados += 1
                try:
                    conn2 = _conn(schema)
                    c2 = conn2.cursor()
                    c2.execute("""UPDATE empresas
                        SET email_enviado = NOW(),
                            status = CASE WHEN status = 'novo'
                                THEN 'contactada' ELSE status END
                        WHERE id = %s""", (lead['id'],))
                    c2.execute("""INSERT INTO atividades
                        (empresa_id, tipo, descricao)
                        VALUES (%s, 'email', 'Email enviado')""",
                        (lead['id'],))
                    conn2.commit()
                finally:
                    conn2.close()
            else:
                erros += 1
        except Exception as e:
            print(f'[send-emails] erro lead {lead["id"]}: {e}')
            erros += 1
    return jsonify({'ok': True, 'enviados': enviados, 'erros': erros})


@app.route('/api/<bot>/email/campanha', methods=['POST'])
@login_required
def api_email_campanha(bot):
    schema = _get_schema() or bot
    data = request.get_json(silent=True) or {}
    assunto = data.get('assunto', '').strip()
    corpo = data.get('corpo', '').strip()
    html_template = data.get('html_template', '').strip()
    if not assunto:
        return jsonify({'error': 'assunto é obrigatório'}), 400
    if not corpo and not html_template:
        return jsonify({'error': 'corpo ou template HTML é obrigatório'}), 400

    ecfg = _get_email_config(schema)
    has_smtp = ecfg.get('smtp_host') and ecfg.get('smtp_user')
    has_resend = bool(ecfg.get('resend_api_key'))
    if not has_smtp and not has_resend:
        return jsonify({'error': 'Email não configurado. Verifique a variável RESEND_API_KEY ou configure SMTP.'}), 400
    if not ecfg['sender_email']:
        return jsonify({'error': 'Configure seu email remetente em Configurações'}), 400

    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute("""SELECT id, nome_fantasia, email, segmento, cidade, estado
                     FROM empresas WHERE email IS NOT NULL AND email != ''
                     ORDER BY score DESC LIMIT 500""")
        leads = c.fetchall()
        conn.close()
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    if not leads:
        return jsonify({'error': 'nenhum lead com email cadastrado'}), 400

    enviados = erros = 0
    for lead in leads:
        nome = lead['nome_fantasia'] or 'empresa'
        link_agenda = _get_link_agenda(schema, lead['id'])
        vars_map = {
            '{{nome}}': nome,
            '{{email}}': lead['email'] or '',
            '{{segmento}}': lead.get('segmento') or '',
            '{{cidade}}': lead.get('cidade') or '',
            '{{link_agenda}}': link_agenda,
            '{{cal_link}}': link_agenda,
            '{{DEMO_CAL_LINK}}': link_agenda,
        }
        if html_template:
            html = html_template
            for k, v in vars_map.items():
                html = html.replace(k, v)
        else:
            corpo_esc = corpo.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            corpo_html = '<br>'.join(corpo_esc.split('\n'))
            for k, v in vars_map.items():
                corpo_html = corpo_html.replace(k, v)
            html = f'<div style="font-family:sans-serif;font-size:15px;line-height:1.6;color:#333">{corpo_html}</div>'

        subj = assunto
        for k, v in vars_map.items():
            subj = subj.replace(k, v)

        try:
            ok = _send_email(
                ecfg, lead['email'], nome, subj, html)
            if ok:
                enviados += 1
                try:
                    conn2 = _conn(schema)
                    c2 = conn2.cursor()
                    c2.execute(
                        "UPDATE empresas SET email_enviado = NOW(),"
                        " status = CASE WHEN status = 'novo'"
                        " THEN 'contactada' ELSE status END"
                        " WHERE id = %s", (lead['id'],))
                    c2.execute(
                        "INSERT INTO atividades "
                        "(empresa_id, tipo, descricao) "
                        "VALUES (%s, 'email', %s)",
                        (lead['id'], f'Campanha: {subj}'))
                    conn2.commit()
                finally:
                    conn2.close()
            else:
                erros += 1
        except Exception as e:
            print(f'[campanha] erro lead {lead["id"]}: {e}')
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
    termos = data.get('termos_busca') or None  # None = não alterar
    li_email = data.get('linkedin_email', '')
    li_password = data.get('linkedin_password', '')
    li_cargos = data.get('linkedin_cargos') or []
    msg_inicial = data.get('msg_inicial', '')
    email_assunto = data.get('email_assunto_padrao', '')
    email_html = data.get('email_html_template', '')
    email_remetente = data.get('email_remetente', '')
    email_remetente_nome = data.get('email_remetente_nome', '')
    resend_api_key = data.get('resend_api_key', '')
    smtp_host = data.get('smtp_host', '')
    smtp_port = data.get('smtp_port', 587)
    smtp_user = data.get('smtp_user', '')
    smtp_password = data.get('smtp_password', '')
    serper_api_key = data.get('serper_api_key', '')

    conn = None
    try:
        print(f'[save_config/{schema}] Iniciando save...', flush=True)
        conn = _conn(schema)
        c = conn.cursor()
        c.execute('SELECT * FROM bot_config LIMIT 1')
        exists = c.fetchone()

        # Preserva termos existentes se não enviados
        if termos is None and exists:
            old_termos = exists.get('termos_busca') or []
            if isinstance(old_termos, str):
                old_termos = json.loads(old_termos)
            termos = old_termos
        termos = termos or []

        if exists:
            sql = """UPDATE bot_config SET empresa_nome=%s, website=%s,
                         descricao=%s, termos_busca=%s, linkedin_email=%s,
                         linkedin_cargos=%s, msg_inicial=%s,
                         email_assunto_padrao=%s, email_html_template=%s,
                         email_remetente=%s, email_remetente_nome=%s,
                         resend_api_key=%s,
                         smtp_host=%s, smtp_port=%s,
                         smtp_user=%s, smtp_password=%s,
                         serper_api_key=%s,
                         atualizado_em=NOW()"""
            params = [empresa_nome, website, descricao, psycopg2.extras.Json(termos),
                      li_email or None, psycopg2.extras.Json(li_cargos),
                      msg_inicial or None, email_assunto or None,
                      email_html or None,
                      email_remetente or None,
                      email_remetente_nome or None,
                      resend_api_key or None,
                      smtp_host or None, smtp_port or 587,
                      smtp_user or None, smtp_password or None,
                      serper_api_key or None]
            if li_password:
                sql += ", linkedin_password=%s"
                params.append(li_password)
            sql += " WHERE id=%s"
            params.append(exists['id'])
            c.execute(sql, params)
        else:
            c.execute("""INSERT INTO bot_config
                (empresa_nome, website, descricao, termos_busca,
                 linkedin_email, linkedin_password, linkedin_cargos,
                 msg_inicial, email_assunto_padrao, email_html_template,
                 email_remetente, email_remetente_nome, resend_api_key,
                 smtp_host, smtp_port, smtp_user, smtp_password)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                      (empresa_nome, website, descricao,
                       psycopg2.extras.Json(termos), li_email or None,
                       li_password or None, psycopg2.extras.Json(li_cargos),
                       msg_inicial or None, email_assunto or None,
                       email_html or None,
                       email_remetente or None,
                       email_remetente_nome or None,
                       resend_api_key or None,
                       smtp_host or None, smtp_port or 587,
                       smtp_user or None, smtp_password or None))
        conn.commit()

        # Atualizar users (separado para não bloquear o save principal)
        uid = session.get('user_id')
        if uid:
            try:
                conn2 = _conn()
                c2 = conn2.cursor()
                c2.execute(
                    'UPDATE users SET empresa_nome=%s, website=%s '
                    'WHERE id=%s',
                    (empresa_nome, website, uid))
                conn2.commit()
                conn2.close()
            except Exception:
                pass

        print(f'[save_config/{schema}] OK - salvou {len(termos)} termos', flush=True)
        return jsonify({'ok': True, 'redirect': '/dashboard', 'termos': termos})
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f'[save_config/{schema}] ERRO: {e}', flush=True)
        return jsonify({'error': str(e)}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


@app.route('/api/<bot>/config/generate-terms', methods=['POST'])
@login_required
def api_generate_terms(bot):
    data = request.get_json(silent=True) or {}
    result = _gerar_termos_ia(
        data.get('empresa_nome', ''),
        data.get('descricao', ''),
        data.get('website', '')
    )
    return jsonify({'ok': True, 'termos': result['termos'], 'cargos': result['cargos']})


def _gerar_termos_ia(empresa_nome: str, descricao: str, website: str) -> dict:
    """Retorna {'termos': [...], 'cargos': [...]}"""
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        return {'termos': _termos_fallback(descricao), 'cargos': []}
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=2000,
            messages=[{'role': 'user', 'content': f"""Você é especialista em prospecção B2B no Brasil.

Empresa vendedora: {empresa_nome}
Site: {website}
O que ela vende/faz: {descricao}

OBJETIVO: gerar MUITOS termos de busca Google para encontrar SITES DE EMPRESAS que seriam CLIENTES (compradores) deste produto/serviço.

REGRAS CRÍTICAS:
1. NUNCA gere termos que descrevam o produto/serviço vendido (isso acha concorrentes e blogs!)
2. Gere termos que achem o SITE INSTITUCIONAL das empresas que COMPRARIAM isso
3. Pense: quem é o COMPRADOR? Qual o segmento, porte, região?

FORMATO DOS TERMOS (varie entre esses padrões):
- "[tipo de empresa] [cidade] contato site:.com.br"
- "[segmento] [estado] telefone email"
- "[tipo empresa] [bairro/região] endereço contato"
- "lista [segmento] [cidade]"
- "[segmento] [cidade] quem somos"
- "[cargo decisor] [segmento] [cidade]"

EXEMPLOS:
Se vende software de monitoramento de PCs:
- ERRADO: "monitoramento de funcionários" (acha concorrentes!)
- CERTO: "escritório contabilidade centro SP contato site:.com.br"
- CERTO: "empresa call center Campinas telefone email"
- CERTO: "agência publicidade Pinheiros SP quem somos"
- CERTO: "lista escritórios advocacia Belo Horizonte"
- CERTO: "empresa logística Curitiba contato site:.com.br"
- CERTO: "construtora obras São Paulo telefone"

Se vende tombadores de grãos:
- ERRADO: "tombador de grãos" (acha concorrentes!)
- CERTO: "cerealista MT contato site:.com.br"
- CERTO: "cooperativa agrícola Londrina telefone"

IMPORTANTE:
- Gere 50 termos (não 20!) — quanto mais, melhor
- Varie MUITO: diferentes segmentos de cliente, diferentes cidades (capitais + interiores), diferentes estados
- Cubra pelo menos 10 estados brasileiros diferentes
- Cubra pelo menos 8 segmentos diferentes de empresas clientes
- Use cidades do interior também (Campinas, Londrina, Joinville, Uberlândia, etc.)

Retorne JSON:
1. "termos": 50 termos variados
2. "cargos": 10 cargos de decisores de compra DENTRO dessas empresas clientes

SOMENTE JSON válido:
{{"termos": ["cerealista MT contato site:.com.br", "cooperativa agricola PR telefone"], "cargos": ["gerente de operações", "diretor de compras"]}}"""}]
        )
        text = msg.content[0].text.strip()
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            data = json.loads(match.group())
            termos = data.get('termos') or []
            cargos = data.get('cargos') or []
            if termos:
                return {'termos': termos, 'cargos': cargos}
    except Exception as e:
        print(f'[gerar_termos] {e}')
    return {'termos': _termos_fallback(descricao), 'cargos': []}


def _termos_fallback(descricao: str) -> list:
    segmentos = [
        'escritório contabilidade', 'escritório advocacia', 'agência publicidade',
        'agência marketing digital', 'consultoria empresarial', 'empresa logística',
        'construtora', 'clínica médica', 'empresa comércio', 'indústria',
        'empresa recursos humanos', 'empresa call center', 'empresa tecnologia',
        'corretora seguros', 'imobiliária', 'empresa transporte',
    ]
    cidades = [
        'São Paulo', 'Rio de Janeiro', 'Belo Horizonte', 'Curitiba',
        'Porto Alegre', 'Brasília', 'Salvador', 'Goiânia',
        'Campinas', 'Fortaleza', 'Recife', 'Florianópolis',
        'Joinville', 'Uberlândia', 'Londrina', 'Ribeirão Preto',
    ]
    termos = []
    for seg in segmentos:
        for cid in random.sample(cidades, min(3, len(cidades))):
            termos.append(f'{seg} {cid} contato site:.com.br')
    random.shuffle(termos)
    return termos[:50]


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
# AGENDA (Calendário interno)
# =============================================================================

@app.route('/api/<bot>/agenda')
@login_required
def api_agenda(bot):
    schema = _get_schema() or bot
    mes = request.args.get('mes')  # formato YYYY-MM
    try:
        conn = _conn(schema)
        c = conn.cursor()
        if mes:
            c.execute("""SELECT a.*, e.nome_fantasia
                         FROM agenda a LEFT JOIN empresas e ON a.empresa_id = e.id
                         WHERE TO_CHAR(a.data_inicio, 'YYYY-MM') = %s
                         ORDER BY a.data_inicio ASC""", (mes,))
        else:
            c.execute("""SELECT a.*, e.nome_fantasia
                         FROM agenda a LEFT JOIN empresas e ON a.empresa_id = e.id
                         WHERE a.data_inicio >= NOW() - INTERVAL '7 days'
                         ORDER BY a.data_inicio ASC LIMIT 100""")
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/<bot>/agenda', methods=['POST'])
@login_required
def api_add_evento(bot):
    schema = _get_schema() or bot
    data = request.get_json(silent=True) or {}
    titulo = (data.get('titulo') or '').strip()
    data_inicio = data.get('data_inicio')
    if not titulo or not data_inicio:
        return jsonify({'error': 'titulo e data_inicio obrigatórios'}), 400
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute("""INSERT INTO agenda (empresa_id, titulo, descricao, data_inicio, data_fim, tipo, local)
                     VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                  (data.get('empresa_id') or None, titulo,
                   data.get('descricao') or None, data_inicio,
                   data.get('data_fim') or None,
                   data.get('tipo', 'reuniao'),
                   data.get('local') or None))
        eid = c.fetchone()['id']
        # Log atividade se vinculado a empresa
        if data.get('empresa_id'):
            c.execute("""INSERT INTO atividades (empresa_id, tipo, descricao)
                         VALUES (%s, 'reuniao', %s)""",
                      (data['empresa_id'], f'Agendado: {titulo} em {data_inicio}'))
        conn.commit()
        conn.close()
        return jsonify({'ok': True, 'id': eid})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/<bot>/agenda/<int:evento_id>', methods=['PUT'])
@login_required
def api_update_evento(bot, evento_id):
    schema = _get_schema() or bot
    data = request.get_json(silent=True) or {}
    try:
        conn = _conn(schema)
        c = conn.cursor()
        if 'concluido' in data:
            c.execute('UPDATE agenda SET concluido = %s WHERE id = %s',
                      (data['concluido'], evento_id))
        allowed = {'titulo', 'descricao', 'data_inicio', 'data_fim', 'tipo', 'local', 'empresa_id'}
        fields = {k: v for k, v in data.items() if k in allowed and v is not None}
        if fields:
            sets = ', '.join(f'{k} = %s' for k in fields)
            c.execute(f'UPDATE agenda SET {sets} WHERE id = %s',
                      list(fields.values()) + [evento_id])
        conn.commit()
        conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/<bot>/agenda/<int:evento_id>', methods=['DELETE'])
@login_required
def api_delete_evento(bot, evento_id):
    schema = _get_schema() or bot
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute('DELETE FROM agenda WHERE id = %s', (evento_id,))
        conn.commit()
        conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# =============================================================================
# GERAR MENSAGEM INICIAL COM IA
# =============================================================================

@app.route('/api/<bot>/config/generate-msg', methods=['POST'])
@login_required
def api_generate_msg(bot):
    data = request.get_json(silent=True) or {}
    empresa = data.get('empresa_nome', '')
    descricao = data.get('descricao', '')
    if not descricao:
        return jsonify({'error': 'Preencha a descrição da empresa'}), 400

    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        return jsonify({'error': 'ANTHROPIC_API_KEY não configurado'}), 400
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=600,
            messages=[{'role': 'user', 'content': f"""Você é copywriter especialista em prospecção B2B via WhatsApp.

Empresa vendedora: {empresa}
O que ela vende: {descricao}

Crie UMA mensagem de primeiro contato via WhatsApp para prospectar clientes.

Regras:
- Máximo 6 linhas (WhatsApp precisa ser curto)
- Tom profissional mas acessível, sem ser invasivo
- Mencione o benefício principal do produto/serviço
- Inclua call-to-action claro
- Use {{{{nome}}}} para o nome da empresa prospectada
- Use {{{{cal_link}}}} para o link de agendamento
- Pode usar 1-2 emojis, sem exagero

Responda SOMENTE com a mensagem, sem explicações."""}]
        )
        return jsonify({'ok': True, 'mensagem': msg.content[0].text.strip()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/<bot>/config/generate-email', methods=['POST'])
@login_required
def api_generate_email(bot):
    data = request.get_json(silent=True) or {}
    empresa = data.get('empresa_nome', '')
    descricao = data.get('descricao', '')
    website = data.get('website', '').strip()
    if not descricao:
        return jsonify({'error': 'Preencha a descrição da empresa'}), 400

    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        return jsonify({'error': 'ANTHROPIC_API_KEY não configurado'}), 400

    # --- Visitar site da empresa para extrair identidade visual ---
    site_html = ''
    if website:
        try:
            import requests as req
            from bs4 import BeautifulSoup
            url = website if website.startswith('http') else f'https://{website}'
            resp = req.get(url, timeout=10,
                           headers={'User-Agent': 'Mozilla/5.0'})
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'html.parser')
            # Remover scripts e imagens para reduzir tamanho
            for tag in soup.find_all(['script', 'noscript', 'svg',
                                      'iframe', 'video', 'audio']):
                tag.decompose()
            for img in soup.find_all('img'):
                img.decompose()
            # Pegar o HTML limpo (cabeça com styles + body)
            site_html = str(soup)[:8000]
        except Exception:
            site_html = ''

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        # Se temos o HTML do site, primeiro pedir análise da identidade visual
        analise_site = ''
        if site_html:
            analise = client.messages.create(
                model='claude-haiku-4-5-20251001',
                max_tokens=500,
                messages=[{'role': 'user', 'content': f"""Analise o HTML deste site e extraia a identidade visual da empresa.

HTML DO SITE:
{site_html}

Retorne APENAS um resumo conciso com:
1. Cores principais (hex exatos encontrados no CSS/HTML)
2. Cores secundárias/de destaque
3. Fontes usadas
4. Tom/estilo visual (moderno, corporativo, minimalista, etc)
5. Slogan ou frase de efeito se houver
6. Tipo de negócio/contexto da empresa

Seja direto e objetivo."""}]
            )
            analise_site = analise.content[0].text.strip()

        contexto = ''
        if analise_site:
            contexto = f"""
IDENTIDADE VISUAL DA EMPRESA (extraída do site {website}):
{analise_site}

IMPORTANTE: Replique EXATAMENTE as cores, fontes e estilo visual da empresa no email.
O email deve parecer que foi feito pelo mesmo designer do site.
"""

        msg = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=2000,
            messages=[{'role': 'user', 'content': f"""Você é designer de emails e copywriter B2B.

Empresa vendedora: {empresa}
O que ela vende: {descricao}
{contexto}
Crie um template HTML de email profissional para prospecção B2B.

Regras:
- HTML completo, inline CSS (compatível com clientes de email)
- Max-width 600px, centrado, fundo branco
- Use EXATAMENTE as cores da identidade visual da empresa vendedora
- Seções: header com nome da empresa, saudação, proposta de valor (2-3 bullets), call-to-action (botão), footer
- Use {{{{nome}}}} para o nome da empresa prospectada
- Use {{{{email}}}} para o email do lead
- Use {{{{segmento}}}} para o segmento do lead
- Use {{{{cidade}}}} para a cidade do lead
- O botão CTA deve apontar para # (o link será substituído depois)
- Tom profissional, direto, sem ser genérico
- NÃO use imagens externas
- O conteúdo deve refletir o contexto real da empresa, não ser genérico

Responda SOMENTE com o HTML, sem explicações ou markdown."""}]
        )
        html = msg.content[0].text.strip()
        # Remove possíveis markdown code fences
        if html.startswith('```'):
            html = html.split('\n', 1)[1]
        if html.endswith('```'):
            html = html.rsplit('```', 1)[0]
        return jsonify({'ok': True, 'html': html.strip(),
                        'assunto': f'{empresa} — uma solução para {{{{nome}}}}'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# =============================================================================
# HEALTH
# =============================================================================

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'version': '2.1'})


# =============================================================================
# AGENDAMENTO PÚBLICO (lead acessa sem login)
# =============================================================================

def _get_agenda_token(schema, lead_id):
    """Gera ou retorna token único para agendamento do lead."""
    conn = _conn(schema)
    c = conn.cursor()
    c.execute('SELECT agenda_token FROM empresas WHERE id=%s', (lead_id,))
    row = c.fetchone()
    if row and row.get('agenda_token'):
        conn.close()
        return row['agenda_token']
    token = secrets.token_urlsafe(16)
    c.execute('UPDATE empresas SET agenda_token=%s WHERE id=%s',
              (token, lead_id))
    conn.commit()
    conn.close()
    return token


def _enriquecer_cnpj(schema, lead_id):
    """Enriquece dados do lead via BrasilAPI (CNPJ)."""
    import requests as http
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute('SELECT cnpj FROM empresas WHERE id = %s', (lead_id,))
        row = c.fetchone()
        if not row or not row.get('cnpj'):
            conn.close()
            return {'ok': False, 'error': 'Lead sem CNPJ'}
        cnpj_digits = ''.join(ch for ch in row['cnpj'] if ch.isdigit())
        if len(cnpj_digits) != 14:
            conn.close()
            return {'ok': False, 'error': 'CNPJ invalido'}
        r = http.get(f'https://brasilapi.com.br/api/cnpj/v1/{cnpj_digits}', timeout=10)
        if r.status_code != 200:
            conn.close()
            return {'ok': False, 'error': f'BrasilAPI retornou {r.status_code}'}
        d = r.json()
        razao = d.get('razao_social', '')
        fantasia = d.get('nome_fantasia', '')
        porte = d.get('porte', '')
        natureza = d.get('descricao_natureza_juridica', '')
        situacao = d.get('descricao_situacao_cadastral', '')
        logr = d.get('logradouro', '')
        num = d.get('numero', '')
        compl = d.get('complemento', '')
        bairro = d.get('bairro', '')
        mun = d.get('municipio', '')
        uf = d.get('uf', '')
        endereco = f'{logr}, {num}'.strip(', ')
        if compl:
            endereco += f' - {compl}'
        if bairro:
            endereco += f', {bairro}'
        c.execute("""UPDATE empresas SET
            razao_social = COALESCE(NULLIF(razao_social,''), %s),
            nome_fantasia = COALESCE(NULLIF(nome_fantasia,''), %s),
            porte = %s, natureza_juridica = %s, situacao_cadastral = %s,
            endereco = COALESCE(NULLIF(endereco,''), %s),
            cidade = COALESCE(NULLIF(cidade,''), %s),
            estado = COALESCE(NULLIF(estado,''), %s),
            enriquecido = TRUE, enriquecido_em = NOW()
            WHERE id = %s""",
            (razao, fantasia, porte, natureza, situacao,
             endereco, mun, uf, lead_id))
        c.execute("""INSERT INTO atividades (empresa_id, tipo, descricao)
            VALUES (%s, 'enriquecimento', %s)""",
            (lead_id, f'CNPJ enriquecido: {razao} | {porte} | {situacao}'))
        conn.commit()
        conn.close()
        return {'ok': True, 'razao_social': razao, 'porte': porte,
                'cidade': mun, 'estado': uf, 'situacao': situacao}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def _get_link_agenda(schema, lead_id):
    """Retorna URL pública de agendamento para o lead."""
    token = _get_agenda_token(schema, lead_id)
    base = os.environ.get('BASE_URL', request.host_url.rstrip('/'))
    return f'{base}/agendar/{token}'


def _find_lead_by_token(token):
    """Busca lead e schema pelo token de agendamento."""
    if not DATABASE_URL or not token:
        return None, None
    try:
        conn = psycopg2.connect(
            DATABASE_URL,
            cursor_factory=psycopg2.extras.RealDictCursor)
        c = conn.cursor()
        c.execute('SELECT id, schema_name FROM users')
        users = c.fetchall()
        conn.close()
        for u in users:
            sch = u.get('schema_name')
            if not sch:
                continue
            try:
                conn2 = _conn(sch)
                c2 = conn2.cursor()
                c2.execute(
                    'SELECT * FROM empresas WHERE agenda_token=%s',
                    (token,))
                lead = c2.fetchone()
                conn2.close()
                if lead:
                    return dict(lead), sch
            except Exception:
                continue
    except Exception:
        pass
    return None, None


def _horarios_disponiveis(schema, data_str):
    """Retorna horários disponíveis para uma data (YYYY-MM-DD)."""
    cfg = get_bot_config(schema)
    h_ini = cfg.get('horario_inicio', 9) or 9
    h_fim = cfg.get('horario_fim', 18) or 18
    duracao = cfg.get('duracao_reuniao', 30) or 30
    dias_ok = str(cfg.get('dias_semana', '1,2,3,4,5') or '1,2,3,4,5')

    from datetime import datetime, timedelta
    dt = datetime.strptime(data_str, '%Y-%m-%d')
    # weekday: 0=seg, 6=dom — mas isoweekday: 1=seg, 7=dom
    if str(dt.isoweekday()) not in dias_ok:
        return []

    # Busca eventos já agendados nesse dia
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute(
            "SELECT data_inicio, data_fim FROM agenda "
            "WHERE data_inicio::date = %s AND concluido = FALSE",
            (data_str,))
        ocupados = []
        for r in c.fetchall():
            ini = r['data_inicio']
            fim = r['data_fim'] or (ini + timedelta(minutes=duracao))
            ocupados.append((ini, fim))
        conn.close()
    except Exception:
        ocupados = []

    # Gera slots
    slots = []
    hora = dt.replace(hour=int(h_ini), minute=0, second=0)
    fim_dia = dt.replace(hour=int(h_fim), minute=0, second=0)
    now = datetime.now()

    while hora + timedelta(minutes=duracao) <= fim_dia:
        if hora > now:  # só horários futuros
            conflito = False
            slot_fim = hora + timedelta(minutes=duracao)
            for oc_ini, oc_fim in ocupados:
                if hora < oc_fim and slot_fim > oc_ini:
                    conflito = True
                    break
            if not conflito:
                slots.append(hora.strftime('%H:%M'))
        hora += timedelta(minutes=duracao)
    return slots


@app.route('/agendar/<token>')
def pagina_agendar(token):
    lead, schema = _find_lead_by_token(token)
    if not lead:
        return '<h2>Link inválido ou expirado</h2>', 404
    cfg = get_bot_config(schema)
    empresa = cfg.get('empresa_nome', 'Empresa')
    return render_template('agendar.html',
                           token=token,
                           empresa=empresa,
                           lead_nome=lead.get('nome_fantasia', ''))


@app.route('/api/agendar/<token>/slots')
def api_agenda_slots(token):
    lead, schema = _find_lead_by_token(token)
    if not lead:
        return jsonify({'error': 'token inválido'}), 404
    data = request.args.get('data')
    if not data:
        return jsonify({'error': 'data obrigatória (YYYY-MM-DD)'}), 400
    slots = _horarios_disponiveis(schema, data)
    return jsonify({'slots': slots, 'data': data})


@app.route('/api/agendar/<token>/confirmar', methods=['POST'])
def api_agenda_confirmar(token):
    lead, schema = _find_lead_by_token(token)
    if not lead:
        return jsonify({'error': 'token inválido'}), 404
    data = request.get_json(silent=True) or {}
    data_str = data.get('data')
    hora_str = data.get('hora')
    if not data_str or not hora_str:
        return jsonify({'error': 'data e hora obrigatórios'}), 400

    from datetime import datetime, timedelta
    cfg = get_bot_config(schema)
    duracao = cfg.get('duracao_reuniao', 30) or 30

    # Verifica disponibilidade
    slots = _horarios_disponiveis(schema, data_str)
    if hora_str not in slots:
        return jsonify({'error': 'Horário não disponível'}), 409

    dt_inicio = datetime.strptime(f'{data_str} {hora_str}', '%Y-%m-%d %H:%M')
    dt_fim = dt_inicio + timedelta(minutes=duracao)
    nome = lead.get('nome_fantasia', 'Lead')

    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute("""INSERT INTO agenda
            (empresa_id, titulo, data_inicio, data_fim, tipo)
            VALUES (%s, %s, %s, %s, 'reuniao') RETURNING id""",
            (lead['id'], f'Reunião — {nome}',
             dt_inicio, dt_fim))
        evt_id = c.fetchone()['id']
        # Auto-mover para qualificado
        c.execute("""UPDATE empresas SET status =
            CASE WHEN status IN ('novo','contactada','respondeu')
            THEN 'qualificado' ELSE status END
            WHERE id = %s""", (lead['id'],))
        c.execute("""INSERT INTO atividades
            (empresa_id, tipo, descricao)
            VALUES (%s, 'reuniao', %s)""",
            (lead['id'],
             f'Reunião agendada pelo lead: {data_str} {hora_str}'))
        conn.commit()
        conn.close()
        return jsonify({'ok': True, 'id': evt_id,
                        'data': data_str, 'hora': hora_str})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/<bot>/lead/<int:lead_id>/link-agenda')
@login_required
def api_lead_link_agenda(bot, lead_id):
    """Retorna link de agendamento para um lead específico."""
    schema = _get_schema() or bot
    link = _get_link_agenda(schema, lead_id)
    return jsonify({'link': link})


# =============================================================================
# MERCADO PAGO — PAGAMENTOS
# =============================================================================

MP_ACCESS_TOKEN = os.environ.get('MP_ACCESS_TOKEN', '')
MP_PUBLIC_KEY = os.environ.get('MP_PUBLIC_KEY', '')
MP_PLANOS = {
    'pro': {
        'nome': 'TurboVenda Pro',
        'valor': 299.00,
        'descricao': 'CRM + Prospecção IA + Email + WhatsApp ilimitado',
    },
}
# Trial: grátis, limite 50 leads
TRIAL_LEAD_LIMIT = 50


@app.route('/api/planos')
def api_planos():
    """Retorna planos disponíveis."""
    planos = []
    for key, p in MP_PLANOS.items():
        planos.append({
            'id': key, 'nome': p['nome'],
            'valor': p['valor'], 'descricao': p['descricao'],
        })
    return jsonify(planos)


@app.route('/api/checkout', methods=['POST'])
@login_required
def api_checkout():
    """Cria preferência de pagamento no Mercado Pago."""
    import requests as http
    if not MP_ACCESS_TOKEN:
        return jsonify({
            'error': 'Mercado Pago não configurado'}), 500
    data = request.get_json(silent=True) or {}
    plano_id = data.get('plano', 'pro')
    plano = MP_PLANOS.get(plano_id)
    if not plano:
        return jsonify({'error': 'Plano inválido'}), 400

    user = get_current_user()
    base = os.environ.get('BASE_URL', '')
    if not base:
        base = request.url_root.rstrip('/')
        if base.startswith('http://') and 'railway' in base:
            base = base.replace('http://', 'https://', 1)

    pref = {
        'items': [{
            'title': plano['nome'],
            'quantity': 1,
            'unit_price': plano['valor'],
            'currency_id': 'BRL',
        }],
        'payer': {'email': user['email']},
        'back_urls': {
            'success': f'{base}/pagamento/sucesso',
            'failure': f'{base}/pagamento/falha',
            'pending': f'{base}/pagamento/pendente',
        },
        'auto_return': 'approved',
        'notification_url': f'{base}/webhook/mercadopago',
        'external_reference': f"user_{user['id']}_{plano_id}",
        'metadata': {
            'user_id': user['id'],
            'plano': plano_id,
        },
    }
    try:
        r = http.post(
            'https://api.mercadopago.com/checkout/preferences',
            headers={
                'Authorization': f'Bearer {MP_ACCESS_TOKEN}',
                'Content-Type': 'application/json',
            },
            json=pref, timeout=15)
        resp = r.json()
        if r.status_code in (200, 201):
            return jsonify({
                'ok': True,
                'init_point': resp.get('init_point'),
                'sandbox_init_point': resp.get(
                    'sandbox_init_point'),
            })
        return jsonify({
            'error': resp.get('message', 'Erro MP')}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/webhook/mercadopago', methods=['POST'])
def webhook_mercadopago():
    """Webhook do Mercado Pago — atualiza plano do user."""
    import requests as http
    data = request.get_json(silent=True) or {}
    if data.get('type') != 'payment':
        return jsonify({'ok': True})

    payment_id = data.get('data', {}).get('id')
    if not payment_id or not MP_ACCESS_TOKEN:
        return jsonify({'ok': True})

    try:
        r = http.get(
            f'https://api.mercadopago.com/v1/payments/{payment_id}',
            headers={
                'Authorization': f'Bearer {MP_ACCESS_TOKEN}'},
            timeout=10)
        pay = r.json()
        status = pay.get('status')
        ext_ref = pay.get('external_reference', '')
        valor = pay.get('transaction_amount', 0)
        meta = pay.get('metadata', {})
        user_id = meta.get('user_id')
        plano = meta.get('plano', 'pro')

        if not user_id and ext_ref.startswith('user_'):
            parts = ext_ref.split('_')
            if len(parts) >= 2:
                user_id = int(parts[1])
                if len(parts) >= 3:
                    plano = parts[2]

        if not user_id:
            return jsonify({'ok': True})

        conn = psycopg2.connect(
            DATABASE_URL,
            cursor_factory=psycopg2.extras.RealDictCursor)
        c = conn.cursor()

        # Registra pagamento
        c.execute("""INSERT INTO pagamentos
            (user_id, mp_payment_id, status, valor, plano)
            VALUES (%s, %s, %s, %s, %s)""",
            (user_id, str(payment_id), status, valor, plano))

        # Ativa plano se aprovado
        if status == 'approved':
            from datetime import timedelta
            c.execute("""UPDATE users SET
                plano = %s,
                plano_expira = NOW() + INTERVAL '30 days',
                mp_subscription_id = %s
                WHERE id = %s""",
                (plano, str(payment_id), user_id))
            print(f'[MP] User {user_id} -> plano {plano}'
                  f' (payment {payment_id})', flush=True)

        conn.commit()
        conn.close()
    except Exception as e:
        print(f'[MP] Webhook error: {e}', flush=True)

    return jsonify({'ok': True})


@app.route('/api/pagamento/pix', methods=['POST'])
@login_required
def api_pagamento_pix():
    """Gera pagamento PIX via Mercado Pago."""
    import requests as http
    if not MP_ACCESS_TOKEN:
        return jsonify({'error': 'MP não configurado'}), 500
    data = request.get_json(silent=True) or {}
    plano_id = data.get('plano', 'pro')
    plano = MP_PLANOS.get(plano_id)
    if not plano:
        return jsonify({'error': 'Plano inválido'}), 400
    user = get_current_user()
    try:
        r = http.post(
            'https://api.mercadopago.com/v1/payments',
            headers={
                'Authorization': f'Bearer {MP_ACCESS_TOKEN}',
                'Content-Type': 'application/json',
                'X-Idempotency-Key': f"pix_{user['id']}_{plano_id}_{int(__import__('time').time())}",
            },
            json={
                'transaction_amount': plano['valor'],
                'description': plano['nome'],
                'payment_method_id': 'pix',
                'payer': {'email': user['email']},
                'metadata': {
                    'user_id': user['id'],
                    'plano': plano_id,
                },
            }, timeout=15)
        pay = r.json()
        if r.status_code in (200, 201):
            pix_data = pay.get(
                'point_of_interaction', {}).get(
                'transaction_data', {})
            # Registra pagamento
            try:
                conn = psycopg2.connect(
                    DATABASE_URL,
                    cursor_factory=psycopg2.extras.RealDictCursor)
                c = conn.cursor()
                c.execute("""INSERT INTO pagamentos
                    (user_id, mp_payment_id, status,
                     valor, plano)
                    VALUES (%s,%s,%s,%s,%s)""",
                    (user['id'], str(pay.get('id')),
                     pay.get('status'), plano['valor'],
                     plano_id))
                conn.commit()
                conn.close()
            except Exception:
                pass
            return jsonify({
                'ok': True,
                'qr_code': pix_data.get('qr_code'),
                'qr_code_base64': pix_data.get(
                    'qr_code_base64'),
                'payment_id': pay.get('id'),
            })
        return jsonify({
            'error': pay.get('message',
                str(pay.get('cause', 'Erro')))}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pagamento/cartao', methods=['POST'])
@login_required
def api_pagamento_cartao():
    """Processa pagamento com cartão via MP."""
    import requests as http
    if not MP_ACCESS_TOKEN:
        return jsonify({'error': 'MP não configurado'}), 500
    data = request.get_json(silent=True) or {}
    plano_id = data.get('plano', 'pro')
    plano = MP_PLANOS.get(plano_id)
    if not plano:
        return jsonify({'error': 'Plano inválido'}), 400
    user = get_current_user()
    card_num = data.get('card_number', '').replace(' ', '')
    exp = data.get('expiration', '')
    cvv = data.get('cvv', '')
    holder = data.get('holder_name', '')
    cpf = data.get('cpf', '').replace('.', '').replace('-', '')
    if not all([card_num, exp, cvv, holder, cpf]):
        return jsonify({'error': 'Preencha todos os campos'}), 400
    exp_parts = exp.split('/')
    if len(exp_parts) != 2:
        return jsonify({'error': 'Validade inválida'}), 400
    exp_month = int(exp_parts[0])
    exp_year = int('20' + exp_parts[1]) if len(
        exp_parts[1]) == 2 else int(exp_parts[1])
    # Detectar bandeira
    bin6 = card_num[:6]
    if card_num.startswith('4'):
        payment_method = 'visa'
    elif card_num.startswith(('51', '52', '53', '54', '55')):
        payment_method = 'master'
    elif card_num.startswith(('34', '37')):
        payment_method = 'amex'
    elif card_num.startswith('636368'):
        payment_method = 'elo'
    else:
        payment_method = 'visa'
    try:
        # Criar token do cartão
        token_r = http.post(
            'https://api.mercadopago.com/v1/card_tokens',
            headers={
                'Authorization': f'Bearer {MP_ACCESS_TOKEN}',
                'Content-Type': 'application/json',
            },
            json={
                'card_number': card_num,
                'expiration_month': exp_month,
                'expiration_year': exp_year,
                'security_code': cvv,
                'cardholder': {
                    'name': holder,
                    'identification': {
                        'type': 'CPF',
                        'number': cpf,
                    },
                },
            }, timeout=15)
        token_data = token_r.json()
        if token_r.status_code not in (200, 201):
            return jsonify({
                'error': token_data.get('message',
                    'Erro ao tokenizar cartão')}), 400
        card_token = token_data.get('id')
        # Criar pagamento
        r = http.post(
            'https://api.mercadopago.com/v1/payments',
            headers={
                'Authorization': f'Bearer {MP_ACCESS_TOKEN}',
                'Content-Type': 'application/json',
                'X-Idempotency-Key': f"card_{user['id']}_{int(__import__('time').time())}",
            },
            json={
                'transaction_amount': plano['valor'],
                'token': card_token,
                'description': plano['nome'],
                'installments': 1,
                'payment_method_id': payment_method,
                'payer': {
                    'email': user['email'],
                    'identification': {
                        'type': 'CPF',
                        'number': cpf,
                    },
                },
                'metadata': {
                    'user_id': user['id'],
                    'plano': plano_id,
                },
            }, timeout=15)
        pay = r.json()
        status = pay.get('status')
        # Registra
        try:
            conn = psycopg2.connect(
                DATABASE_URL,
                cursor_factory=psycopg2.extras.RealDictCursor)
            c = conn.cursor()
            c.execute("""INSERT INTO pagamentos
                (user_id, mp_payment_id, status,
                 valor, plano)
                VALUES (%s,%s,%s,%s,%s)""",
                (user['id'], str(pay.get('id')),
                 status, plano['valor'], plano_id))
            if status == 'approved':
                c.execute("""UPDATE users SET
                    plano = %s,
                    plano_expira = NOW() + INTERVAL '30 days'
                    WHERE id = %s""",
                    (plano_id, user['id']))
            conn.commit()
            conn.close()
        except Exception:
            pass
        if status == 'approved':
            return jsonify({'ok': True, 'status': 'approved'})
        elif status == 'in_process':
            return jsonify({
                'ok': True,
                'status': 'pending',
                'error': 'Pagamento em análise'})
        else:
            detail = pay.get('status_detail', '')
            msgs = {
                'cc_rejected_call_for_authorize':
                    'Cartão requer autorização. Ligue pro banco.',
                'cc_rejected_insufficient_amount':
                    'Saldo insuficiente.',
                'cc_rejected_bad_filled_security_code':
                    'CVV incorreto.',
                'cc_rejected_bad_filled_date':
                    'Data de validade incorreta.',
                'cc_rejected_bad_filled_other':
                    'Dados do cartão incorretos.',
            }
            return jsonify({
                'error': msgs.get(detail,
                    f'Pagamento recusado ({detail})')}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pagamento/boleto', methods=['POST'])
@login_required
def api_pagamento_boleto():
    """Gera boleto via Mercado Pago."""
    import requests as http
    if not MP_ACCESS_TOKEN:
        return jsonify({'error': 'MP não configurado'}), 500
    data = request.get_json(silent=True) or {}
    plano_id = data.get('plano', 'pro')
    plano = MP_PLANOS.get(plano_id)
    if not plano:
        return jsonify({'error': 'Plano inválido'}), 400
    user = get_current_user()
    try:
        r = http.post(
            'https://api.mercadopago.com/v1/payments',
            headers={
                'Authorization': f'Bearer {MP_ACCESS_TOKEN}',
                'Content-Type': 'application/json',
                'X-Idempotency-Key': f"boleto_{user['id']}_{int(__import__('time').time())}",
            },
            json={
                'transaction_amount': plano['valor'],
                'description': plano['nome'],
                'payment_method_id': 'bolbradesco',
                'payer': {
                    'email': user['email'],
                    'first_name': user.get('empresa_nome', 'Cliente'),
                    'last_name': 'TurboVenda',
                },
                'metadata': {
                    'user_id': user['id'],
                    'plano': plano_id,
                },
            }, timeout=15)
        pay = r.json()
        if r.status_code in (200, 201):
            boleto_url = pay.get(
                'transaction_details', {}).get(
                'external_resource_url', '')
            try:
                conn = psycopg2.connect(
                    DATABASE_URL,
                    cursor_factory=psycopg2.extras.RealDictCursor)
                c = conn.cursor()
                c.execute("""INSERT INTO pagamentos
                    (user_id, mp_payment_id, status,
                     valor, plano)
                    VALUES (%s,%s,%s,%s,%s)""",
                    (user['id'], str(pay.get('id')),
                     pay.get('status'), plano['valor'],
                     plano_id))
                conn.commit()
                conn.close()
            except Exception:
                pass
            return jsonify({
                'ok': True,
                'boleto_url': boleto_url,
                'payment_id': pay.get('id'),
            })
        return jsonify({
            'error': pay.get('message',
                str(pay.get('cause', 'Erro')))}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/pagamento/<resultado>')
@login_required
def pagamento_resultado(resultado):
    """Página de resultado do pagamento."""
    msgs = {
        'sucesso': ('Pagamento aprovado!',
                     'Seu plano Pro já está ativo.', '#22c55e'),
        'falha': ('Pagamento não aprovado',
                   'Tente novamente ou use outro método.', '#f87171'),
        'pendente': ('Pagamento pendente',
                      'Aguardando confirmação.', '#fbbf24'),
    }
    titulo, desc, cor = msgs.get(
        resultado, ('Pagamento', '', '#818cf8'))
    return f'''<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<title>Pagamento - TurboVenda</title>
<style>
body{{font-family:Inter,sans-serif;background:#060b18;
color:#f1f5f9;display:flex;align-items:center;
justify-content:center;min-height:100vh}}
.box{{text-align:center;background:#0d1526;
padding:40px;border-radius:16px;
border:1px solid rgba(255,255,255,.06)}}
h2{{color:{cor};margin-bottom:8px}}
a{{color:#818cf8;text-decoration:none}}
</style></head><body>
<div class="box">
<h2>{titulo}</h2><p>{desc}</p>
<br><a href="/dashboard">Ir para o Dashboard &rarr;</a>
</div></body></html>'''


@app.route('/api/meu-plano')
@login_required
def api_meu_plano():
    """Retorna info do plano do user logado."""
    user = get_current_user()
    plano = user.get('plano', 'trial')
    expira = user.get('plano_expira')
    ativo = plano != 'trial'
    if expira:
        from datetime import datetime
        if isinstance(expira, str):
            expira = datetime.fromisoformat(expira)
        ativo = expira > datetime.now()
    return jsonify({
        'plano': plano,
        'ativo': ativo,
        'expira': str(expira) if expira else None,
    })


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == '__main__':
    _init_public_schema()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
