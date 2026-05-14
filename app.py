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
from urllib.parse import quote as _urlquote
import psycopg2
import psycopg2.extras
from functools import wraps
from flask import (Flask, jsonify, make_response, redirect, render_template,
                   request, send_file, session, url_for)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'mv-saas-2025-change-in-prod')
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['PREFERRED_URL_SCHEME'] = 'https'
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

GA_MEASUREMENT_ID = os.environ.get('GA_MEASUREMENT_ID', 'G-NGSNSF3SPM')

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
        # Set users as pro
        c.execute("UPDATE users SET plano = 'pro' WHERE email IN ('suporte@pcmonitor.com.br', 'comercial1@pili.ind.br') AND plano != 'pro'")
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
        email_remetente TEXT,
        email_remetente_nome TEXT,
        resend_api_key TEXT,
        smtp_host TEXT, smtp_port INTEGER DEFAULT 587,
        smtp_user TEXT, smtp_password TEXT,
        serper_api_key TEXT,
        horario_inicio INTEGER DEFAULT 9,
        horario_fim INTEGER DEFAULT 18,
        duracao_reuniao INTEGER DEFAULT 30,
        dias_semana TEXT DEFAULT '1,2,3,4,5',
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
    c.execute("""CREATE TABLE IF NOT EXISTS sequencias (
        id BIGSERIAL PRIMARY KEY,
        nome TEXT NOT NULL,
        passos JSONB DEFAULT '[]',
        ativo BOOLEAN DEFAULT TRUE,
        criado_em TIMESTAMP DEFAULT NOW(),
        atualizado_em TIMESTAMP DEFAULT NOW()
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS sequencia_leads (
        id BIGSERIAL PRIMARY KEY,
        sequencia_id BIGINT REFERENCES sequencias(id) ON DELETE CASCADE,
        empresa_id BIGINT REFERENCES empresas(id) ON DELETE CASCADE,
        passo_atual INTEGER DEFAULT 0,
        proximo_envio TIMESTAMP,
        status TEXT DEFAULT 'ativo',
        iniciado_em TIMESTAMP DEFAULT NOW(),
        atualizado_em TIMESTAMP DEFAULT NOW(),
        UNIQUE(sequencia_id, empresa_id)
    )""")
    c.execute("INSERT INTO execucao (id) VALUES (1) ON CONFLICT DO NOTHING")
    conn.commit()
    # Migrations para schemas antigos
    for stmt in [
        "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS observacoes TEXT",
        "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS wa_enviado TIMESTAMP",
        "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS agenda_token TEXT",
        "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS enriquecido BOOLEAN DEFAULT FALSE",
        "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS enriquecido_em TIMESTAMP",
        "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS natureza_juridica TEXT",
        "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS situacao_cadastral TEXT",
        "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS email_remetente TEXT",
        "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS email_remetente_nome TEXT",
        "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS resend_api_key TEXT",
        "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS smtp_host TEXT",
        "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS smtp_port INTEGER DEFAULT 587",
        "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS smtp_user TEXT",
        "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS smtp_password TEXT",
        "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS serper_api_key TEXT",
        "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS horario_inicio INTEGER DEFAULT 9",
        "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS horario_fim INTEGER DEFAULT 18",
        "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS duracao_reuniao INTEGER DEFAULT 30",
        "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS dias_semana TEXT DEFAULT '1,2,3,4,5'",
        "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS email_aberto TIMESTAMP",
        "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS email_clicado TIMESTAMP",
        "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS email_track_token TEXT",
    ]:
        try:
            c.execute(stmt)
        except Exception:
            conn.rollback()
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


PLAN_LEAD_LIMITS = {
    'trial': 50,
    'starter': 500,
    'pro': None,       # ilimitado
    'enterprise': None  # ilimitado
}


def _check_lead_limit(schema, uid=None):
    """Retorna (ok, msg). ok=True se pode inserir, False se atingiu limite."""
    uid = uid or session.get('user_id')
    if not uid:
        return True, ''
    try:
        conn = _conn()
        c = conn.cursor()
        c.execute('SELECT plano FROM users WHERE id = %s', (uid,))
        row = c.fetchone()
        conn.close()
        plano = (row['plano'] if row else 'trial') or 'trial'
    except Exception:
        plano = 'trial'
    limite = PLAN_LEAD_LIMITS.get(plano)
    if limite is None:
        return True, ''
    try:
        conn2 = _conn(schema)
        c2 = conn2.cursor()
        c2.execute('SELECT COUNT(*) AS total FROM empresas')
        total = c2.fetchone()['total']
        conn2.close()
    except Exception:
        return True, ''
    if total >= limite:
        return False, f'Limite de {limite} leads atingido no plano {plano}. Faça upgrade para continuar.'
    return True, ''


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
         'linkedin_total': 0, 'msgs_hoje': 0, 'qualificados': 0,
         'emails_abertos': 0, 'emails_clicados': 0}
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
        try:
            c.execute("SELECT COUNT(*) AS n FROM empresas "
                      "WHERE email_aberto IS NOT NULL")
            z['emails_abertos'] = c.fetchone()['n']
        except Exception:
            conn.rollback()
        try:
            c.execute("SELECT COUNT(*) AS n FROM empresas "
                      "WHERE email_clicado IS NOT NULL")
            z['emails_clicados'] = c.fetchone()['n']
        except Exception:
            conn.rollback()
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
        _sub = """(SELECT ct.nome || ' - ' || ct.cargo
                   FROM contatos ct WHERE ct.empresa_id = e.id AND ct.decisor = 1
                   LIMIT 1) AS _decisor"""
        _base = """e.id, e.nome_fantasia, e.whatsapp, e.telefone, e.email, e.score,
                   e.status, e.segmento, e.demo_status, e.cidade, e.estado,
                   e.encontrado_em, e.cnpj, e.razao_social, e.website,
                   e.linkedin, e.instagram, e.fonte, e.porte,
                   e.email_enviado, e.wa_enviado, e.observacoes"""
        try:
            c.execute(f"SELECT {_base}, e.email_aberto, e.email_clicado, {_sub}"
                      " FROM empresas e ORDER BY e.encontrado_em DESC LIMIT %s",
                      (limite,))
        except Exception:
            conn.rollback()
            c.execute(f"SELECT {_base}, NULL as email_aberto, NULL as email_clicado, {_sub}"
                      " FROM empresas e ORDER BY e.encontrado_em DESC LIMIT %s",
                      (limite,))
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
    if not user:
        return None
    schema = user.get('schema_name')
    if not schema:
        schema = f'emp_{user["id"]}'
        try:
            conn = _conn()
            c = conn.cursor()
            c.execute('UPDATE users SET schema_name=%s WHERE id=%s',
                      (schema, user['id']))
            conn.commit()
            conn.close()
        except Exception:
            pass
    return schema


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
                schema = user.get('schema_name') or f'emp_{user["id"]}'
                if not user.get('schema_name'):
                    c2 = _conn()
                    cc = c2.cursor()
                    cc.execute('UPDATE users SET schema_name=%s WHERE id=%s',
                               (schema, user['id']))
                    c2.commit()
                    c2.close()
                try:
                    _init_user_schema(schema)
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

BLOG_POSTS = [
    {
        'slug': 'como-prospectar-clientes-b2b',
        'titulo': 'Como Prospectar Clientes B2B em 2026: Guia Completo',
        'desc': 'Aprenda as melhores estratégias de prospecção B2B: outbound, inbound, automação com IA e ferramentas para gerar leads qualificados.',
        'keywords': 'prospecção B2B, como prospectar clientes, geração de leads B2B, vendas B2B',
        'data': '2026-03-15',
        'tempo': '8 min',
        'conteudo': """
<p>A prospecção B2B é o processo de identificar e abordar potenciais clientes empresariais. Em 2026, as empresas que prosperam são as que combinam <strong>tecnologia com personalização</strong>.</p>

<h2>O que é prospecção B2B?</h2>
<p>Prospecção B2B (Business-to-Business) é a busca ativa por empresas que podem se beneficiar do seu produto ou serviço. Diferente do B2C, o ciclo de vendas é mais longo, envolve múltiplos decisores e exige abordagens mais consultivas.</p>

<h2>As 5 melhores estratégias de prospecção B2B</h2>

<h3>1. Prospecção Outbound com IA</h3>
<p>A prospecção outbound evoluiu. Em vez de ligar para listas frias, ferramentas de IA como o <strong>TurboVenda</strong> identificam empresas que se encaixam no seu perfil ideal de cliente (ICP) automaticamente, coletando dados como telefone, e-mail, CNPJ e porte da empresa.</p>

<h3>2. E-mail Marketing B2B Personalizado</h3>
<p>E-mails genéricos têm taxa de abertura de 5%. E-mails personalizados com o nome da empresa, setor e dor específica chegam a <strong>35% de abertura</strong>. A chave é usar dados do lead para criar mensagens relevantes.</p>

<h3>3. LinkedIn como canal de prospecção</h3>
<p>O LinkedIn concentra 80% dos leads B2B gerados em redes sociais. Conecte-se com decisores, publique conteúdo de valor e use mensagens diretas para iniciar conversas.</p>

<h3>4. Indicações e parcerias estratégicas</h3>
<p>Clientes satisfeitos são sua melhor fonte de novos leads. Crie um programa de indicação estruturado com incentivos claros.</p>

<h3>5. Marketing de conteúdo (Inbound)</h3>
<p>Blog posts, webinars e materiais ricos atraem leads que já estão pesquisando soluções. O custo por lead do inbound é 62% menor que o outbound tradicional.</p>

<h2>Como automatizar a prospecção B2B</h2>
<p>A automação elimina tarefas repetitivas e permite que sua equipe foque no que importa: vender. Um CRM com prospecção automática como o TurboVenda faz o trabalho de pesquisar empresas, coletar contatos e até enviar a primeira abordagem — tudo no piloto automático.</p>

<h2>Métricas essenciais de prospecção</h2>
<ul>
<li><strong>Taxa de resposta:</strong> quantos leads respondem sua abordagem (meta: &gt;10%)</li>
<li><strong>Taxa de conversão:</strong> quantos viram oportunidades reais (meta: &gt;3%)</li>
<li><strong>Custo por lead (CPL):</strong> quanto você gasta para gerar cada lead</li>
<li><strong>Tempo médio de ciclo:</strong> dias entre primeiro contato e fechamento</li>
</ul>

<h2>Conclusão</h2>
<p>A prospecção B2B em 2026 exige um mix de tecnologia e toque humano. Automatize a pesquisa e a abordagem inicial, mas mantenha a personalização nas interações. Ferramentas como o TurboVenda permitem que mesmo equipes pequenas prospectem como grandes empresas.</p>
"""
    },
    {
        'slug': 'automacao-comercial-guia-completo',
        'titulo': 'Automação Comercial: Como Vender Mais Gastando Menos',
        'desc': 'Descubra como a automação comercial com IA pode multiplicar suas vendas B2B. Guia prático com exemplos reais e ferramentas.',
        'keywords': 'automação comercial, automação de vendas, CRM automático, robô de vendas',
        'data': '2026-03-20',
        'tempo': '7 min',
        'conteudo': """
<p>A automação comercial não é mais luxo de grandes empresas. Com as ferramentas certas, qualquer equipe de vendas pode automatizar tarefas repetitivas e focar no fechamento.</p>

<h2>O que é automação comercial?</h2>
<p>É o uso de tecnologia para executar tarefas de vendas automaticamente: desde a busca por leads até o envio de e-mails de follow-up, passando pela organização do pipeline.</p>

<h2>O que você pode automatizar hoje</h2>

<h3>Prospecção de leads</h3>
<p>Em vez de pesquisar manualmente no Google, um robô de prospecção busca empresas por segmento, cidade e palavras-chave, coletando nome, telefone, e-mail e CNPJ automaticamente.</p>

<h3>Primeiro contato (e-mail e WhatsApp)</h3>
<p>Com templates inteligentes gerados por IA, cada mensagem é personalizada com o nome da empresa e uma proposta de valor específica para o segmento do lead.</p>

<h3>Follow-up automático</h3>
<p>70% das vendas B2B acontecem após o 5º contato. Sequências automáticas garantem que nenhum lead seja esquecido, com intervalos programados entre cada mensagem.</p>

<h3>Pipeline e CRM</h3>
<p>Leads se movem automaticamente pelo funil conforme interagem: abriu e-mail → "Interessado", respondeu → "Em negociação", agendou reunião → "Qualificado".</p>

<h2>ROI da automação comercial</h2>
<p>Empresas que implementam automação comercial reportam em média:</p>
<ul>
<li><strong>3x mais leads</strong> gerados por vendedor</li>
<li><strong>40% menos tempo</strong> em tarefas administrativas</li>
<li><strong>25% aumento</strong> na taxa de conversão</li>
<li><strong>50% redução</strong> no custo por lead</li>
</ul>

<h2>Como começar</h2>
<p>O TurboVenda combina prospecção automática + CRM + envio de e-mails e WhatsApp em uma única plataforma. Configure seu perfil de cliente ideal, ative o robô e comece a receber leads qualificados em minutos.</p>
"""
    },
    {
        'slug': 'crm-para-pequenas-empresas',
        'titulo': 'CRM para Pequenas Empresas: Por Que Você Precisa de Um',
        'desc': 'Descubra por que um CRM é essencial para pequenas empresas e como escolher o ideal. Comparativo de funcionalidades e preços.',
        'keywords': 'CRM pequenas empresas, CRM barato, CRM simples, software de vendas PME',
        'data': '2026-03-25',
        'tempo': '6 min',
        'conteudo': """
<p>Se você ainda controla seus clientes em planilhas, está perdendo vendas. Um CRM (Customer Relationship Management) organiza seus contatos, automatiza tarefas e mostra exatamente onde cada negociação está.</p>

<h2>Sinais de que você precisa de um CRM</h2>
<ul>
<li>Leads se perdem entre planilhas e e-mails</li>
<li>Você não sabe quantos clientes estão em cada etapa do funil</li>
<li>Follow-ups são esquecidos com frequência</li>
<li>Não há histórico centralizado de conversas com clientes</li>
<li>Relatórios de vendas levam horas para serem montados</li>
</ul>

<h2>O que um bom CRM para PME precisa ter</h2>

<h3>Pipeline visual (Kanban)</h3>
<p>Visualize todas as suas negociações em colunas: Novo Lead → Contatado → Interessado → Proposta → Fechado. Arraste e solte para mover leads entre etapas.</p>

<h3>Integração com e-mail e WhatsApp</h3>
<p>Envie mensagens diretamente do CRM sem alternar entre aplicativos. Todo histórico de comunicação fica registrado no perfil do cliente.</p>

<h3>Automação de tarefas</h3>
<p>Lembretes de follow-up, e-mails automáticos, atribuição de leads — quanto menos trabalho manual, mais tempo para vender.</p>

<h3>Relatórios simples</h3>
<p>Dashboard com métricas essenciais: leads gerados, taxa de conversão, receita por período. Sem complicação.</p>

<h2>CRM + Prospecção: a combinação perfeita</h2>
<p>A maioria dos CRMs para PME só organiza leads que você já tem. O TurboVenda vai além: ele <strong>encontra novos leads automaticamente</strong> e já coloca no seu pipeline pronto para abordar. É CRM e prospecção numa única ferramenta, a partir de R$0/mês.</p>
"""
    },
    {
        'slug': 'como-gerar-leads-qualificados',
        'titulo': 'Como Gerar Leads Qualificados: 7 Estratégias Práticas',
        'desc': 'Aprenda 7 estratégias comprovadas para gerar leads B2B qualificados sem gastar fortunas com marketing. Técnicas gratuitas e pagas.',
        'keywords': 'gerar leads qualificados, geração de leads, captar clientes, leads B2B qualificados',
        'data': '2026-03-28',
        'tempo': '9 min',
        'conteudo': """
<p>Quantidade sem qualidade é desperdício. O segredo não é gerar mais leads, mas gerar leads que realmente têm potencial de compra. Veja 7 estratégias práticas.</p>

<h2>O que é um lead qualificado?</h2>
<p>Um lead qualificado é uma empresa ou pessoa que:</p>
<ul>
<li>Tem o <strong>perfil</strong> do seu cliente ideal (porte, segmento, localização)</li>
<li>Tem a <strong>necessidade</strong> que seu produto resolve</li>
<li>Tem <strong>orçamento</strong> para investir</li>
<li>Tem <strong>autoridade</strong> para tomar a decisão de compra</li>
</ul>

<h2>7 estratégias para gerar leads qualificados</h2>

<h3>1. Defina seu ICP (Ideal Customer Profile)</h3>
<p>Antes de prospectar, saiba exatamente quem você busca: segmento, porte, faturamento, localização, cargo do decisor. Quanto mais específico, mais qualificados serão seus leads.</p>

<h3>2. Use dados públicos a seu favor</h3>
<p>CNPJ, Receita Federal, sites de empresas — há uma mina de informações públicas. Ferramentas como o TurboVenda cruzam essas fontes automaticamente para enriquecer cada lead.</p>

<h3>3. Segmente por dor, não por demografia</h3>
<p>Em vez de "empresas de 10-50 funcionários", pense em "empresas que provavelmente sofrem com [problema que você resolve]". A abordagem muda completamente.</p>

<h3>4. Crie conteúdo que atrai decisores</h3>
<p>Um artigo sobre "Como reduzir custos operacionais em 30%" atrai gerentes e diretores. Um post genérico sobre seu produto atrai curiosos. Foque em conteúdo que resolve problemas reais.</p>

<h3>5. Automatize a qualificação</h3>
<p>Use critérios automáticos para classificar leads: empresa com site = +10 pontos, tem telefone = +5, segmento alvo = +20. Foque nos leads com maior pontuação.</p>

<h3>6. Sequências de e-mail multi-toque</h3>
<p>Um único e-mail converte 2%. Uma sequência de 5 e-mails converte 15%. Cada mensagem deve agregar valor e criar urgência progressiva.</p>

<h3>7. Peça indicações sistematicamente</h3>
<p>Após cada venda fechada, peça 3 indicações. Leads indicados convertem 4x mais que leads frios.</p>

<h2>Ferramenta certa faz diferença</h2>
<p>O TurboVenda automatiza as estratégias 1, 2, 5 e 6 em uma única plataforma. Configure seu ICP, ative o robô e receba leads qualificados no seu pipeline todos os dias.</p>
"""
    },
    {
        'slug': 'email-marketing-b2b-templates',
        'titulo': 'E-mail Marketing B2B: 5 Templates que Convertem',
        'desc': 'Templates prontos de e-mail B2B para prospecção, follow-up e reengajamento. Copie, personalize e envie. Taxas de conversão reais.',
        'keywords': 'email marketing B2B, templates email comercial, email de prospecção, cold email',
        'data': '2026-04-01',
        'tempo': '7 min',
        'conteudo': """
<p>O e-mail ainda é o canal B2B com melhor ROI: R$36 para cada R$1 investido. Mas só funciona com a mensagem certa. Aqui estão 5 templates testados e aprovados.</p>

<h2>Regras de ouro do e-mail B2B</h2>
<ul>
<li><strong>Assunto curto</strong> (máx. 50 caracteres) — personalizado com nome da empresa</li>
<li><strong>Primeira linha</strong> mostra que você pesquisou sobre a empresa</li>
<li><strong>Proposta de valor</strong> clara em uma frase</li>
<li><strong>CTA único</strong> — uma pergunta ou ação, não três</li>
<li><strong>Assinatura profissional</strong> com cargo e telefone</li>
</ul>

<h2>Template 1: Primeiro contato</h2>
<p><em>Assunto: {Nome da empresa} + [benefício principal]</em></p>
<p>Olá {Nome},<br>Vi que a {Empresa} atua com {segmento} em {cidade}. Empresas desse setor costumam enfrentar [dor comum]. Nós ajudamos empresas como a {Empresa concorrente} a resolver isso, gerando [resultado específico]. Vale uma conversa de 15 min esta semana?</p>

<h2>Template 2: Follow-up (3 dias depois)</h2>
<p><em>Assunto: Re: {assunto anterior}</em></p>
<p>{Nome}, sei que a rotina é corrida. Só queria reforçar: temos ajudado empresas de {segmento} a {resultado}. Se fizer sentido, posso mostrar em 10 minutos como funciona. Qual o melhor horário?</p>

<h2>Template 3: Prova social</h2>
<p><em>Assunto: Como {empresa similar} conseguiu {resultado}</em></p>
<p>Olá {Nome},<br>A {empresa similar do mesmo segmento} estava com o mesmo desafio que muitas empresas de {segmento}: {dor}. Em 3 meses usando nossa solução, conseguiram {resultado com números}. Acha que vale explorar algo assim para a {Empresa}?</p>

<h2>Template 4: Último follow-up</h2>
<p><em>Assunto: Devo parar de enviar e-mails?</em></p>
<p>{Nome}, não quero ser inconveniente. Se {solução} não faz sentido para a {Empresa} agora, sem problemas. Mas se em algum momento quiser explorar como {benefício}, estou à disposição. Posso entrar em contato em outro momento?</p>

<h2>Template 5: Reengajamento</h2>
<p><em>Assunto: Novidades para {segmento}</em></p>
<p>Olá {Nome},<br>Há uns meses conversamos sobre {tema}. Desde então, lançamos {novidade/funcionalidade} que tem ajudado empresas de {segmento} a {resultado novo}. Quer ver como ficou?</p>

<h2>Automatize seus e-mails</h2>
<p>No TurboVenda, a IA gera mensagens personalizadas para cada lead usando os dados da empresa. Você configura a sequência uma vez e o sistema envia automaticamente, com intervalos programados e follow-ups inteligentes.</p>
"""
    },
]


@app.route('/')
def landing():
    return render_template('landing.html', ga_id=GA_MEASUREMENT_ID)


@app.route('/blog')
def blog_index():
    return render_template('blog.html',
                           posts=BLOG_POSTS,
                           ga_id=GA_MEASUREMENT_ID)


@app.route('/blog/<slug>')
def blog_post(slug):
    post = next((p for p in BLOG_POSTS if p['slug'] == slug), None)
    if not post:
        return redirect('/blog')
    return render_template('blog_post.html',
                           post=post,
                           posts=BLOG_POSTS,
                           ga_id=GA_MEASUREMENT_ID)


@app.route('/robots.txt')
def robots_txt():
    txt = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /api/\n"
        "Disallow: /admin/\n"
        "Disallow: /dashboard\n"
        "Disallow: /configurar\n"
        "Disallow: /logout\n\n"
        "Sitemap: https://turbovenda.com.br/sitemap.xml\n"
    )
    return app.response_class(txt, mimetype='text/plain')


@app.route('/sitemap.xml')
def sitemap_xml():
    urls = [
        ('https://turbovenda.com.br/', 'weekly', '1.0'),
        ('https://turbovenda.com.br/cadastro', 'monthly', '0.8'),
        ('https://turbovenda.com.br/blog', 'weekly', '0.9'),
        ('https://turbovenda.com.br/login', 'monthly', '0.6'),
    ]
    for p in BLOG_POSTS:
        urls.append((
            f"https://turbovenda.com.br/blog/{p['slug']}",
            'monthly', '0.7'
        ))
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for loc, freq, pri in urls:
        xml += (f'  <url>\n    <loc>{loc}</loc>\n'
                f'    <changefreq>{freq}</changefreq>\n'
                f'    <priority>{pri}</priority>\n  </url>\n')
    xml += '</urlset>\n'
    return app.response_class(xml, mimetype='application/xml')


@app.route('/dashboard')
@login_required
def dashboard():
    uid = session.get('user_id')
    schema = f'emp_{uid}'
    user = get_current_user() or {'id': uid, 'schema_name': schema,
                                   'empresa_nome': '', 'email': ''}
    if not user.get('schema_name'):
        user['schema_name'] = schema
        try:
            conn = _conn()
            c = conn.cursor()
            c.execute('UPDATE users SET schema_name=%s WHERE id=%s',
                      (schema, uid))
            conn.commit()
            conn.close()
        except Exception:
            pass
    schema = user['schema_name']
    stats = get_stats(schema)
    return render_template('dashboard.html',
                           bot=schema,
                           user=user,
                           stats=stats,
                           name=user.get('empresa_nome') or 'Minha Empresa',
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
    wa_proc = _procs.get(schema, {}).get('wa')
    wa_running = wa_proc is not None and wa_proc.poll() is None
    wa_exit = None
    if wa_proc is not None and wa_proc.poll() is not None:
        wa_exit = wa_proc.returncode
        _procs.setdefault(schema, {})['wa'] = None
    return jsonify({
        'busca': _proc_running(schema, 'busca'),
        'wa': wa_running,
        'wa_exit': wa_exit,
        'linkedin': _proc_running(schema, 'linkedin'),
    })


@app.route('/api/<bot>/qr')
@login_required
def api_bot_qr(bot):
    base = os.path.dirname(os.path.abspath(__file__))
    qr_path = os.path.join(base, 'robo_pili', 'wa_qr.png')
    if os.path.exists(qr_path):
        return send_file(qr_path, mimetype='image/png',
                         max_age=0)
    return '', 404


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
    was_running = False
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        was_running = True
    _procs.setdefault(schema, {})[canal] = None
    return jsonify({'status': 'stopped', 'canal': canal, 'was_running': was_running})


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
    ok, msg = _check_lead_limit(schema)
    if not ok:
        return jsonify({'error': msg, 'limit_reached': True}), 403
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
            track_token = _get_email_track_token(schema, p['empresa_id'])
            seq_base_url = os.environ.get('BASE_URL', 'https://turbovenda.com.br')
            track_open_url = f'{seq_base_url}/t/{track_token}/open.png'
            track_click_url = f'{seq_base_url}/t/{track_token}/click?url={_urlquote(link_agenda, safe="")}'
            assunto = (passo.get('assunto', '')
                .replace('{{nome}}', nome)
                .replace('{nome}', nome)
                .replace('{{link_agenda}}', track_click_url)
                .replace('{link_agenda}', track_click_url))
            raw_msg = passo.get('mensagem') or passo.get('html_template') or ''
            raw_msg = (raw_msg
                .replace('{{nome}}', nome)
                .replace('{nome}', nome)
                .replace('{{link_agenda}}', track_click_url)
                .replace('{link_agenda}', track_click_url))
            if '<html' not in raw_msg.lower() and '<body' not in raw_msg.lower():
                html = '<div style="font-family:sans-serif;font-size:14px;color:#333">' + raw_msg.replace('\n', '<br>') + '</div>'
            else:
                html = raw_msg
            html = _inject_tracking_pixel(html, track_open_url)
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
    user = get_current_user() or {}
    return {
        'sender_email': os.environ.get('EMAIL_FROM',
                                       'contato@turbovenda.com.br'),
        'sender_name': (cfg.get('email_remetente_nome') or
                        cfg.get('empresa_nome') or ''),
        'reply_to': user.get('email') or '',
        'smtp_host': cfg.get('smtp_host') or '',
        'smtp_port': cfg.get('smtp_port') or 587,
        'smtp_user': cfg.get('smtp_user') or '',
        'smtp_password': cfg.get('smtp_password') or '',
        'resend_api_key': os.environ.get('RESEND_API_KEY', '') or '',
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
            payload = {'from': f'{sender_name} <{sender_email}>',
                       'to': [to_email],
                       'subject': subject,
                       'html': html}
            reply_to = ecfg.get('reply_to', '')
            if reply_to:
                payload['reply_to'] = [reply_to]
            r = http.post('https://api.resend.com/emails',
                          headers={'Authorization': f'Bearer {resend_key}',
                                   'Content-Type': 'application/json'},
                          json=payload,
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
    reenviar = data.get('reenviar', False)
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
    if reenviar:
        c.execute(f"SELECT id, nome_fantasia, email FROM empresas WHERE id IN ({ph}) AND email IS NOT NULL"
                  f" AND status NOT IN ('bounce','spam')",
                  lead_ids)
    else:
        try:
            c.execute(f"SELECT id, nome_fantasia, email FROM empresas WHERE id IN ({ph}) AND email IS NOT NULL"
                      f" AND (email_enviado IS NULL)"
                      f" AND status NOT IN ('bounce','spam')",
                      lead_ids)
        except Exception:
            conn.rollback()
            c.execute(f"SELECT id, nome_fantasia, email FROM empresas WHERE id IN ({ph}) AND email IS NOT NULL"
                      f" AND status NOT IN ('bounce','spam')",
                      lead_ids)
    leads = c.fetchall()
    conn.close()
    if not leads:
        return jsonify({'error': 'Nenhum lead elegível (todos bounce/spam ou sem email)'}), 400

    empresa_nome = user['empresa_nome'] if user else ''
    base_url = os.environ.get('BASE_URL', request.host_url.rstrip('/')).replace('http://', 'https://')
    enviados = erros = 0
    for lead in leads:
        nome = lead['nome_fantasia'] or 'empresa'
        link_agenda = _get_link_agenda(schema, lead['id'])
        track_token = _get_email_track_token(schema, lead['id'])
        track_open_url = f'{base_url}/t/{track_token}/open.png'
        track_click_url = f'{base_url}/t/{track_token}/click?url={_urlquote(link_agenda, safe="")}'
        html = (tpl_html.replace('{{nome}}', nome)
                        .replace('{{DEMO_CAL_LINK}}', track_click_url)
                        .replace('{{cal_link}}', track_click_url)
                        .replace('{{link_agenda}}', track_click_url)
                        .replace('{{EMPRESA}}', empresa_nome))
        html = _inject_tracking_pixel(html, track_open_url)
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
    reenviar = data.get('reenviar', False)
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
        if reenviar:
            c.execute("""SELECT id, nome_fantasia, email, segmento, cidade, estado
                         FROM empresas WHERE email IS NOT NULL AND email != ''
                         AND status NOT IN ('bounce','spam')
                         ORDER BY score DESC LIMIT 500""")
        else:
            try:
                c.execute("""SELECT id, nome_fantasia, email, segmento, cidade, estado
                             FROM empresas WHERE email IS NOT NULL AND email != ''
                             AND email_enviado IS NULL
                             AND status NOT IN ('bounce','spam')
                             ORDER BY score DESC LIMIT 500""")
            except Exception:
                conn.rollback()
                c.execute("""SELECT id, nome_fantasia, email, segmento, cidade, estado
                             FROM empresas WHERE email IS NOT NULL AND email != ''
                             AND status NOT IN ('bounce','spam')
                             ORDER BY score DESC LIMIT 500""")
        leads = c.fetchall()
        conn.close()
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    if not leads:
        return jsonify({'error': 'nenhum lead com email cadastrado'}), 400

    base_url = os.environ.get('BASE_URL', request.host_url.rstrip('/')).replace('http://', 'https://')
    enviados = erros = 0
    for lead in leads:
        nome = lead['nome_fantasia'] or 'empresa'
        link_agenda = _get_link_agenda(schema, lead['id'])
        track_token = _get_email_track_token(schema, lead['id'])
        track_open_url = f'{base_url}/t/{track_token}/open.png'
        track_click_url = f'{base_url}/t/{track_token}/click?url={_urlquote(link_agenda, safe="")}'
        vars_map = {
            '{{nome}}': nome,
            '{{email}}': lead['email'] or '',
            '{{segmento}}': lead.get('segmento') or '',
            '{{cidade}}': lead.get('cidade') or '',
            '{{link_agenda}}': track_click_url,
            '{{cal_link}}': track_click_url,
            '{{DEMO_CAL_LINK}}': track_click_url,
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
        html = _inject_tracking_pixel(html, track_open_url)

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
    email_cor_header = data.get('email_cor_header', '#1a2332')
    email_cor_botao = data.get('email_cor_botao', '#2563eb')
    email_cor_texto = data.get('email_cor_texto', '#ffffff')
    resend_api_key = data.get('resend_api_key', '')
    smtp_host = data.get('smtp_host', '')
    smtp_port = data.get('smtp_port', 587)
    smtp_user = data.get('smtp_user', '')
    smtp_password = data.get('smtp_password', '')
    serper_api_key = data.get('serper_api_key', '')

    # Validação de campos obrigatórios
    erros = []
    if not empresa_nome.strip():
        erros.append('Nome da empresa')
    if not descricao.strip():
        erros.append('Descrição do produto/serviço')
    if erros:
        return jsonify({'error': f'Preencha os campos obrigatórios: {", ".join(erros)}'}), 400

    conn = None
    try:
        print(f'[save_config/{schema}] Iniciando save...', flush=True)
        conn = _conn(schema)
        c = conn.cursor()
        # Garantir colunas existem (schemas antigos)
        for col_stmt in [
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS email_remetente TEXT",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS email_remetente_nome TEXT",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS resend_api_key TEXT",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS smtp_host TEXT",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS smtp_port INTEGER DEFAULT 587",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS smtp_user TEXT",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS smtp_password TEXT",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS serper_api_key TEXT",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS email_cor_header TEXT DEFAULT '#1a2332'",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS email_cor_botao TEXT DEFAULT '#2563eb'",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS email_cor_texto TEXT DEFAULT '#ffffff'",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS horario_inicio INTEGER DEFAULT 9",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS horario_fim INTEGER DEFAULT 18",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS duracao_reuniao INTEGER DEFAULT 30",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS dias_semana TEXT DEFAULT '1,2,3,4,5'",
        ]:
            try:
                c.execute(col_stmt)
            except Exception:
                conn.rollback()
        conn.commit()
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
                         email_cor_header=%s, email_cor_botao=%s, email_cor_texto=%s,
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
                      email_cor_header or '#1a2332',
                      email_cor_botao or '#2563eb',
                      email_cor_texto or '#ffffff',
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
    result = _gerar_termos(
        data.get('empresa_nome', ''),
        data.get('descricao', ''),
        data.get('website', '')
    )
    return jsonify({'ok': True, 'termos': result['termos'], 'cargos': result['cargos']})


def _gerar_termos(empresa_nome: str, descricao: str, website: str) -> dict:
    """Gera termos de busca dinamicamente a partir da descricao do usuario."""
    desc_lower = descricao.lower()

    # ── 0. Detectar se descricao e sobre PRODUTOS vendidos ──
    _VERBOS_PRODUTO = ['vendemos', 'fabricamos', 'produzimos', 'oferecemos',
                       'desenvolvemos', 'criamos', 'fornecemos', 'trabalhamos com']
    _is_product_desc = any(v in desc_lower for v in _VERBOS_PRODUTO)

    # Encontrar a frase do produto (tudo entre verbo e primeiro ponto/virgula)
    _produto_frase = ''
    for v in _VERBOS_PRODUTO:
        idx = desc_lower.find(v)
        if idx >= 0:
            rest = desc_lower[idx + len(v):]
            end = len(rest)
            for sep in ['.', ';', ' para ', ' nos ', ' no ', ' na ', ' em ']:
                p = rest.find(sep)
                if p > 0:
                    end = min(end, p)
            _produto_frase = rest[:end].strip(' ,')
            break

    # ── 1. Extrair SEGMENTOS-ALVO (tipos de empresa cliente) ──

    _ORG = (
        r'cooperativa|cerealista|agroindustria|agroindústria|industria|indústria|'
        r'fabrica|fábrica|usina|hospital|clinica|clínica|escola|faculdade|'
        r'escritorio|escritório|construtora|distribuidora|transportadora|'
        r'atacadista|imobiliaria|imobiliária|concessionaria|concessionária|'
        r'mineradora|frigorifico|frigorífico|armazem|armazém|silo|'
        r'laboratorio|laboratório|farmacia|farmácia|drogaria|loja|'
        r'franquia|startup|consultoria|corretora|provedor|agencia|agência|'
        r'hotel|pousada|restaurante|supermercado|academia|grafica|gráfica|'
        r'editora|condominio|condomínio|shopping|oficina|autopecas|autopeças|'
        r'padaria|torrefadora|moinho|beneficiadora|exportadora|'
        r'trading|revendedora|fazenda|pecuaria|pecuária|confinamento|'
        r'pet shop|coworking|call center|software house|'
        r'incorporadora|marmoraria|funilaria|bpo'
    )

    segmentos = []
    seen_segs = set()

    def _add_seg(s):
        s = s.strip()
        if len(s) < 4 or len(s) > 35:
            return
        if s in seen_segs:
            return
        if empresa_nome and empresa_nome.lower() in s:
            return
        rejects = [
            'brasil', 'norte', 'sul', 'sudeste', 'nordeste', 'centro-oeste',
            'grande porte', 'medio porte', 'pequeno porte',
            'gerente', 'diretor', 'coordenador', 'responsavel',
            'compras', 'operacoes', 'infraestrutura', 'vendas',
            'nosso', 'nossa', 'todo', 'toda',
        ]
        sl = s.lower()
        for r in rejects:
            if sl.startswith(r) or sl == r:
                return
        if re.search(r'\b(?:que|quem|onde|como|quando)\b', sl):
            return
        estados_nomes = [
            'sao paulo', 'minas gerais', 'rio de janeiro', 'parana',
            'santa catarina', 'rio grande do sul', 'bahia', 'goias',
            'mato grosso', 'espirito santo', 'pernambuco', 'ceara',
        ]
        if sl in estados_nomes:
            return
        seen_segs.add(s)
        segmentos.append(s)

    # a) Extrai tipos de organizacao — mas ignora se esta na frase de produto
    for m in re.finditer(
        r'\b(' + _ORG + r')(?:\s+(?:de\s+|da\s+|do\s+|das\s+|dos\s+)?[a-záàâãéêíóôõúüç]+){0,2}',
        desc_lower
    ):
        seg = m.group(0).strip()
        pos = m.start()
        # Verifica se esta dentro da frase de produto (olha a FRASE, nao so 30 chars)
        # Encontra inicio da frase (ultimo ponto ou inicio)
        frase_start = max(desc_lower.rfind('.', 0, pos), desc_lower.rfind(';', 0, pos), 0)
        frase = desc_lower[frase_start:pos]
        is_proprio = any(v in frase for v in _VERBOS_PRODUTO)
        if not is_proprio:
            _add_seg(seg)

    # b) Extrai do padrao "cliente ideal e ... de XXXX, YYYY e ZZZZ"
    cliente_match = re.search(
        r'cliente[s]?\s+ideal[^.]*?(?:de|em|para)\s+([^.]+)',
        desc_lower
    )
    if cliente_match:
        trecho = cliente_match.group(1)
        trecho = re.sub(
            r'(?:gerente|diretor|coordenador|responsavel|chefe|head|'
            r'supervisor|dono|proprietario|socio)\s+(?:de\s+)?[^,]+,?\s*',
            '', trecho
        )
        partes = re.split(r'\s*,\s*|\s+e\s+', trecho)
        for parte in partes:
            parte = re.sub(r'^(?:os?|as?|de|da|do|das|dos|uns?|umas?)\s+', '', parte.strip())
            if re.search(_ORG, parte):
                _add_seg(parte)

    # c) Extrai do padrao "atendemos XXXX"
    atende_match = re.search(r'atendemos\s+([^.]+)', desc_lower)
    if atende_match:
        partes = re.split(r'\s*,\s*|\s+e\s+', atende_match.group(1))
        for parte in partes:
            parte = re.sub(r'^(?:os?|as?|de|da|do|das|dos)\s+', '', parte.strip())
            if re.search(_ORG, parte):
                _add_seg(parte)

    # d) INFERIR clientes a partir do contexto de produto/industria
    _INDUSTRY_CLIENTS = {
        'agro': {
            'keywords': ['grão', 'graos', 'grãos', 'soja', 'milho', 'trigo', 'arroz',
                         'tombador', 'calador', 'secador', 'armazenagem', 'armazenamento',
                         'silo', 'moega', 'expedição', 'expedicao', 'colheita',
                         'cereal', 'fertilizante', 'adubo', 'defensivo', 'semente',
                         'irrigação', 'irrigacao', 'plantio', 'safra', 'agro',
                         'agricola', 'agrícola', 'pecuaria', 'pecuária'],
            'clients': ['cooperativa agricola', 'cerealista', 'armazem de graos',
                        'trading agricola', 'agroindustria', 'fazenda',
                        'empresa de armazenagem', 'beneficiadora de graos',
                        'exportadora de graos', 'silo de armazenagem',
                        'unidade de recebimento de graos'],
        },
        'construcao': {
            'keywords': ['construção', 'construcao', 'cimento', 'concreto', 'aço', 'aco',
                         'estrutura metalica', 'estrutura metálica', 'telhado', 'cobertura',
                         'obra', 'edificio', 'edifício', 'pavimentação', 'pavimentacao'],
            'clients': ['construtora', 'incorporadora', 'empreiteira',
                        'empresa de engenharia', 'condominio', 'shopping'],
        },
        'industrial': {
            'keywords': ['hidraulic', 'hidráulic', 'pneumatic', 'pneumátic',
                         'motor', 'valvula', 'válvula', 'bomba', 'compressor',
                         'maquina', 'máquina', 'equipamento industrial',
                         'torno', 'fresa', 'solda', 'metalurgia', 'usinagem',
                         'automação', 'automacao', 'esteira', 'correia'],
            'clients': ['industria', 'fabrica', 'mineradora', 'usina',
                        'metalurgica', 'siderurgica', 'frigorifico'],
        },
        'alimenticio': {
            'keywords': ['alimento', 'alimentício', 'alimenticio', 'embalagem de alimento',
                         'frigorifico', 'frigorífico', 'carne', 'laticinio', 'laticínio',
                         'bebida', 'processamento de alimento'],
            'clients': ['frigorifico', 'laticinio', 'fabrica de alimentos',
                        'industria alimenticia', 'supermercado', 'atacadista'],
        },
        'saude': {
            'keywords': ['saude', 'saúde', 'medico', 'médico', 'hospitalar', 'cirurg',
                         'diagnóstico', 'diagnostico', 'laboratorial', 'clinico', 'clínico',
                         'implante', 'protese', 'prótese', 'odonto'],
            'clients': ['hospital', 'clinica', 'laboratorio', 'farmacia'],
        },
        'logistica': {
            'keywords': ['logistica', 'logística', 'transporte', 'frete', 'carga',
                         'armazem geral', 'armazém geral', 'embalagem', 'palete',
                         'container', 'contêiner', 'rastreamento'],
            'clients': ['transportadora', 'distribuidora', 'atacadista',
                        'operador logistico', 'centro de distribuicao'],
        },
        'energia': {
            'keywords': ['energia', 'solar', 'fotovoltaic', 'eolica', 'eólica',
                         'eletric', 'elétric', 'gerador', 'transformador',
                         'subestação', 'subestacao', 'quadro eletrico'],
            'clients': ['industria', 'fabrica', 'condominio', 'shopping',
                        'cooperativa de energia', 'usina'],
        },
        'ti': {
            'keywords': ['software', 'sistema', 'aplicativo', 'app', 'plataforma',
                         'erp', 'crm', 'saas', 'cloud', 'nuvem', 'dados',
                         'inteligencia artificial', 'automação', 'automacao'],
            'clients': ['empresa de tecnologia', 'startup', 'escritorio',
                        'industria', 'consultoria', 'agencia'],
        },
    }

    if _is_product_desc and len(segmentos) < 3:
        for industry, data in _INDUSTRY_CLIENTS.items():
            if any(kw in desc_lower for kw in data['keywords']):
                for client in data['clients']:
                    _add_seg(client)

    # e) Fallback: palavras-chave frequentes — mas EXCLUI termos de produto
    if not segmentos:
        from collections import Counter
        stops = {
            'para', 'como', 'mais', 'nosso', 'nossa', 'nossos', 'nossas',
            'empresa', 'ideal', 'cliente', 'objetivo', 'meta', 'foco',
            'entre', 'desde', 'sobre', 'esse', 'essa', 'este', 'esta',
            'tambem', 'pode', 'deve', 'todo', 'toda', 'todos', 'todas',
            'muito', 'menos', 'cada', 'outro', 'outra', 'mesmo', 'mesma',
            'qual', 'quando', 'onde', 'porque', 'pois', 'ainda',
            'vendemos', 'oferecemos', 'somos', 'temos', 'fazemos',
            'atendemos', 'trabalhamos', 'atuamos', 'produzimos',
            'fabricamos', 'fornecemos', 'criamos', 'desenvolvemos',
            'servico', 'produto', 'solucao', 'sistema', 'plataforma',
            'brasil', 'nacional', 'porte',
            'qualidade', 'performance', 'alta', 'melhor', 'custo',
            'beneficio', 'desde', 'estados', 'estado',
            'equipamento', 'equipamentos', 'recebimento', 'expedicao',
        }
        palavras = re.findall(r'[a-záàâãéêíóôõúüç]{5,}', desc_lower)
        freq = Counter(p for p in palavras if p not in stops)
        segmentos = [w for w, _ in freq.most_common(8)]

    # ── 2. Extrair REGIOES / CIDADES ──
    TODAS_CIDADES = {
        'sul': ['Curitiba', 'Porto Alegre', 'Florianopolis', 'Londrina', 'Maringa',
                'Cascavel', 'Ponta Grossa', 'Chapeco', 'Joinville', 'Blumenau',
                'Caxias do Sul', 'Passo Fundo', 'Novo Hamburgo', 'Santa Maria',
                'Pelotas', 'Guarapuava', 'Toledo', 'Francisco Beltrao'],
        'centro-oeste': ['Goiania', 'Brasilia', 'Campo Grande', 'Cuiaba',
                         'Anapolis', 'Dourados', 'Rondonopolis', 'Rio Verde',
                         'Sinop', 'Lucas do Rio Verde', 'Sorriso',
                         'Primavera do Leste', 'Itumbiara'],
        'sudeste': ['Sao Paulo', 'Campinas', 'Ribeirao Preto', 'Sorocaba',
                    'Sao Jose dos Campos', 'Piracicaba', 'Belo Horizonte',
                    'Uberlandia', 'Rio de Janeiro', 'Vitoria', 'Jundiai',
                    'Bauru', 'Franca', 'Uberaba', 'Juiz de Fora'],
        'nordeste': ['Salvador', 'Recife', 'Fortaleza', 'Sao Luis', 'Natal',
                     'Joao Pessoa', 'Aracaju', 'Maceio', 'Teresina',
                     'Feira de Santana', 'Petrolina', 'Barreiras'],
        'norte': ['Manaus', 'Belem', 'Porto Velho', 'Palmas', 'Macapa'],
    }
    ESTADOS_POR_REGIAO = {
        'sul': ['PR', 'SC', 'RS'],
        'centro-oeste': ['GO', 'MT', 'MS', 'DF'],
        'sudeste': ['SP', 'MG', 'RJ', 'ES'],
        'nordeste': ['BA', 'PE', 'CE', 'MA', 'RN', 'PB', 'SE', 'AL', 'PI'],
        'norte': ['AM', 'PA', 'TO', 'RO', 'AC', 'RR', 'AP'],
    }

    regioes_match = []
    # Regioes explicitas (com word boundary para evitar falsos positivos)
    for regiao in TODAS_CIDADES:
        if re.search(r'\b' + re.escape(regiao) + r'\b', desc_lower):
            regioes_match.append(regiao)

    # Estados por sigla (2 letras maiusculas no texto original)
    _UF_REGIAO = {
        'PR': 'sul', 'SC': 'sul', 'RS': 'sul',
        'GO': 'centro-oeste', 'MT': 'centro-oeste', 'MS': 'centro-oeste', 'DF': 'centro-oeste',
        'SP': 'sudeste', 'MG': 'sudeste', 'RJ': 'sudeste', 'ES': 'sudeste',
        'BA': 'nordeste', 'PE': 'nordeste', 'CE': 'nordeste', 'MA': 'nordeste',
        'RN': 'nordeste', 'PB': 'nordeste', 'SE': 'nordeste', 'AL': 'nordeste', 'PI': 'nordeste',
        'AM': 'norte', 'PA': 'norte', 'TO': 'norte', 'RO': 'norte',
        'AC': 'norte', 'RR': 'norte', 'AP': 'norte',
    }
    for uf, reg in _UF_REGIAO.items():
        if re.search(r'\b' + uf + r'\b', descricao):
            if reg not in regioes_match:
                regioes_match.append(reg)

    # Estados por nome completo (word boundary)
    uf_map = {
        'paraná': 'sul', 'parana': 'sul',
        'santa catarina': 'sul',
        'rio grande do sul': 'sul',
        'goiás': 'centro-oeste', 'goias': 'centro-oeste',
        'mato grosso': 'centro-oeste',
        'mato grosso do sul': 'centro-oeste',
        'são paulo': 'sudeste', 'sao paulo': 'sudeste',
        'minas gerais': 'sudeste',
        'rio de janeiro': 'sudeste',
        'espírito santo': 'sudeste', 'espirito santo': 'sudeste',
        'bahia': 'nordeste', 'pernambuco': 'nordeste',
        'ceará': 'nordeste', 'ceara': 'nordeste',
        'maranhão': 'nordeste', 'maranhao': 'nordeste',
        'tocantins': 'norte',
    }
    for uf_nome, reg in uf_map.items():
        if re.search(r'\b' + re.escape(uf_nome) + r'\b', desc_lower):
            if reg not in regioes_match:
                regioes_match.append(reg)

    if any(x in desc_lower for x in ['todo o brasil', 'brasil inteiro', 'nacional',
                                       'todo brasil']):
        regioes_match = list(TODAS_CIDADES.keys())

    if not regioes_match:
        regioes_match = list(TODAS_CIDADES.keys())

    cidades = []
    estados = []
    for reg in regioes_match:
        cidades.extend(TODAS_CIDADES.get(reg, []))
        estados.extend(ESTADOS_POR_REGIAO.get(reg, []))
    cidades = list(dict.fromkeys(cidades))
    estados = list(dict.fromkeys(estados))

    # ── 3. Extrair CARGOS ──
    cargos = []
    for m in re.finditer(
        r'\b((?:gerente|diretor|coordenador|responsavel|responsável|'
        r'chefe|head|supervisor|proprietario|proprietário|'
        r'socio|sócio|dono|ceo|cfo|cto|coo)'
        r'(?:\s+(?:de|da|do|geral|comercial|industrial|administrativo|'
        r'financeiro|operacoes|operações|compras|infraestrutura|'
        r'producao|produção|logistica|logística|marketing|vendas|'
        r'agricola|agrícola|tecnico|técnico|ti|rh|recursos\s+humanos))*)',
        desc_lower
    ):
        c = m.group(0).strip().title()
        if len(c) > 3 and c not in cargos:
            cargos.append(c)

    cargos_base = [
        'Diretor Geral', 'Diretor Comercial', 'Proprietario',
        'Socio-diretor', 'CEO', 'Gerente Administrativo',
        'Gerente Comercial', 'Gerente de Operacoes',
    ]
    cargos = list(dict.fromkeys(cargos + cargos_base))

    # ── 4. Gerar termos ──
    PADROES = [
        '{seg} {loc} contato site:.com.br',
        '{seg} {loc} telefone email',
        '{seg} {loc} quem somos',
        'empresas de {seg} {loc}',
        '{seg} {loc} endereco telefone',
        '{seg} {loc} CNPJ contato',
        'lista {seg} {loc}',
        'diretorio {seg} {loc}',
    ]

    termos = set()
    for seg in segmentos:
        n_cids = min(6, len(cidades))
        cids = random.sample(cidades, n_cids)
        for cid in cids:
            pat = random.choice(PADROES)
            termos.add(pat.format(seg=seg, loc=cid))
        ufs = random.sample(estados, min(3, len(estados)))
        for uf in ufs:
            termos.add(f'{seg} {uf} contato site:.com.br')

    while len(termos) < 130:
        seg = random.choice(segmentos)
        loc = random.choice(cidades + estados)
        pat = random.choice(PADROES)
        termos.add(pat.format(seg=seg, loc=loc))

    lista = list(termos)
    random.shuffle(lista)
    return {'termos': lista, 'cargos': cargos}






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
    uid = request.token_user.get('user_id') or request.token_user.get('id')
    ok, msg = _check_lead_limit(schema, uid=uid)
    if not ok:
        return jsonify({'error': msg, 'limit_reached': True}), 403
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
# GERAR MENSAGEM WHATSAPP (sem IA)
# =============================================================================

@app.route('/api/<bot>/config/generate-msg', methods=['POST'])
@login_required
def api_generate_msg(bot):
    data = request.get_json(silent=True) or {}
    empresa = data.get('empresa_nome', '')
    descricao = data.get('descricao', '')
    website = data.get('website', '').strip()
    if not descricao:
        return jsonify({'error': 'Preencha a descrição da empresa'}), 400

    pitch = _extrair_pitch(descricao, empresa, max_chars=100)
    pitch_lower = pitch[0].lower() + pitch[1:] if pitch else ''
    tipo = data.get('tipo', 'whatsapp')

    site_link = ''
    if website:
        url = website if website.startswith('http') else f'https://{website}'
        site_link = '\n\n🔗 ' + url

    if tipo == 'followup':
        mensagem = (
            "{{nome}}, te mandei uma msg sobre a " + empresa + ".\n\n"
            "Resumindo: ajudamos empresas a " + pitch_lower + ".\n\n"
            "Vale 15 min? {{link_agenda}}" + site_link
        )
    else:
        mensagem = (
            "Oi {{nome}}! 👋\n\n"
            "Aqui é da " + empresa
            + " — ajudamos empresas a " + pitch_lower + ".\n\n"
            "Posso te mostrar em 15 min como funciona?\n"
            "{{cal_link}}" + site_link
        )

    return jsonify({'ok': True, 'mensagem': mensagem})


@app.route('/api/<bot>/config/generate-email', methods=['POST'])
@login_required
def api_generate_email(bot):
    data = request.get_json(silent=True) or {}
    empresa = data.get('empresa_nome', '') or 'Sua Empresa'
    descricao = data.get('descricao', '')
    website = data.get('website', '').strip()
    if not descricao:
        return jsonify({'error': 'Preencha a descrição da empresa'}), 400

    pitch = _extrair_pitch(descricao, empresa, max_chars=150)
    pitch_lower = pitch[0].lower() + pitch[1:] if pitch else ''
    cor_header = data.get('cor_header') or '#1a2332'
    cor_btn = data.get('cor_botao') or '#2563eb'
    cor_texto = data.get('cor_texto') or '#ffffff'
    if cor_header == '#1a2332' and website:
        site_h, site_b = _extrair_cores_site(website)
        cor_header = site_h
        cor_btn = site_b if cor_btn == '#2563eb' else cor_btn
    site_url = ''
    site_limpo = ''
    if website:
        site_url = website if website.startswith('http') else f'https://{website}'
        site_limpo = re.sub(r'^https?://(www\.)?', '', website).rstrip('/')

    site_link_inline = ''
    if site_url:
        site_link_inline = (
            ' (<a href="' + site_url + '" style="color:' + cor_btn
            + ';text-decoration:none;border-bottom:1px solid ' + cor_btn + ';">'
            + site_limpo + '</a>)')

    site_footer = ''
    if site_url:
        site_footer = (
            '<a href="' + site_url
            + '" style="color:#6b7280;text-decoration:none;border-bottom:1px solid #d1d5db;">'
            + site_limpo + '</a>')

    html = _build_email_html(
        empresa=empresa, pitch=pitch_lower, cor_header=cor_header,
        cor_btn=cor_btn, cor_texto=cor_texto,
        site_link_inline=site_link_inline, site_footer=site_footer,
        site_url=site_url)

    assunto = '{{nome}}, posso te mostrar algo?'
    return jsonify({'ok': True, 'html': html, 'assunto': assunto})


def _build_email_html(*, empresa, pitch, cor_header, cor_btn, cor_texto,
                      site_link_inline, site_footer, site_url):
    """Monta o HTML profissional do email de prospecção."""
    site_display = site_url.replace("https://", "").replace("http://", "").rstrip("/") if site_url else ''

    header_site_row = ''
    if site_display:
        header_site_row = (
            '<tr><td style="padding:6px 48px 0;font-family:Segoe UI,Arial,sans-serif;'
            'font-size:12px;color:' + cor_texto + ';opacity:0.6;letter-spacing:0.5px;">'
            + site_display + '</td></tr>')

    footer_site = ''
    if site_footer:
        footer_site = '<br>' + site_footer

    site_btn = ''
    if site_url:
        site_btn = (
            '<tr><td align="center" style="padding:16px 0 0;">'
            '<a href="' + site_url + '" style="font-family:Segoe UI,Arial,sans-serif;'
            'font-size:13px;color:' + cor_btn + ';text-decoration:none;">'
            'Conheça nosso site &rarr;</a></td></tr>')

    # btn_light: versão clara da cor do botão para backgrounds
    # Converte hex para RGB e mistura com branco
    try:
        r = int(cor_btn[1:3], 16)
        g = int(cor_btn[3:5], 16)
        b = int(cor_btn[5:7], 16)
        btn_bg = f"#{min(r+200,255):02x}{min(g+200,255):02x}{min(b+200,255):02x}"
        btn_border = f"#{min(r+140,255):02x}{min(g+140,255):02x}{min(b+140,255):02x}"
    except Exception:
        btn_bg = '#e0e7ff'
        btn_border = '#c7d2fe'

    return f'''<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{empresa}</title>
</head>
<body style="margin:0;padding:0;background-color:#f3f4f6;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f3f4f6;">
<tr><td align="center" style="padding:40px 16px;">

<!-- CARD -->
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e5e7eb;">

<!-- HEADER BAR -->
<tr><td style="background-color:{cor_header};padding:36px 48px 30px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0">
<tr>
<td style="font-family:Segoe UI,Arial,sans-serif;font-size:24px;font-weight:800;color:{cor_texto};letter-spacing:-0.5px;">{empresa}</td>
</tr>
{header_site_row}
</table>
</td></tr>

<!-- ACCENT -->
<tr><td style="background-color:{cor_btn};height:3px;font-size:0;">&nbsp;</td></tr>

<!-- GREETING -->
<tr><td style="background-color:#ffffff;padding:36px 48px 0;">
<p style="margin:0;font-family:Segoe UI,Arial,sans-serif;font-size:16px;line-height:1.6;color:#1f2937;">
Olá <strong>{{{{nome}}}}</strong>,
</p>
</td></tr>

<!-- INTRO -->
<tr><td style="background-color:#ffffff;padding:20px 48px 0;">
<p style="margin:0;font-family:Segoe UI,Arial,sans-serif;font-size:15px;line-height:1.75;color:#374151;">
Sou da <strong>{empresa}</strong>{site_link_inline} e trabalho com empresas de
<strong>{{{{segmento}}}}</strong> em <strong>{{{{cidade}}}}</strong>.
</p>
</td></tr>

<!-- PITCH CARD -->
<tr><td style="background-color:#ffffff;padding:24px 48px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
       style="background-color:{btn_bg};border-left:4px solid {cor_btn};border-radius:0 8px 8px 0;">
<tr><td style="padding:20px 24px;">
<p style="margin:0;font-family:Segoe UI,Arial,sans-serif;font-size:14px;line-height:1.7;color:#1e293b;">
<strong style="font-size:15px;">O que fazemos:</strong><br>
Ajudamos empresas a {pitch}.
</p>
</td></tr>
</table>
</td></tr>

<!-- CTA TEXT -->
<tr><td style="background-color:#ffffff;padding:0 48px 28px;">
<p style="margin:0;font-family:Segoe UI,Arial,sans-serif;font-size:15px;line-height:1.75;color:#374151;">
Posso te mostrar em <strong>15 minutos</strong> como funciona na prática?
</p>
</td></tr>

<!-- CTA BUTTON -->
<tr><td align="center" style="background-color:#ffffff;padding:0 48px 12px;">
<table role="presentation" cellpadding="0" cellspacing="0">
<tr><td style="background-color:{cor_btn};border-radius:10px;">
<a href="{{{{link_agenda}}}}" style="display:inline-block;font-family:Segoe UI,Arial,sans-serif;font-size:15px;font-weight:700;color:#ffffff;text-decoration:none;padding:16px 48px;letter-spacing:0.3px;">
&#128197; Agendar conversa de 15 min
</a>
</td></tr>
</table>
</td></tr>

<!-- SITE LINK -->
{site_btn}

<!-- SPACER -->
<tr><td style="background-color:#ffffff;padding:16px 0 0;font-size:0;">&nbsp;</td></tr>

<!-- DIVIDER -->
<tr><td style="background-color:#ffffff;padding:0 48px;">
<div style="border-top:1px solid #e5e7eb;"></div>
</td></tr>

<!-- FOOTER -->
<tr><td style="background-color:#ffffff;padding:20px 48px 28px;">
<p style="margin:0;font-family:Segoe UI,Arial,sans-serif;font-size:11px;color:#9ca3af;text-align:center;line-height:1.6;">
<strong style="color:#6b7280;">{empresa}</strong>{footer_site}
</p>
</td></tr>

</table>
<!-- /CARD -->

</td></tr>
</table>
</body>
</html>'''


def _extrair_pitch(descricao, empresa_nome='', max_chars=150):
    """Extrai a frase de BENEFÍCIO da descrição, não a frase descritiva."""
    BENEFIT_WORDS = [
        'produtividade', 'economia', 'reduz', 'aumenta', 'controle',
        'proteg', 'seguran', 'resultado', 'otimiz', 'eficiên',
        'visibilidade', 'automatiz', 'agilidade', 'evita', 'elimin',
        'garante', 'melhora', 'simplifica', 'acelera', 'monitora',
        'objetivo', 'permite', 'ajuda', 'facilita',
    ]
    frases = re.split(r'(?<=[.!?])\s+', descricao.strip())
    if not frases:
        return descricao[:max_chars]

    for frase in reversed(frases):
        fl = frase.lower()
        if any(bw in fl for bw in BENEFIT_WORDS):
            pitch = frase.rstrip('.')
            pitch = re.sub(r'^O objetivo é\s+', '', pitch, flags=re.IGNORECASE)
            pitch = re.sub(r'^A meta é\s+', '', pitch, flags=re.IGNORECASE)
            pitch = re.sub(r'^O foco é\s+', '', pitch, flags=re.IGNORECASE)
            if empresa_nome:
                pitch = re.sub(
                    rf'^O\s+{re.escape(empresa_nome)}\s+(é|permite|ajuda|oferece)\s+',
                    '', pitch, flags=re.IGNORECASE)
                pitch = re.sub(
                    rf'^A\s+{re.escape(empresa_nome)}\s+(é|permite|ajuda|oferece)\s+',
                    '', pitch, flags=re.IGNORECASE)
            if pitch:
                pitch = pitch[0].upper() + pitch[1:]
            if len(pitch) > max_chars:
                pitch = pitch[:max_chars].rsplit(' ', 1)[0]
            return pitch

    pitch = frases[0].rstrip('.')
    if empresa_nome:
        pitch = re.sub(
            rf'^O\s+{re.escape(empresa_nome)}\s+é\s+(um[a]?\s+)?',
            '', pitch, flags=re.IGNORECASE)
        pitch = re.sub(
            rf'^A\s+{re.escape(empresa_nome)}\s+é\s+(um[a]?\s+)?',
            '', pitch, flags=re.IGNORECASE)
    if pitch:
        pitch = pitch[0].upper() + pitch[1:]
    if len(pitch) > max_chars:
        pitch = pitch[:max_chars].rsplit(' ', 1)[0]
    return pitch


def _extrair_cores_site(website):
    """Extrai cores primárias do CSS/HTML do site. Retorna (cor_header, cor_btn)."""
    if not website:
        return '#1a2332', '#2563eb'
    try:
        import requests as req
        url = website if website.startswith('http') else f'https://{website}'
        resp = req.get(url, timeout=8,
                       headers={'User-Agent': 'Mozilla/5.0'})
        text = resp.text[:20000]
        hex_colors = re.findall(r'#([0-9a-fA-F]{6})\b', text)
        neutrals = {
            '000000', 'ffffff', '333333', '666666', '999999', 'aaaaaa',
            'bbbbbb', 'cccccc', 'dddddd', 'eeeeee', 'f0f0f0', 'f5f5f5',
            'fafafa', 'f8f8f8', 'e5e5e5', 'f4f4f4', 'f9f9f9', 'fbfbfb',
            'f7f7f7', 'f1f1f1', 'e0e0e0', 'd0d0d0', 'c0c0c0', 'b0b0b0',
            'a0a0a0', '808080', '404040', '1a1a1a', '2d2d2d', '4a4a4a',
        }
        filtered = [c.lower() for c in hex_colors if c.lower() not in neutrals]
        if filtered:
            from collections import Counter
            top = Counter(filtered).most_common(2)
            cor_header = '#' + top[0][0]
            cor_btn = '#' + (top[1][0] if len(top) > 1 else top[0][0])
            return cor_header, cor_btn
    except Exception:
        pass
    return '#1a2332', '#2563eb'


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


def _get_email_track_token(schema, lead_id):
    """Gera ou retorna token de tracking de email para o lead."""
    conn = _conn(schema)
    c = conn.cursor()
    try:
        c.execute('SELECT email_track_token FROM empresas WHERE id=%s', (lead_id,))
        row = c.fetchone()
        if row and row.get('email_track_token'):
            conn.close()
            return row['email_track_token']
    except Exception:
        conn.rollback()
        try:
            c.execute("ALTER TABLE empresas ADD COLUMN IF NOT EXISTS email_track_token TEXT")
            conn.commit()
        except Exception:
            conn.rollback()
    token = secrets.token_urlsafe(16)
    try:
        c.execute('UPDATE empresas SET email_track_token=%s WHERE id=%s',
                  (token, lead_id))
        conn.commit()
    except Exception:
        conn.rollback()
    conn.close()
    return token


def _find_lead_by_email_token(token):
    """Busca lead e schema pelo token de tracking de email."""
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
                    'SELECT id FROM empresas WHERE email_track_token=%s',
                    (token,))
                row = c2.fetchone()
                conn2.close()
                if row:
                    return sch, row['id']
            except Exception:
                pass
    except Exception:
        pass
    return None, None


def _inject_tracking_pixel(html, track_url):
    """Injeta pixel de tracking antes do </body>."""
    pixel = (f'<img src="{track_url}" width="1" height="1" '
             f'style="display:block;width:1px;height:1px;border:0" alt="">')
    if '</body>' in html:
        return html.replace('</body>', pixel + '</body>')
    return html + pixel


# ── Email Tracking Endpoints (públicos, sem auth) ──

@app.route('/t/test')
def email_track_test():
    """Diagnóstico do tracking — acesse para verificar se está funcionando."""
    base = os.environ.get('BASE_URL', request.host_url.rstrip('/'))
    base_https = base.replace('http://', 'https://')
    return jsonify({
        'ok': True,
        'base_url_env': os.environ.get('BASE_URL', '(não definido)'),
        'request_host_url': request.host_url,
        'base_url_final': base_https,
        'pixel_example': f'{base_https}/t/TEST_TOKEN/open.png',
        'scheme': request.scheme,
        'x_forwarded_proto': request.headers.get('X-Forwarded-Proto', '(nenhum)'),
    })

@app.route('/t/<token>/open.png')
def email_track_open(token):
    """Pixel 1x1 — registra abertura de email."""
    schema, lead_id = _find_lead_by_email_token(token)
    if schema and lead_id:
        try:
            conn = _conn(schema)
            c = conn.cursor()
            c.execute("""UPDATE empresas
                SET email_aberto = COALESCE(email_aberto, NOW())
                WHERE id = %s""", (lead_id,))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f'[track/open] {e}', flush=True)
    import base64
    pixel = base64.b64decode(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVQI12NgAAIABQAB'
        'Nl7BcQAAAABJRU5ErkJggg==')
    resp = make_response(pixel)
    resp.headers['Content-Type'] = 'image/png'
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    return resp


@app.route('/t/<token>/click')
def email_track_click(token):
    """Redireciona para o link de agendamento, registra clique."""
    schema, lead_id = _find_lead_by_email_token(token)
    redirect_url = request.args.get('url', '/')
    if schema and lead_id:
        try:
            conn = _conn(schema)
            c = conn.cursor()
            c.execute("""UPDATE empresas
                SET email_clicado = COALESCE(email_clicado, NOW()),
                    email_aberto = COALESCE(email_aberto, NOW())
                WHERE id = %s""", (lead_id,))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f'[track/click] {e}', flush=True)
    return redirect(redirect_url)


@app.route('/webhook/email', methods=['POST'])
def webhook_email():
    """Webhook do Resend para eventos de email (bounce, complaint, etc)."""
    data = request.get_json(silent=True) or {}
    event_type = data.get('type', '')
    payload = data.get('data', {})
    to_email = ''
    if isinstance(payload.get('to'), list) and payload['to']:
        to_email = payload['to'][0]
    elif isinstance(payload.get('to'), str):
        to_email = payload['to']
    print(f'[WEBHOOK] {event_type} to={to_email}', flush=True)
    if event_type in ('email.bounced', 'email.complained'):
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
                    bounce_status = 'bounce' if 'bounce' in event_type else 'spam'
                    c2.execute(
                        "UPDATE empresas SET status = %s "
                        "WHERE email = %s AND status IN ('novo','contactada')",
                        (bounce_status, to_email))
                    if c2.rowcount > 0:
                        conn2.commit()
                        conn2.close()
                        break
                    conn2.close()
                except Exception:
                    pass
        except Exception as e:
            print(f'[WEBHOOK] erro: {e}', flush=True)
    return jsonify({'ok': True})


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
    'starter': {
        'nome': 'TurboVenda Starter',
        'valor': 97.00,
        'descricao': 'Até 500 leads + Busca IA + Email + Pipeline',
    },
    'pro': {
        'nome': 'TurboVenda Pro',
        'valor': 297.00,
        'descricao': 'Leads ilimitados + IA 24/7 + Email + WhatsApp + Sequências',
    },
}


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
    # Info de limite de leads
    limite = PLAN_LEAD_LIMITS.get(plano)
    total_leads = 0
    try:
        schema = _get_schema()
        if schema:
            conn2 = _conn(schema)
            c2 = conn2.cursor()
            c2.execute('SELECT COUNT(*) AS total FROM empresas')
            total_leads = c2.fetchone()['total']
            conn2.close()
    except Exception:
        pass
    return jsonify({
        'plano': plano,
        'ativo': ativo,
        'expira': str(expira) if expira else None,
        'limite_leads': limite,
        'total_leads': total_leads,
    })


# =============================================================================
# ADMIN PANEL
# =============================================================================

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_auth'):
            if request.path.startswith('/admin/api/'):
                return jsonify({'error': 'unauthorized'}), 401
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated


@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    error = None
    if request.method == 'POST':
        key = request.form.get('admin_key', '')
        admin_key = os.environ.get('ADMIN_KEY', 'trocar123')
        if key == admin_key:
            session['admin_auth'] = True
            return redirect(url_for('admin_dashboard'))
        error = 'Senha incorreta'
    if session.get('admin_auth'):
        return redirect(url_for('admin_dashboard'))
    return render_template('admin.html', error=error)


@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    return render_template('admin.html')


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_auth', None)
    return redirect(url_for('admin_login'))


@app.route('/admin/api/stats')
@admin_required
def admin_api_stats():
    try:
        conn = _conn()
        c = conn.cursor()
        c.execute('SELECT COUNT(*) AS total FROM users')
        total_users = c.fetchone()['total']
        c.execute('SELECT COUNT(*) AS total FROM users WHERE ativo = TRUE')
        active_users = c.fetchone()['total']
        c.execute('SELECT COUNT(*) AS total FROM pagamentos')
        total_payments = c.fetchone()['total']

        # Count leads and emails across all user schemas
        total_leads = 0
        total_emails = 0
        c.execute('SELECT id, schema_name FROM users WHERE schema_name IS NOT NULL')
        users = c.fetchall()
        for u in users:
            schema = u['schema_name']
            try:
                c.execute(
                    'SELECT COUNT(*) AS cnt FROM {}.empresas'.format(schema))
                total_leads += c.fetchone()['cnt']
            except Exception:
                conn.rollback()
            try:
                c.execute(
                    "SELECT COUNT(*) AS cnt FROM {}.empresas "
                    "WHERE email_enviado IS NOT NULL".format(schema))
                total_emails += c.fetchone()['cnt']
            except Exception:
                conn.rollback()
        conn.close()
        return jsonify({
            'total_users': total_users,
            'active_users': active_users,
            'total_leads': total_leads,
            'total_emails': total_emails,
            'total_payments': total_payments,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/admin/api/users')
@admin_required
def admin_api_users_list():
    try:
        conn = _conn()
        c = conn.cursor()
        c.execute(
            'SELECT id, email, empresa_nome, website, schema_name, '
            'plano, plano_expira, ativo, criado_em '
            'FROM users ORDER BY id')
        users = c.fetchall()
        result = []
        for u in users:
            row = dict(u)
            # Count leads for this user
            schema = row.get('schema_name')
            lead_count = 0
            if schema:
                try:
                    c.execute(
                        'SELECT COUNT(*) AS cnt FROM {}.empresas'.format(
                            schema))
                    lead_count = c.fetchone()['cnt']
                except Exception:
                    conn.rollback()
            row['lead_count'] = lead_count
            _serialize_row(row)
            result.append(row)
        conn.close()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/admin/api/users/<int:uid>/toggle', methods=['POST'])
@admin_required
def admin_api_toggle_user(uid):
    try:
        conn = _conn()
        c = conn.cursor()
        c.execute('UPDATE users SET ativo = NOT ativo WHERE id = %s '
                  'RETURNING ativo', (uid,))
        row = c.fetchone()
        if not row:
            conn.close()
            return jsonify({'error': 'Usuario nao encontrado'}), 404
        conn.commit()
        conn.close()
        return jsonify({'ok': True, 'ativo': row['ativo']})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/admin/api/users/<int:uid>/plano', methods=['POST'])
@admin_required
def admin_api_change_plan(uid):
    try:
        data = request.get_json(force=True)
        plano = data.get('plano', 'trial')
        if plano not in ('trial', 'starter', 'pro', 'enterprise'):
            return jsonify({'error': 'Plano invalido'}), 400
        conn = _conn()
        c = conn.cursor()
        c.execute('UPDATE users SET plano = %s WHERE id = %s '
                  'RETURNING id', (plano, uid))
        row = c.fetchone()
        if not row:
            conn.close()
            return jsonify({'error': 'Usuario nao encontrado'}), 404
        conn.commit()
        conn.close()
        return jsonify({'ok': True, 'plano': plano})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/admin/api/users/<int:uid>/impersonate', methods=['POST'])
@admin_required
def admin_api_impersonate(uid):
    try:
        conn = _conn()
        c = conn.cursor()
        c.execute('SELECT id, schema_name FROM users WHERE id = %s', (uid,))
        user = c.fetchone()
        conn.close()
        if not user:
            return jsonify({'error': 'Usuario nao encontrado'}), 404
        session['user_id'] = user['id']
        schema = user.get('schema_name') or f'emp_{user["id"]}'
        try:
            _init_user_schema(schema)
        except Exception:
            pass
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/admin/api/payments')
@admin_required
def admin_api_payments():
    try:
        conn = _conn()
        c = conn.cursor()
        c.execute(
            'SELECT p.id, p.user_id, p.mp_payment_id, p.status, '
            'p.valor, p.plano, p.criado_em, u.email '
            'FROM pagamentos p '
            'LEFT JOIN users u ON u.id = p.user_id '
            'ORDER BY p.criado_em DESC LIMIT 100')
        rows = c.fetchall()
        conn.close()
        result = []
        for r in rows:
            row = dict(r)
            _serialize_row(row)
            result.append(row)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == '__main__':
    _init_public_schema()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
