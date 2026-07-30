# -*- coding: utf-8 -*-
"""
TurboVenda — SaaS CRM multi-tenant
Prospecção IA + CRM + Email + WhatsApp + Agendamento
"""

import datetime as _dt
import hashlib
import hmac as _hmac
import json
import os
import random
import re
import secrets
import subprocess
import sys
from urllib.parse import quote as _urlquote, urlparse as _urlparse
import bcrypt
from cryptography.fernet import Fernet, InvalidToken
import psycopg2
import psycopg2.extras
import psycopg2.pool
from psycopg2 import sql as psql
from functools import lru_cache, wraps
import logging
from flask import (Flask, abort, jsonify, make_response, redirect,
                   render_template, request, send_file, session, url_for)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
try:
    import sentry_sdk
    _sentry_dsn = os.environ.get('SENTRY_DSN', '')
    if _sentry_dsn:
        sentry_sdk.init(dsn=_sentry_dsn, traces_sample_rate=0.1,
                        profiles_sample_rate=0.1)
except ImportError:
    pass

from pseo_data import (CNAE_B2B, CNAE_POR_CODIGO, CNAE_POR_SLUG,
                       PORTE_LABELS, UF_NOMES, cnae_formatado, slugify)

app = Flask(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
    datefmt='%Y-%m-%dT%H:%M:%S')
logger = logging.getLogger(__name__)

_secret = os.environ.get('SECRET_KEY', '')
if not _secret or _secret == 'mv-saas-2025-change-in-prod':
    if os.environ.get('RAILWAY_ENVIRONMENT') or os.environ.get('RENDER') or os.environ.get('FLY_APP_NAME'):
        logger.critical('SECRET_KEY nao definido em producao — defina a variavel de ambiente')
        sys.exit(1)
    _secret = secrets.token_hex(32)
    logger.warning('SECRET_KEY não definido — gerado temporário')
app.secret_key = _secret

_is_production = bool(os.environ.get('RAILWAY_ENVIRONMENT') or os.environ.get('RENDER') or os.environ.get('FLY_APP_NAME'))
app.config['TEMPLATES_AUTO_RELOAD'] = not _is_production
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 300 if _is_production else 0
app.config['PREFERRED_URL_SCHEME'] = 'https'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = _dt.timedelta(hours=8)

from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

limiter = Limiter(get_remote_address, app=app, default_limits=["200 per minute"],
                  storage_uri="memory://")

GA_MEASUREMENT_ID = os.environ.get('GA_MEASUREMENT_ID', 'G-NGSNSF3SPM')

# --- Encriptação de credenciais sensíveis no DB ---
_ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY', '')
_fernet = None
if _ENCRYPTION_KEY:
    try:
        _fernet = Fernet(_ENCRYPTION_KEY.encode() if len(_ENCRYPTION_KEY) == 44
                         else Fernet.generate_key())
        if len(_ENCRYPTION_KEY) != 44:
            logger.warning('ENCRYPTION_KEY invalida (deve ser 44 chars base64 Fernet)')
            _fernet = None
    except Exception:
        _fernet = None


def _encrypt_field(value: str) -> str:
    if not value or not _fernet:
        return value
    return 'ENC:' + _fernet.encrypt(value.encode()).decode()


def _decrypt_field(value: str) -> str:
    if not value or not _fernet or not value.startswith('ENC:'):
        return value or ''
    try:
        return _fernet.decrypt(value[4:].encode()).decode()
    except (InvalidToken, Exception):
        return value


_SENSITIVE_FIELDS = ('linkedin_password', 'smtp_password', 'resend_api_key', 'serper_api_key', 'brave_api_key', 'google_cse_key', 'oauth_refresh_token')


def _csrf_token():
    if '_csrf' not in session:
        session['_csrf'] = secrets.token_hex(16)
    return session['_csrf']


def _check_csrf():
    """Valida CSRF em forms HTML (POST sem JSON content-type)."""
    if request.method not in ('POST', 'PUT', 'DELETE'):
        return
    if request.content_type and 'json' in request.content_type:
        return
    if request.path.startswith('/webhook/'):
        return
    if request.path.startswith('/t/'):
        return
    token = request.form.get('_csrf') or request.headers.get('X-CSRF-Token', '')
    if not token or not _hmac.compare_digest(token, session.get('_csrf', '')):
        abort(403)


app.jinja_env.globals['csrf_token'] = _csrf_token


@app.before_request
def _csrf_protect():
    _check_csrf()


@app.after_request
def _set_security_headers(resp):
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['X-Frame-Options'] = 'SAMEORIGIN'
    resp.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    resp.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    resp.headers.pop('Server', None)
    if request.is_secure:
        resp.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return resp


@app.errorhandler(404)
def _not_found(e):
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Não encontrado'}), 404
    return render_template('404.html'), 404


@app.errorhandler(429)
def _rate_limit_handler(e):
    return jsonify({'error': 'Muitas tentativas. Aguarde um momento.'}), 429


@app.errorhandler(500)
def _internal_error(e):
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Erro interno'}), 500
    return render_template('500.html'), 500

DATABASE_URL = os.environ.get('DATABASE_URL', '')
if not DATABASE_URL:
    logger.critical('DATABASE_URL nao configurado — defina a variavel de ambiente')
    sys.exit(1)
if DATABASE_URL.startswith('psql://'):
    DATABASE_URL = 'postgresql://' + DATABASE_URL[7:]
elif DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = 'postgresql://' + DATABASE_URL[11:]

_db_pool = None
try:
    _db_pool = psycopg2.pool.ThreadedConnectionPool(
        minconn=2, maxconn=10, dsn=DATABASE_URL,
        cursor_factory=psycopg2.extras.RealDictCursor)
except Exception as _pool_err:
    logger.warning(f'Pool de conexões falhou, usando fallback: {_pool_err}')

# Processos em background: {schema: {'busca': Popen, 'linkedin': Popen}}
_procs: dict = {}

# Inicializa tabelas globais ao importar (gunicorn não chama __main__)
def _init_public_schema_safe():
    if not DATABASE_URL:
        return
    conn = None
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
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
            "utm_source TEXT",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
            "utm_medium TEXT",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
            "utm_campaign TEXT",
            """CREATE TABLE IF NOT EXISTS pagamentos (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(id),
                mp_payment_id TEXT,
                status TEXT,
                valor DECIMAL(10,2),
                plano TEXT,
                criado_em TIMESTAMP DEFAULT NOW()
            )""",
            # pSEO: dados cadastrais públicos (dados abertos CNPJ / Receita)
            """CREATE TABLE IF NOT EXISTS empresas_publicas (
                cnpj_basico    TEXT PRIMARY KEY,
                razao_social   TEXT,
                nome_fantasia  TEXT,
                municipio      TEXT,
                uf             TEXT,
                bairro         TEXT,
                cnae_principal TEXT,
                porte          TEXT,
                data_abertura  DATE,
                situacao       TEXT
            )""",
            "CREATE INDEX IF NOT EXISTS idx_emp_pub_cnae_uf_mun "
            "ON empresas_publicas (cnae_principal, uf, municipio)",
            "CREATE INDEX IF NOT EXISTS idx_emp_pub_uf_mun "
            "ON empresas_publicas (uf, municipio)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
            "trial_email_3d_sent BOOLEAN DEFAULT FALSE",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
            "trial_email_expired_sent BOOLEAN DEFAULT FALSE",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_pagamentos_mp_id "
            "ON pagamentos (mp_payment_id)",
        ]:
            try:
                c.execute(stmt)
            except Exception:
                conn.rollback()
        # Set users as pro
        c.execute("UPDATE users SET plano = 'pro' WHERE email IN ('suporte@pcmonitor.com.br', 'comercial1@pili.ind.br') AND plano != 'pro'")
        conn.commit()
    except Exception as e:
        logger.error(f'init_public_schema: {e}')
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

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


def _safe_sql_name(name: str) -> bool:
    """Valida que um nome SQL contem apenas alfanumerico e underscore."""
    return bool(name) and bool(re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', name))


class _PooledConn:
    """Wrapper que devolve a conexão ao pool quando .close() é chamado."""
    __slots__ = ('_conn', '_pool')

    def __init__(self, conn, pool):
        self._conn = conn
        self._pool = pool

    def close(self):
        if self._conn is not None:
            try:
                self._conn.reset()
                self._pool.putconn(self._conn)
            except Exception:
                try:
                    self._pool.putconn(self._conn, close=True)
                except Exception:
                    pass
            self._conn = None

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _conn(schema=None):
    if _db_pool:
        raw = _db_pool.getconn()
        conn = _PooledConn(raw, _db_pool)
    else:
        conn = psycopg2.connect(DATABASE_URL,
                                cursor_factory=psycopg2.extras.RealDictCursor)
    if schema:
        if not _safe_sql_name(schema):
            conn.close()
            raise ValueError(f'Schema invalido: {schema}')
        with conn.cursor() as c:
            c.execute(psql.SQL('SET search_path TO {}, public').format(
                psql.Identifier(schema)))
        conn.commit()
    return conn


def _init_public_schema():
    _init_public_schema_safe()


def _init_user_schema(schema: str):
    if not re.match(r'^emp_\d+$', schema):
        raise ValueError(f'Schema inválido: {schema}')
    conn = _conn()
    try:
        c = conn.cursor()
        c.execute(psql.SQL('CREATE SCHEMA IF NOT EXISTS {}').format(psql.Identifier(schema)))
        c.execute('SET search_path TO %s, public', (schema,))
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
            estados_atuacao JSONB DEFAULT '[]',
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
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS smtp_verificado BOOLEAN DEFAULT FALSE",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS segmentos_evitar JSONB DEFAULT '[]'",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS email_metodo TEXT DEFAULT 'global'",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS oauth_provider TEXT",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS oauth_refresh_token TEXT",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS oauth_email TEXT",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS dominio_proprio TEXT",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS dominio_id TEXT",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS dominio_verificado BOOLEAN DEFAULT FALSE",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS serper_api_key TEXT",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS brave_api_key TEXT",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS google_cse_key TEXT",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS google_cse_cx TEXT",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS horario_inicio INTEGER DEFAULT 9",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS horario_fim INTEGER DEFAULT 18",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS duracao_reuniao INTEGER DEFAULT 30",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS dias_semana TEXT DEFAULT '1,2,3,4,5'",
            "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS email_aberto TIMESTAMP",
            "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS email_clicado TIMESTAMP",
            "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS email_track_token TEXT",
            "ALTER TABLE contatos ADD COLUMN IF NOT EXISTS instagram TEXT",
            "ALTER TABLE contatos ADD COLUMN IF NOT EXISTS fonte TEXT",
        ]:
            try:
                c.execute(stmt)
            except Exception:
                conn.rollback()
        for idx in [
            "CREATE INDEX IF NOT EXISTS idx_empresas_email_track ON empresas (email_track_token) WHERE email_track_token IS NOT NULL",
            "CREATE INDEX IF NOT EXISTS idx_empresas_agenda_token ON empresas (agenda_token) WHERE agenda_token IS NOT NULL",
            "CREATE INDEX IF NOT EXISTS idx_empresas_status ON empresas (status)",
            "CREATE INDEX IF NOT EXISTS idx_contatos_empresa_decisor ON contatos (empresa_id, decisor)",
            "CREATE INDEX IF NOT EXISTS idx_sequencia_leads_proximo ON sequencia_leads (proximo_envio) WHERE status = 'ativo'",
        ]:
            try:
                c.execute(idx)
            except Exception:
                conn.rollback()
        conn.commit()
    finally:
        conn.close()


# =============================================================================
# AUTH HELPERS
# =============================================================================

def _hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def _verify_pw(pw: str, stored_hash: str) -> bool:
    """Verifica senha — suporta bcrypt e legacy SHA-256 (migra automaticamente)."""
    if stored_hash.startswith('$2'):
        return bcrypt.checkpw(pw.encode(), stored_hash.encode())
    return hashlib.sha256(pw.encode()).hexdigest() == stored_hash


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
    conn = None
    try:
        conn = _conn()
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE id = %s AND ativo = TRUE', (uid,))
        row = c.fetchone()
        return dict(row) if row else None
    except Exception:
        return None
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


PLAN_LEAD_LIMITS = {
    'trial': 50,
    'starter': 500,
    'pro': None,       # ilimitado
    'enterprise': None  # ilimitado
}

TRIAL_DAYS = 14

PLAN_FEATURES = {
    'trial':      {'email_massa': False, 'sequencias': False, 'api_tokens': False},
    'starter':    {'email_massa': True,  'sequencias': False, 'api_tokens': False},
    'pro':        {'email_massa': True,  'sequencias': True,  'api_tokens': True},
    'enterprise': {'email_massa': True,  'sequencias': True,  'api_tokens': True},
}


def _get_user_plano(uid=None):
    uid = uid or session.get('user_id')
    if not uid:
        return 'trial'
    conn = None
    try:
        conn = _conn()
        c = conn.cursor()
        c.execute('SELECT plano FROM users WHERE id = %s', (uid,))
        row = c.fetchone()
        return (row['plano'] if row else 'trial') or 'trial'
    except Exception:
        return 'trial'
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def _check_feature(feature, uid=None):
    plano = _get_user_plano(uid)
    allowed = PLAN_FEATURES.get(plano, PLAN_FEATURES['trial'])
    if not allowed.get(feature, False):
        nomes = {'email_massa': 'Email em massa', 'sequencias': 'Sequências automáticas', 'api_tokens': 'API REST'}
        return False, f'{nomes.get(feature, feature)} não disponível no plano {plano}. Faça upgrade para desbloquear.'
    return True, ''


def _check_lead_limit(schema, uid=None):
    """Retorna (ok, msg). ok=True se pode inserir, False se atingiu limite."""
    uid = uid or session.get('user_id')
    if not uid:
        return True, ''
    # Admin logado = sem limite
    if session.get('admin_auth'):
        return True, ''
    conn = None
    try:
        conn = _conn()
        c = conn.cursor()
        c.execute('SELECT plano, plano_expira FROM users WHERE id = %s', (uid,))
        row = c.fetchone()
        plano = (row['plano'] if row else 'trial') or 'trial'
    except Exception:
        plano = 'trial'
        row = None
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
    if row and row.get('plano_expira'):
        from datetime import datetime
        expira = row['plano_expira']
        if isinstance(expira, str):
            expira = datetime.fromisoformat(expira)
        if expira < datetime.now():
            if plano == 'trial':
                return False, f'Seu trial de {TRIAL_DAYS} dias expirou. Faça upgrade para continuar prospectando.'
            else:
                return False, f'Seu plano {plano} expirou. Renove para continuar prospectando.'
    limite = PLAN_LEAD_LIMITS.get(plano)
    if limite is None:
        return True, ''
    conn2 = None
    try:
        conn2 = _conn(schema)
        c2 = conn2.cursor()
        c2.execute('SELECT COUNT(*) AS total FROM empresas')
        total = c2.fetchone()['total']
    except Exception:
        return True, ''
    finally:
        if conn2:
            try:
                conn2.close()
            except Exception:
                pass
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
        conn = None
        try:
            conn = _conn()
            c = conn.cursor()
            c.execute("""SELECT t.*, u.schema_name FROM api_tokens t
                         JOIN users u ON t.user_id = u.id
                         WHERE t.token = %s AND t.ativo = TRUE AND u.ativo = TRUE""",
                      (token,))
            row = c.fetchone()
            if not row:
                return jsonify({'error': 'token inválido'}), 401
            request.token_user = dict(row)
        except Exception as e:
            logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
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
    conn = None
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
            logger.error(f'stats/{schema} linkedin_total: {e}')
    except Exception as e:
        logger.error(f'stats/{schema}: {e}')
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
    return z


def _fmt_tel(raw) -> str:
    """Padroniza telefone para (DD) XXXXX-XXXX. Não-BR/inválido mantém
    o original. Mesma lógica do formatTel() do frontend."""
    if not raw:
        return ''
    d = ''.join(ch for ch in str(raw) if ch.isdigit())
    if len(d) > 11 and d.startswith('55'):
        d = d[2:]
    if len(d) >= 2 and d[:2].isdigit() and int(d[:2]) >= 11:
        if len(d) == 11:
            return f'({d[:2]}) {d[2:7]}-{d[7:]}'
        if len(d) == 10:
            return f'({d[:2]}) {d[2:6]}-{d[6:]}'
    return str(raw)


def get_leads(schema: str, limite: int = 50, page: int = 1, per_page: int = 50) -> list:
    if not DATABASE_URL or not schema:
        return []
    per_page = max(1, min(per_page, 200))
    page = max(1, page)
    offset = (page - 1) * per_page
    conn = None
    try:
        conn = _conn(schema)
        c = conn.cursor()
        _sub = """(SELECT ct.nome || ' - ' || ct.cargo
                   FROM contatos ct WHERE ct.empresa_id = e.id AND ct.decisor = 1
                   LIMIT 1) AS _decisor,
                  (SELECT ct.linkedin FROM contatos ct
                   WHERE ct.empresa_id = e.id AND ct.decisor = 1
                   LIMIT 1) AS _decisor_linkedin,
                  (SELECT ct.instagram FROM contatos ct
                   WHERE ct.empresa_id = e.id AND ct.decisor = 1
                   LIMIT 1) AS _decisor_instagram"""
        _base = """e.id, e.nome_fantasia, e.whatsapp, e.telefone, e.email, e.score,
                   e.status, e.segmento, e.demo_status, e.cidade, e.estado,
                   e.encontrado_em, e.cnpj, e.razao_social, e.website,
                   e.linkedin, e.instagram, e.fonte, e.porte,
                   e.situacao_cadastral, e.enriquecido,
                   e.email_enviado, e.wa_enviado, e.observacoes"""
        def _exec():
            try:
                c.execute(
                    f"SELECT {_base}, e.email_aberto, e.email_clicado, {_sub}"
                    " FROM empresas e ORDER BY e.encontrado_em DESC"
                    " LIMIT %s OFFSET %s",
                    (per_page, offset))
            except Exception:
                conn.rollback()
                c.execute(
                    f"SELECT {_base}, NULL as email_aberto,"
                    f" NULL as email_clicado, {_sub}"
                    " FROM empresas e ORDER BY e.encontrado_em DESC"
                    " LIMIT %s OFFSET %s",
                    (per_page, offset))
        try:
            _exec()
        except Exception:
            # Auto-reparo: schema de tenant antigo sem as colunas novas.
            conn.rollback()
            for stmt in (
                "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS "
                "situacao_cadastral TEXT",
                "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS "
                "enriquecido BOOLEAN DEFAULT FALSE",
                "ALTER TABLE contatos ADD COLUMN IF NOT EXISTS instagram TEXT",
                "ALTER TABLE contatos ADD COLUMN IF NOT EXISTS fonte TEXT",
            ):
                try:
                    c.execute(stmt)
                    conn.commit()
                except Exception:
                    conn.rollback()
            _exec()
        rows = [_serialize_row(dict(r)) for r in c.fetchall()]
        return rows
    except Exception:
        # lista vazia e falha de schema ficam iguais pro frontend — por isso
        # o traceback completo vai pro log, senao o bug fica invisivel
        logger.exception('get_leads falhou (schema=%s)', schema)
        return []
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def get_logs(schema: str, limite: int = 60) -> list:
    if not DATABASE_URL or not schema:
        return []
    conn = None
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute("SELECT tipo, mensagem, timestamp FROM logs ORDER BY timestamp DESC LIMIT %s", (limite,))
        rows = [_serialize_row(dict(r)) for r in c.fetchall()]
        return rows
    except Exception as e:
        logger.error(f'logs/{schema}: {e}')
        return []
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def get_bot_config(schema: str) -> dict:
    if not schema:
        return {}
    conn = None
    try:
        conn = _conn(schema)
        c = conn.cursor()
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
            estados_atuacao JSONB DEFAULT '[]',
            horario_inicio INTEGER DEFAULT 9,
            horario_fim INTEGER DEFAULT 18,
            duracao_reuniao INTEGER DEFAULT 30,
            dias_semana TEXT DEFAULT '1,2,3,4,5',
            atualizado_em TIMESTAMP DEFAULT NOW()
        )""")
        conn.commit()
        c.execute('SELECT * FROM bot_config ORDER BY id DESC LIMIT 1')
        row = c.fetchone()
        conn.close()
        if not row:
            return {}
        result = _serialize_row(dict(row))
        for field in _SENSITIVE_FIELDS:
            if field in result and result[field]:
                result[field] = _decrypt_field(result[field])
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f'bot_config/{schema}: {e}')
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        return {}


def _get_schema():
    user = get_current_user()
    if not user:
        abort(403)
    schema = user.get('schema_name')
    if not schema:
        schema = f'emp_{user["id"]}'
        conn = None
        try:
            conn = _conn()
            c = conn.cursor()
            c.execute('UPDATE users SET schema_name=%s WHERE id=%s',
                      (schema, user['id']))
            conn.commit()
        except Exception:
            logger.exception("Erro ao atualizar schema_name em _get_schema")
        finally:
            if conn:
                try:
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
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if session.get('user_id'):
        return redirect(url_for('dashboard'))
    error = None
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        pw = request.form.get('senha', '')
        conn = None
        try:
            conn = _conn()
            c = conn.cursor()
            c.execute('SELECT * FROM users WHERE email = %s AND ativo = TRUE', (email,))
            user = c.fetchone()
            conn.close()
            conn = None
            if user and _verify_pw(pw, user['password_hash']):
                session['user_id'] = user['id']
                session.permanent = True
                # Migra hash SHA-256 legado para bcrypt
                if not user['password_hash'].startswith('$2'):
                    conn_up = None
                    try:
                        conn_up = _conn()
                        cu = conn_up.cursor()
                        cu.execute('UPDATE users SET password_hash=%s WHERE id=%s',
                                   (_hash_pw(pw), user['id']))
                        conn_up.commit()
                    except Exception:
                        logger.exception("Erro ao migrar hash bcrypt no login")
                    finally:
                        if conn_up:
                            try:
                                conn_up.close()
                            except Exception:
                                pass
                schema = user.get('schema_name') or f'emp_{user["id"]}'
                if not user.get('schema_name'):
                    c2 = None
                    try:
                        c2 = _conn()
                        cc = c2.cursor()
                        cc.execute('UPDATE users SET schema_name=%s WHERE id=%s',
                                   (schema, user['id']))
                        c2.commit()
                    except Exception:
                        logger.exception("Erro ao atualizar schema_name no login")
                    finally:
                        if c2:
                            try:
                                c2.close()
                            except Exception:
                                pass
                try:
                    _init_user_schema(schema)
                except Exception:
                    logger.exception("Erro ao inicializar schema no login")
                return redirect(url_for('dashboard'))
            error = 'Email ou senha incorretos'
        except Exception as e:
            logger.exception("Erro no login")
            error = 'Erro interno. Tente novamente.'
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
    return render_template('login.html', error=error)


@app.route('/cadastro', methods=['GET', 'POST'])
@limiter.limit("5 per minute", methods=["POST"])
def cadastro():
    if session.get('user_id'):
        return redirect(url_for('dashboard'))
    error = None
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        pw = request.form.get('senha', '')
        empresa = request.form.get('empresa_nome', '').strip()
        website = request.form.get('website', '').strip()
        segmento = request.form.get('segmento', '').strip()
        regiao = request.form.get('regiao', '').strip()
        utm_source = request.form.get('utm_source', '').strip() or None
        utm_medium = request.form.get('utm_medium', '').strip() or None
        utm_campaign = request.form.get('utm_campaign', '').strip() or None
        if not email or not pw or not empresa:
            error = 'Preencha todos os campos obrigatórios'
        elif len(pw) < 6:
            error = 'Senha mínimo 6 caracteres'
        else:
            conn = None
            conn2 = None
            try:
                conn = _conn()
                c = conn.cursor()
                c.execute('SELECT id FROM users WHERE email = %s', (email,))
                if c.fetchone():
                    error = 'Email já cadastrado'
                else:
                    c.execute("""INSERT INTO users (email, password_hash, empresa_nome, website, plano_expira,
                                 utm_source, utm_medium, utm_campaign)
                                 VALUES (%s,%s,%s,%s, NOW() + INTERVAL '%s days', %s,%s,%s) RETURNING id""",
                              (email, _hash_pw(pw), empresa, website or None, TRIAL_DAYS,
                               utm_source, utm_medium, utm_campaign))
                    uid = c.fetchone()['id']
                    schema = f'emp_{uid}'
                    c.execute('UPDATE users SET schema_name=%s WHERE id=%s', (schema, uid))
                    conn.commit()
                    conn.close()
                    conn = None
                    _init_user_schema(schema)
                    conn2 = _conn(schema)
                    c2 = conn2.cursor()
                    _REGIAO_UFS = {
                        'sul': ['PR', 'SC', 'RS'],
                        'sudeste': ['SP', 'RJ', 'MG', 'ES'],
                        'centro-oeste': ['GO', 'MT', 'MS', 'DF'],
                        'nordeste': ['BA', 'PE', 'CE', 'MA', 'RN', 'PB', 'AL', 'SE', 'PI'],
                        'norte': ['AM', 'PA', 'TO', 'RO', 'AC', 'RR', 'AP'],
                    }
                    estados_atuacao = []
                    if regiao == 'brasil_todo':
                        for ufs in _REGIAO_UFS.values():
                            estados_atuacao.extend(ufs)
                    elif regiao in _REGIAO_UFS:
                        estados_atuacao = _REGIAO_UFS[regiao]
                    c2.execute("""INSERT INTO bot_config (empresa_nome, website, descricao, termos_busca, estados_atuacao)
                                  VALUES (%s,%s,%s,%s,%s)""",
                               (empresa, website or None,
                                segmento or None,
                                '[]',
                                psycopg2.extras.Json(estados_atuacao)))
                    conn2.commit()
                    session['user_id'] = uid
                    session['just_registered'] = True
                    return redirect(url_for('config_page'))
            except Exception as e:
                logger.error(f'cadastro: {e}')
                error = 'Erro interno. Tente novamente.'
            finally:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass
                if conn2:
                    try:
                        conn2.close()
                    except Exception:
                        pass
    return render_template('register.html', error=error, ga_id=GA_MEASUREMENT_ID)


@app.route('/admin/users')
def admin_users():
    if not session.get('admin_auth'):
        return jsonify({'error': 'unauthorized'}), 401
    admin_key = os.environ.get('ADMIN_KEY', '')
    if not admin_key:
        return jsonify({'error': 'unauthorized'}), 401
    conn = None
    try:
        conn = _conn()
        c = conn.cursor()
        c.execute('SELECT id, email, empresa_nome, plano, ativo, criado_em FROM users ORDER BY id')
        users = c.fetchall()
        for u in users:
            if u.get('criado_em'):
                u['criado_em'] = str(u['criado_em'])
        return jsonify(users)
    except Exception as e:
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


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
<p>A <a href="/blog/prospecao-outbound-guia">prospecção outbound</a> evoluiu. Em vez de ligar para listas frias, ferramentas de IA como o <strong>TurboVenda</strong> identificam empresas que se encaixam no seu perfil ideal de cliente (ICP) automaticamente, coletando dados como telefone, e-mail, CNPJ e porte da empresa.</p>

<h3>2. E-mail Marketing B2B Personalizado</h3>
<p>E-mails genéricos têm taxa de abertura de 5%. E-mails personalizados com o nome da empresa, setor e dor específica chegam a <strong>35% de abertura</strong>. A chave é usar dados do lead para criar mensagens relevantes. Veja <a href="/blog/email-marketing-b2b-templates">5 templates de e-mail B2B prontos</a>.</p>

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
<p>A prospecção B2B em 2026 exige um mix de tecnologia e toque humano. Automatize a pesquisa e a abordagem inicial, mas mantenha a personalização nas interações. Ferramentas como o TurboVenda permitem que mesmo equipes pequenas prospectem como grandes empresas. Saiba também <a href="/blog/como-encontrar-clientes-pela-internet">6 formas de encontrar clientes pela internet</a> e como montar um <a href="/blog/pipeline-de-vendas-como-montar">pipeline de vendas eficiente</a>.</p>
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
<p>Leads se movem automaticamente pelo <a href="/blog/pipeline-de-vendas-como-montar">funil de vendas</a> conforme interagem: abriu e-mail → "Interessado", respondeu → "Em negociação", agendou reunião → "Qualificado".</p>

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
<p>A maioria dos CRMs para PME só organiza leads que você já tem. O TurboVenda vai além: ele <strong>encontra novos leads automaticamente</strong> e já coloca no seu <a href="/blog/pipeline-de-vendas-como-montar">pipeline</a> pronto para abordar. É CRM e prospecção numa única ferramenta, a partir de R$0/mês. Entenda melhor <a href="/blog/o-que-e-crm-para-que-serve">o que é CRM e para que serve</a>.</p>
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
<p>O TurboVenda automatiza as estratégias 1, 2, 5 e 6 em uma única plataforma. Configure seu ICP, ative o robô e receba leads qualificados no seu <a href="/blog/pipeline-de-vendas-como-montar">pipeline</a> todos os dias. Veja também <a href="/blog/como-encontrar-clientes-pela-internet">6 formas de encontrar clientes pela internet</a>.</p>
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
<p>No TurboVenda, a IA gera mensagens personalizadas para cada lead usando os dados da empresa. Você configura a sequência uma vez e o sistema envia automaticamente, com intervalos programados e follow-ups inteligentes. Saiba como usar <a href="/blog/whatsapp-para-vendas-b2b">WhatsApp para vendas B2B</a> como canal complementar.</p>
"""
    },
    {
        'slug': 'prospecao-outbound-guia',
        'titulo': 'Prospecção Outbound: Guia Completo para Vendas B2B',
        'desc': 'Aprenda o que é prospecção outbound, como montar um processo do zero e quais ferramentas usar para vender mais no B2B.',
        'keywords': 'prospecção outbound, outbound marketing, vendas B2B, prospecção ativa, cold outreach',
        'data': '2026-06-10',
        'tempo': '10 min',
        'conteudo': """
<p>Prospecção outbound é quando <strong>você vai atrás do cliente</strong>, em vez de esperar ele chegar. No B2B, onde o ticket médio é alto e o ciclo de venda é longo, outbound bem feito é a forma mais rápida de gerar pipeline.</p>

<h2>Outbound vs Inbound: qual escolher?</h2>
<p>Inbound (blog, SEO, conteúdo) traz leads no médio/longo prazo. Outbound traz leads <strong>agora</strong>. O ideal é combinar os dois, mas se você precisa de resultado rápido, comece pelo outbound.</p>
<ul>
<li><strong>Inbound</strong>: volume maior, custo menor por lead, ciclo mais longo</li>
<li><strong>Outbound</strong>: volume menor, custo maior, mas leads mais qualificados e ciclo mais curto</li>
</ul>

<h2>5 etapas de um processo outbound eficiente</h2>

<h3>1. Defina seu ICP (Perfil de Cliente Ideal)</h3>
<p>Antes de prospectar, saiba exatamente quem você busca: segmento, porte, região, cargo do decisor. Quanto mais específico, melhor a taxa de conversão.</p>

<h3>2. Monte sua lista de empresas</h3>
<p>Use fontes como Google, LinkedIn, associações comerciais e <a href="/blog/como-gerar-leads-qualificados">ferramentas de geração de leads</a>. O TurboVenda automatiza essa etapa usando IA para varrer a internet e encontrar empresas que compram o que você vende.</p>

<h3>3. Enriqueça os dados</h3>
<p>Nome da empresa não basta. Você precisa de: telefone, e-mail, CNPJ, nome do decisor, cargo. Ferramentas de enriquecimento cruzam dados da Receita Federal e sites corporativos.</p>

<h3>4. Crie sequências de contato</h3>
<p>Um único e-mail ou ligação raramente converte. Monte uma sequência multi-canal: e-mail → ligação → WhatsApp → follow-up. Veja <a href="/blog/email-marketing-b2b-templates">templates de e-mail B2B prontos</a>.</p>

<h3>5. Meça e otimize</h3>
<p>Acompanhe: taxa de resposta, taxa de agendamento, conversão por canal. Um <a href="/blog/crm-para-pequenas-empresas">CRM organizado</a> é essencial para não perder o controle.</p>

<h2>Ferramentas para prospecção outbound</h2>
<p>O TurboVenda combina as etapas 2, 3 e 4 numa única plataforma: a IA busca empresas, extrai contatos completos e alimenta seu pipeline. Você foca no que importa: <strong>fechar negócio</strong>.</p>
"""
    },
    {
        'slug': 'como-encontrar-clientes-pela-internet',
        'titulo': 'Como Encontrar Clientes pela Internet: 6 Formas Práticas',
        'desc': 'Descubra 6 formas práticas de encontrar novos clientes pela internet para sua empresa B2B. Do Google ao LinkedIn, com ferramentas gratuitas.',
        'keywords': 'como encontrar clientes, encontrar clientes pela internet, captar clientes online, achar clientes B2B',
        'data': '2026-06-15',
        'tempo': '8 min',
        'conteudo': """
<p>Encontrar clientes pela internet não é sorte — é método. Existem dezenas de fontes públicas com dados de empresas que você pode usar para montar uma lista de prospecção. Veja as 6 formas mais eficientes.</p>

<h2>1. Busca avançada no Google</h2>
<p>Use operadores de busca para filtrar resultados: <code>"distribuidora" + "contato" + "SP"</code> retorna páginas de contato de distribuidoras em São Paulo. Combine com <code>site:linkedin.com</code> para encontrar decisores.</p>

<h2>2. LinkedIn (gratuito)</h2>
<p>O LinkedIn é a maior base de profissionais do mundo. Use o filtro de busca por cargo, empresa, setor e região. Conecte com decisores e envie mensagens personalizadas.</p>

<h2>3. Google Maps</h2>
<p>Para negócios locais, o Google Maps é uma mina de ouro. Busque "fábrica de [produto] em [cidade]" e você terá nome, telefone, site e avaliações.</p>

<h2>4. Receita Federal (CNPJ)</h2>
<p>Sites como a consulta pública da Receita Federal permitem buscar empresas por CNAE (atividade econômica), estado e situação cadastral. Ideal para listas segmentadas.</p>

<h2>5. Associações e diretórios setoriais</h2>
<p>Cada setor tem associações com listas de membros. ABRAS (supermercados), ABIOVE (óleos vegetais), ABRASCE (shopping centers) — todas publicam diretórios com contatos.</p>

<h2>6. Ferramentas de prospecção automática</h2>
<p>Fazer tudo manual funciona, mas escala mal. O <a href="/blog/prospecao-outbound-guia">processo outbound completo</a> exige volume. Ferramentas como o TurboVenda automatizam a busca, extração de contatos e alimentação do CRM. Você descreve seu cliente ideal e a IA faz o resto.</p>

<h2>Como escolher a melhor forma?</h2>
<p>Depende do seu ICP e volume. Se você precisa de 10 clientes por mês, busca manual no Google e LinkedIn funciona. Se precisa de 100+, <a href="/blog/automacao-comercial-guia-completo">automação comercial</a> é o caminho.</p>
"""
    },
    {
        'slug': 'pipeline-de-vendas-como-montar',
        'titulo': 'Pipeline de Vendas: Como Montar e Gerenciar seu Funil B2B',
        'desc': 'Aprenda a montar um pipeline de vendas B2B eficiente com etapas claras, métricas certas e ferramentas para não perder nenhuma oportunidade.',
        'keywords': 'pipeline de vendas, funil de vendas B2B, etapas do funil, gestão de pipeline, funil comercial',
        'data': '2026-06-18',
        'tempo': '9 min',
        'conteudo': """
<p>Pipeline de vendas é a representação visual de onde cada oportunidade está no seu processo comercial. Sem pipeline, você não sabe quantos negócios estão em andamento, quais estão parados e onde está perdendo dinheiro.</p>

<h2>Por que pipeline importa?</h2>
<ul>
<li><strong>Previsibilidade</strong>: saber quanto vai faturar no mês que vem</li>
<li><strong>Priorização</strong>: focar nas oportunidades com maior chance de fechar</li>
<li><strong>Diagnóstico</strong>: identificar onde os leads travam e por quê</li>
</ul>

<h2>6 etapas de um pipeline B2B</h2>

<h3>1. Novo (lead bruto)</h3>
<p>Lead acabou de entrar — por prospecção, inbound ou indicação. Ainda não foi contactado.</p>

<h3>2. Contactado</h3>
<p>Você fez o primeiro contato (e-mail, ligação, WhatsApp). Aguardando resposta.</p>

<h3>3. Respondeu</h3>
<p>O lead respondeu. Pode ser positivo ("me conte mais") ou neutro ("agora não"). Registre a resposta.</p>

<h3>4. Qualificado</h3>
<p>O lead tem fit (perfil certo), necessidade e orçamento. Vale investir tempo.</p>

<h3>5. Demo/Proposta</h3>
<p>Apresentou a solução ou enviou proposta comercial. Fase de negociação.</p>

<h3>6. Convertido (ganho) ou Perdido</h3>
<p>Registre o motivo em ambos os casos. Leads perdidos são fonte de aprendizado.</p>

<h2>Métricas do pipeline</h2>
<ul>
<li><strong>Taxa de conversão por etapa</strong>: onde os leads travam?</li>
<li><strong>Tempo médio em cada etapa</strong>: negócios parados há muito tempo morrem</li>
<li><strong>Valor total do pipeline</strong>: quanto potencial tem na mesa</li>
<li><strong>Velocidade do pipeline</strong>: quantos dias do primeiro contato ao fechamento</li>
</ul>

<h2>Ferramenta certa para seu pipeline</h2>
<p>Planilha funciona até 20 leads. Acima disso, um <a href="/blog/crm-para-pequenas-empresas">CRM com Kanban</a> é essencial. O TurboVenda oferece pipeline visual com drag-and-drop, timeline de atividades por lead e <a href="/blog/como-gerar-leads-qualificados">geração automática de leads</a> para manter o topo do funil cheio.</p>
"""
    },
    {
        'slug': 'whatsapp-para-vendas-b2b',
        'titulo': 'WhatsApp para Vendas B2B: Como Usar sem Parecer Spam',
        'desc': 'Aprenda a usar o WhatsApp Business para vendas B2B de forma profissional. Dicas, templates e erros para evitar na abordagem comercial.',
        'keywords': 'WhatsApp vendas B2B, WhatsApp Business vendas, mensagem comercial WhatsApp, abordagem WhatsApp',
        'data': '2026-06-20',
        'tempo': '7 min',
        'conteudo': """
<p>O WhatsApp é o canal de comunicação mais usado no Brasil — 99% dos smartphones têm o app. No B2B, ele pode ser uma arma poderosa de vendas <strong>se usado corretamente</strong>. Mal usado, é spam e queima sua marca.</p>

<h2>WhatsApp pessoal vs Business vs API</h2>
<ul>
<li><strong>Pessoal</strong>: serve para conversas individuais, mas não escala</li>
<li><strong>Business</strong>: perfil comercial, catálogo, respostas rápidas, etiquetas — gratuito</li>
<li><strong>API</strong>: automação em escala, integração com CRM, mensagens em massa programadas</li>
</ul>

<h2>5 regras para não parecer spam</h2>

<h3>1. Personalize SEMPRE</h3>
<p>Nunca envie a mesma mensagem para todos. Use o nome da empresa, do decisor e mencione algo específico: "Vi que a {Empresa} atua com {segmento} em {cidade}..."</p>

<h3>2. Primeira mensagem = valor, não venda</h3>
<p>Não comece vendendo. Ofereça algo útil: um dado do setor, uma comparação, um case relevante. A venda vem depois.</p>

<h3>3. Horário comercial</h3>
<p>Respeite o horário. Mensagens às 22h de sábado queimam sua marca. Segunda a sexta, 9h-18h.</p>

<h3>4. Dê saída fácil</h3>
<p>"Se não fizer sentido, sem problemas." Essa frase reduz a resistência e aumenta respostas.</p>

<h3>5. Sequência curta</h3>
<p>Máximo 3 mensagens. Se não respondeu em 3 tentativas, pare. Insistir é spam.</p>

<h2>Template de primeira mensagem</h2>
<p><em>Olá {Nome}, tudo bem? Sou {SeuNome} da {SuaEmpresa}. Vi que a {Empresa} atua com {segmento} — temos ajudado empresas do setor a {benefício}. Posso te mostrar em 5 min como funciona?</em></p>

<h2>Automatizando WhatsApp B2B</h2>
<p>O TurboVenda integra WhatsApp Business para envio em massa com personalização por lead. Cada mensagem usa os dados extraídos automaticamente (nome, empresa, cargo) para parecer uma conversa 1:1, não um disparo genérico. Combine com <a href="/blog/email-marketing-b2b-templates">e-mail marketing B2B</a> para uma <a href="/blog/prospecao-outbound-guia">estratégia outbound multi-canal</a>.</p>
"""
    },
    {
        'slug': 'o-que-e-crm-para-que-serve',
        'titulo': 'O que é CRM e Para que Serve? Guia Simples para PMEs',
        'desc': 'Entenda o que é CRM, para que serve e por que sua empresa precisa de um. Guia simples e direto para pequenas e médias empresas.',
        'keywords': 'o que é CRM, CRM para que serve, CRM significado, sistema CRM, CRM para empresas',
        'data': '2026-06-22',
        'tempo': '6 min',
        'conteudo': """
<p>CRM significa <strong>Customer Relationship Management</strong> — Gestão de Relacionamento com o Cliente. Na prática, é um sistema que organiza todas as informações dos seus clientes e oportunidades de venda num lugar só.</p>

<h2>O que um CRM faz?</h2>
<ul>
<li><strong>Centraliza contatos</strong>: nome, telefone, e-mail, empresa, cargo — tudo num lugar</li>
<li><strong>Organiza o funil</strong>: saber em que etapa cada negociação está</li>
<li><strong>Registra interações</strong>: ligações, e-mails, reuniões, notas</li>
<li><strong>Lembra de follow-ups</strong>: tarefas e lembretes para não esquecer nenhum lead</li>
<li><strong>Mostra métricas</strong>: quantos leads, taxa de conversão, receita prevista</li>
</ul>

<h2>Quem precisa de CRM?</h2>
<p>Se você tem mais de 10 clientes ou oportunidades simultâneas, precisa. Planilha funciona até certo ponto, mas:</p>
<ul>
<li>Não avisa quando um follow-up está atrasado</li>
<li>Não mostra o funil visualmente</li>
<li>Não registra histórico de interações</li>
<li>Não escala quando a equipe cresce</li>
</ul>

<h2>CRM para PMEs: o que procurar?</h2>
<ul>
<li><strong>Simples de usar</strong>: se exige treinamento de 2 semanas, é complicado demais</li>
<li><strong>Pipeline visual</strong>: Kanban com drag-and-drop é o mais intuitivo</li>
<li><strong>Preço acessível</strong>: CRMs enterprise custam R$200+/usuário. PMEs precisam de opções a partir de R$0</li>
<li><strong>Prospecção integrada</strong>: o CRM ideal não só organiza leads, mas <a href="/blog/como-encontrar-clientes-pela-internet">ajuda a encontrar novos</a></li>
</ul>

<h2>CRM + prospecção automática</h2>
<p>A maioria dos CRMs do mercado só organiza leads que você já tem. O TurboVenda vai além: ele <a href="/blog/como-prospectar-clientes-b2b">prospecta automaticamente</a> usando IA, extrai contatos completos e alimenta seu <a href="/blog/pipeline-de-vendas-como-montar">pipeline</a> sem esforço. É CRM e prospecção numa única ferramenta, a partir de R$0/mês.</p>
"""
    },
    {
        'slug': 'como-prospectar-clinicas-e-consultorios',
        'titulo': 'Como Prospectar Clínicas e Consultórios: Guia para Vendas no Setor de Saúde',
        'desc': 'Aprenda a encontrar clínicas médicas, odontológicas e laboratórios para prospectar. Estratégias específicas para vender no setor de saúde.',
        'keywords': 'prospectar clínicas, vender para consultórios, leads saúde, prospecção médica, vendas saúde',
        'data': '2026-07-25',
        'tempo': '7 min',
        'conteudo': """
<p>O setor de saúde no Brasil tem mais de 350 mil estabelecimentos ativos. Para quem vende equipamentos médicos, software para clínicas, insumos hospitalares ou serviços B2B para saúde, prospectar esse mercado exige abordagem específica.</p>

<h2>Por que prospectar clínicas é diferente</h2>
<p>Diferente de outros segmentos B2B, o setor de saúde tem particularidades:</p>
<ul>
<li><strong>Decisor nem sempre é o médico</strong> — em clínicas de médio porte, quem compra é o administrador ou gerente de compras</li>
<li><strong>Ciclo de venda consultivo</strong> — equipamentos médicos exigem demonstração e aprovação técnica</li>
<li><strong>Regulação pesada</strong> — ANVISA, conselhos regionais e normas sanitárias influenciam decisões</li>
<li><strong>Horário restrito</strong> — profissionais de saúde atendem pacientes durante o dia, o melhor horário de contato é entre 12h-14h ou após 18h</li>
</ul>

<h2>Onde encontrar clínicas para prospectar</h2>
<h3>1. Dados abertos da Receita Federal</h3>
<p>Toda clínica tem CNPJ. Os dados abertos do CNPJ permitem filtrar por CNAE (atividade econômica), cidade e data de abertura. O TurboVenda usa esses dados para montar listas segmentadas — veja <a href="/empresas">empresas por segmento e cidade</a> com dados reais.</p>

<h3>2. Conselhos regionais (CRM, CRO)</h3>
<p>Os conselhos de medicina e odontologia publicam cadastros de profissionais. Cruzar com dados de CNPJ revela quais médicos também são sócios de clínicas — ou seja, decisores.</p>

<h3>3. Google Maps e diretórios de saúde</h3>
<p>Plataformas como Doctoralia, BoaConsulta e o próprio Google Maps listam milhares de clínicas com telefone, endereço e especialidade. O TurboVenda automatiza essa coleta.</p>

<h2>Modelo de abordagem para clínicas</h2>
<p>E-mails para clínicas que funcionam seguem uma fórmula: <strong>menção ao segmento + dor específica + prova rápida</strong>.</p>
<p>Exemplo: <em>"Olá [Nome], vi que a [Clínica] atua com ortopedia em [Cidade]. Ajudo fornecedores do setor de saúde a encontrar clínicas novas — semana passada entregamos 47 contatos de clínicas recém-abertas no Paraná. Posso mostrar em 5 min?"</em></p>

<h2>Automatizando a prospecção no setor de saúde</h2>
<p>Com o TurboVenda, você descreve seu público (ex: "clínicas odontológicas com mais de 3 dentistas no Sul do Brasil") e a IA monta a lista com razão social, CNPJ, bairro e porte. Depois, o CRM organiza a abordagem por <a href="/blog/email-marketing-b2b-templates">e-mail</a> ou <a href="/blog/whatsapp-para-vendas-b2b">WhatsApp</a>. Conheça mais sobre <a href="/para/saude">prospecção para o setor de saúde</a>.</p>
"""
    },
    {
        'slug': 'crm-para-distribuidora',
        'titulo': 'CRM para Distribuidora: Como Organizar Vendas e Expandir Carteira',
        'desc': 'Saiba como distribuidoras e atacadistas usam CRM para prospectar novos PDVs, organizar rotas e aumentar faturamento.',
        'keywords': 'CRM distribuidora, CRM atacadista, sistema vendas distribuidora, prospectar PDV, expandir carteira',
        'data': '2026-07-23',
        'tempo': '7 min',
        'conteudo': """
<p>Distribuidoras vivem de volume e capilaridade. Quanto mais PDVs (pontos de venda) ativos na carteira, maior o faturamento. Mas gerenciar centenas de clientes, rotas e pedidos sem um CRM é receita para perder vendas.</p>

<h2>O problema de distribuidoras sem CRM</h2>
<ul>
<li><strong>Vendedores usam planilha ou caderno</strong> — quando saem, levam a carteira junto</li>
<li><strong>Sem visibilidade de pipeline</strong> — não sabe quantos PDVs novos estão em negociação</li>
<li><strong>Follow-up esquecido</strong> — prospects esfriam porque ninguém ligou de volta</li>
<li><strong>Territórios sem cobertura</strong> — regiões inteiras sem prospecção ativa</li>
</ul>

<h2>O que muda com um CRM</h2>
<p>Um CRM para distribuidora centraliza toda a operação comercial:</p>
<ul>
<li><strong>Cadastro de PDVs</strong> com endereço, contato do comprador, frequência de pedido</li>
<li><strong>Pipeline visual</strong> — arraste cards entre "Primeiro contato", "Visita agendada", "Proposta enviada", "Cliente ativo"</li>
<li><strong>Histórico de interações</strong> — cada ligação, visita e e-mail registrado</li>
<li><strong>Métricas por vendedor</strong> — quantos PDVs cada um prospecta, visita e converte</li>
</ul>

<h2>Prospectar novos PDVs automaticamente</h2>
<p>O maior diferencial de um CRM com prospecção integrada: encontrar novos pontos de venda sem esforço manual. O TurboVenda busca empresas por segmento e região — por exemplo, "pet shops em Santa Catarina" ou "farmácias no interior de SP" — e entrega nome, CNPJ e contato do responsável. Veja <a href="/empresas">empresas reais por segmento</a> na nossa base.</p>

<p>Combine com <a href="/blog/como-prospectar-clientes-b2b">estratégias de prospecção B2B</a> e um <a href="/blog/pipeline-de-vendas-como-montar">pipeline bem estruturado</a> para escalar sua carteira. Conheça mais sobre <a href="/para/comercio">prospecção para o setor de comércio</a>.</p>
"""
    },
    {
        'slug': 'automacao-comercial-para-industria',
        'titulo': 'Automação Comercial para Indústria: Como Prospectar Compradores Industriais',
        'desc': 'Guia prático de automação comercial para indústrias. Como encontrar compradores, distribuidores e revendas usando IA.',
        'keywords': 'automação comercial indústria, prospectar compradores industriais, vendas indústria, CRM industrial',
        'data': '2026-07-21',
        'tempo': '8 min',
        'conteudo': """
<p>Indústrias dependem de vendas B2B de alto ticket e ciclo longo. O desafio é encontrar compradores qualificados — diretores de produção, gerentes de compras, engenheiros de processo — sem depender exclusivamente de feiras e indicações.</p>

<h2>Os canais tradicionais estão saturados</h2>
<p>Feiras setoriais custam R$20-50 mil por edição. Indicações são valiosas mas não escalam. Ligações frias para PABX têm taxa de contato abaixo de 5%. A automação comercial resolve isso ao combinar <strong>dados públicos + IA + abordagem multi-canal</strong>.</p>

<h2>Como automatizar a prospecção industrial</h2>
<h3>1. Defina seu ICP industrial</h3>
<p>Perfil de Cliente Ideal para indústrias é muito específico: porte (faturamento, número de funcionários), CNAE (atividade econômica), região, e se é fabricante, distribuidor ou integrador.</p>

<h3>2. Monte listas com dados da Receita Federal</h3>
<p>Os dados abertos do CNPJ classificam cada empresa por CNAE, porte e localização. O TurboVenda cruza esses dados para entregar listas segmentadas — por exemplo, <a href="/empresas">metalúrgicas de médio porte no Paraná</a> ou fábricas de embalagens em São Paulo.</p>

<h3>3. Aborde o decisor certo</h3>
<p>Em indústrias, o comprador raramente é quem atende o telefone geral. A prospecção com IA extrai nomes de diretores e gerentes de fontes públicas (LinkedIn, site institucional) e permite abordagem direta via <a href="/blog/email-marketing-b2b-templates">e-mail personalizado</a>.</p>

<h3>4. Mantenha cadência no CRM</h3>
<p>Vendas industriais precisam de 6-12 toques antes do primeiro pedido. Um <a href="/blog/pipeline-de-vendas-como-montar">pipeline</a> bem estruturado garante que nenhum follow-up escape. Saiba mais sobre <a href="/para/industria">prospecção para o setor industrial</a>.</p>
"""
    },
    {
        'slug': 'como-vender-para-cooperativas-agricolas',
        'titulo': 'Como Vender para Cooperativas Agrícolas: Prospecção no Agronegócio',
        'desc': 'Estratégias para prospectar cooperativas agrícolas, cerealistas e empresas do agronegócio. Como encontrar compradores no agro.',
        'keywords': 'vender cooperativas agrícolas, prospecção agronegócio, vendas agro B2B, cooperativas agro',
        'data': '2026-07-19',
        'tempo': '7 min',
        'conteudo': """
<p>O agronegócio brasileiro representa 24% do PIB. Cooperativas agrícolas, cerealistas, distribuidoras de insumos e indústrias de processamento movimentam bilhões em compras B2B. O problema: encontrar o decisor certo nessas organizações exige estratégia.</p>

<h2>Quem compra no agro</h2>
<ul>
<li><strong>Cooperativas</strong> — gerente comercial ou diretor de compras (não o presidente)</li>
<li><strong>Cerealistas</strong> — proprietário ou gerente de operações</li>
<li><strong>Distribuidoras de insumos</strong> — comprador ou gerente de produto</li>
<li><strong>Indústrias de processamento</strong> — gerente industrial ou de suprimentos</li>
</ul>

<h2>Onde encontrar empresas do agro para prospectar</h2>
<p>O TurboVenda cruza dados da Receita Federal filtrando por CNAEs do agronegócio — fabricação de rações, comércio de cereais, máquinas agrícolas — e entrega listas com razão social, cidade, porte e ano de abertura. Explore a <a href="/empresas">base de empresas por segmento</a>.</p>

<h2>Calendário de prospecção no agro</h2>
<p>O agronegócio tem sazonalidade forte:</p>
<ul>
<li><strong>Jan-Mar</strong>: colheita de soja/milho — decisores focados na operação, prospecção mais difícil</li>
<li><strong>Abr-Jun</strong>: entressafra — melhor janela para prospectar equipamentos e serviços</li>
<li><strong>Jul-Set</strong>: planejamento da safra seguinte — decisões de compra de insumos e maquinário</li>
<li><strong>Out-Dez</strong>: plantio — investimentos já definidos, foco em entrega</li>
</ul>

<p>A prospecção contínua com <a href="/blog/automacao-comercial-guia-completo">automação comercial</a> garante presença no momento certo. Conheça as soluções para <a href="/para/agronegocio">prospecção no agronegócio</a>.</p>
"""
    },
    {
        'slug': 'prospectar-empresas-de-tecnologia',
        'titulo': 'Como Prospectar Empresas de Tecnologia: Guia para Vendas B2B em Tech',
        'desc': 'Aprenda a encontrar software houses, startups e consultorias de TI para prospectar. Estratégias de vendas B2B para o setor de tecnologia.',
        'keywords': 'prospectar empresas tecnologia, vendas B2B tech, leads TI, prospecção startups, vender para software house',
        'data': '2026-07-17',
        'tempo': '7 min',
        'conteudo': """
<p>Empresas de tecnologia são um dos melhores mercados B2B para prospectar: decisores conectados, orçamento para ferramentas, e ciclos de decisão mais curtos que indústria tradicional. O desafio é se destacar num mercado que já recebe muita prospecção.</p>

<h2>O perfil do comprador tech</h2>
<p>CTOs, heads de engenharia e founders de startups são bombardeados por e-mails de vendas. Para converter, sua abordagem precisa:</p>
<ul>
<li><strong>Ser técnica</strong> — jargão genérico de vendas não funciona com devs e CTOs</li>
<li><strong>Mostrar valor imediato</strong> — demo ou trial, não slides</li>
<li><strong>Respeitar o canal</strong> — Slack e e-mail são preferidos a ligação fria</li>
</ul>

<h2>Encontrando empresas de tech para prospectar</h2>
<p>Dados da Receita Federal classificam empresas por CNAE. Os CNAEs de tecnologia incluem desenvolvimento de software (6201-5), consultoria em TI (6204-0) e suporte técnico (6209-1). O TurboVenda filtra essas empresas por região e porte — explore a <a href="/empresas">base de empresas de tecnologia</a>.</p>

<h2>Estratégias que funcionam em tech</h2>
<h3>1. Prospecção por sinal de crescimento</h3>
<p>Empresas contratando (vagas abertas) ou que receberam investimento têm orçamento disponível. Combine dados de CNPJ com monitoramento de vagas.</p>

<h3>2. Comunidades e eventos</h3>
<p>Meetups, conferências e comunidades online (Discord, Slack) são onde decisores tech passam tempo. Participar genuinamente gera leads quentes.</p>

<h3>3. Conteúdo técnico</h3>
<p>Blog posts e ferramentas gratuitas atraem tráfego orgânico de devs e CTOs. Combine com <a href="/blog/como-gerar-leads-qualificados">estratégias de geração de leads</a> para converter visitantes em trials.</p>

<p>Conheça mais sobre <a href="/para/tecnologia">prospecção no setor de tecnologia</a>.</p>
"""
    },
    {
        'slug': 'como-prospectar-contabilidades',
        'titulo': 'Como Prospectar Escritórios de Contabilidade: Vendas B2B para Contadores',
        'desc': 'Estratégias para vender para escritórios de contabilidade. Como encontrar contadores e oferecer produtos e serviços B2B.',
        'keywords': 'prospectar contabilidade, vender para contadores, leads contabilidade, vendas B2B contabilidade',
        'data': '2026-07-15',
        'tempo': '6 min',
        'conteudo': """
<p>O Brasil tem mais de 80 mil escritórios de contabilidade ativos. Eles compram software, certificado digital, seguros, materiais de escritório e serviços terceirizados. Se você vende para contadores, a prospecção certa faz toda a diferença.</p>

<h2>Por que contabilidades são bons clientes B2B</h2>
<ul>
<li><strong>Ticket recorrente</strong> — assinaturas de software, certificados digitais renovados anualmente</li>
<li><strong>Decisor acessível</strong> — em escritórios pequenos, o sócio decide; nos maiores, o gerente administrativo</li>
<li><strong>Multiplicador</strong> — um contador satisfeito indica para outros contadores e para seus clientes</li>
</ul>

<h2>Onde encontrar escritórios de contabilidade</h2>
<p>O CNAE 6920-6 (atividades de contabilidade) identifica todos os escritórios registrados na Receita Federal. O TurboVenda filtra por cidade e porte, entregando listas prontas para abordagem. Veja <a href="/empresas">empresas por segmento e região</a>.</p>

<h2>Abordagem que funciona com contadores</h2>
<p>Contadores são pragmáticos e ocupados. A melhor abordagem é direta e focada em economia de tempo ou dinheiro:</p>
<p><em>"[Nome], vi que a [Escritório] atende empresas em [Cidade]. Temos [produto] que economiza X horas/mês no processo de [tarefa]. Posso mostrar em 5 min como funciona?"</em></p>

<p>Combine prospecção de contabilidades com as técnicas de <a href="/blog/email-marketing-b2b-templates">e-mail marketing B2B</a> e <a href="/blog/whatsapp-para-vendas-b2b">WhatsApp para vendas</a>. Conheça mais sobre <a href="/para/servicos">prospecção para o setor de serviços</a>.</p>
"""
    },
    {
        'slug': 'como-prospectar-metalurgicas',
        'titulo': 'Como Prospectar Metalúrgicas e Indústrias de Usinagem',
        'desc': 'Guia prático para encontrar metalúrgicas, tornearias e indústrias de usinagem para prospectar. Vendas B2B no setor metalúrgico.',
        'keywords': 'prospectar metalúrgicas, vendas metalurgia, leads usinagem, prospecção industrial, metalúrgica B2B',
        'data': '2026-07-13',
        'tempo': '6 min',
        'conteudo': """
<p>O setor metalúrgico brasileiro emprega mais de 500 mil trabalhadores em metalúrgicas, tornearias, funções e indústrias de usinagem. São empresas que compram matéria-prima, ferramentas, equipamentos, EPI, gases industriais e serviços de manutenção. Prospectar esse mercado exige conhecer a cadeia.</p>

<h2>Tipos de metalúrgicas e o que compram</h2>
<ul>
<li><strong>Tornearias e usinagem</strong> — ferramentas de corte, fluidos de usinagem, máquinas CNC</li>
<li><strong>Serralheria e caldeiraria</strong> — chapas, tubos, eletrodos, gases de soldagem</li>
<li><strong>Fundições</strong> — matéria-prima (sucata, lingotes), refratários, areia</li>
<li><strong>Tratamento de superfície</strong> — produtos químicos, EPIs, equipamentos de banho</li>
</ul>

<h2>Como encontrar metalúrgicas para prospectar</h2>
<p>Os dados da Receita Federal permitem filtrar por CNAEs como fabricação de estruturas metálicas (2511-0), usinagem (2539-0) e obras de caldeiraria (2513-6). O TurboVenda organiza esses dados por cidade e porte — veja na <a href="/empresas">base de empresas por segmento</a>.</p>

<h2>Melhor abordagem para o setor metalúrgico</h2>
<p>Decisores em metalúrgicas são práticos e técnicos. Evite jargão de marketing; foque em:</p>
<ul>
<li>Economia de custo ou tempo (ex: "reduz troca de ferramenta em 40%")</li>
<li>Prova técnica (fichas técnicas, comparativos de desempenho)</li>
<li>Visita presencial ou vídeo demonstrativo</li>
</ul>

<p>Combine com <a href="/blog/prospecao-outbound-guia">prospecção outbound</a> e <a href="/blog/automacao-comercial-guia-completo">automação comercial</a> para escalar. Conheça mais sobre <a href="/para/industria">prospecção para o setor industrial</a>.</p>
"""
    },
    {
        'slug': 'turbovenda-vs-rdstation',
        'titulo': 'TurboVenda vs RD Station: Qual CRM Escolher para Prospecção B2B?',
        'desc': 'Comparativo entre TurboVenda e RD Station CRM. Preços, funcionalidades e qual é melhor para prospecção outbound B2B.',
        'keywords': 'TurboVenda vs RD Station, alternativa RD Station, comparar CRM, CRM prospecção B2B, RD Station alternativa',
        'data': '2026-07-27',
        'tempo': '6 min',
        'conteudo': """
<p>Se você está escolhendo um CRM para prospecção B2B, provavelmente já viu o RD Station. É a ferramenta mais conhecida no Brasil — mas será que é a melhor opção para <strong>prospecção outbound</strong>?</p>

<h2>Diferenças fundamentais</h2>
<p>O RD Station nasceu como ferramenta de <strong>inbound marketing</strong> (landing pages, formulários, automação de e-mail). O CRM veio depois. O TurboVenda nasceu como ferramenta de <strong>prospecção outbound</strong> com IA — o CRM é parte do fluxo de prospecção, não um produto separado.</p>

<h2>Comparativo de funcionalidades</h2>
<table style="width:100%;border-collapse:collapse;margin:16px 0">
<tr style="border-bottom:2px solid rgba(255,255,255,.1)"><th style="text-align:left;padding:8px">Funcionalidade</th><th style="padding:8px">TurboVenda</th><th style="padding:8px">RD Station CRM</th></tr>
<tr style="border-bottom:1px solid rgba(255,255,255,.05)"><td style="padding:8px">Prospecção automática com IA</td><td style="text-align:center;padding:8px">✅</td><td style="text-align:center;padding:8px">❌</td></tr>
<tr style="border-bottom:1px solid rgba(255,255,255,.05)"><td style="padding:8px">Busca de empresas por CNAE/região</td><td style="text-align:center;padding:8px">✅</td><td style="text-align:center;padding:8px">❌</td></tr>
<tr style="border-bottom:1px solid rgba(255,255,255,.05)"><td style="padding:8px">Extração de contatos (decisores)</td><td style="text-align:center;padding:8px">✅</td><td style="text-align:center;padding:8px">❌</td></tr>
<tr style="border-bottom:1px solid rgba(255,255,255,.05)"><td style="padding:8px">CRM com Kanban</td><td style="text-align:center;padding:8px">✅</td><td style="text-align:center;padding:8px">✅</td></tr>
<tr style="border-bottom:1px solid rgba(255,255,255,.05)"><td style="padding:8px">E-mail em massa</td><td style="text-align:center;padding:8px">✅</td><td style="text-align:center;padding:8px">✅</td></tr>
<tr style="border-bottom:1px solid rgba(255,255,255,.05)"><td style="padding:8px">Landing pages</td><td style="text-align:center;padding:8px">❌</td><td style="text-align:center;padding:8px">✅</td></tr>
<tr style="border-bottom:1px solid rgba(255,255,255,.05)"><td style="padding:8px">Automação de inbound</td><td style="text-align:center;padding:8px">❌</td><td style="text-align:center;padding:8px">✅</td></tr>
<tr><td style="padding:8px">Preço inicial</td><td style="text-align:center;padding:8px">R$ 0/mês</td><td style="text-align:center;padding:8px">R$ 0/mês</td></tr>
</table>

<h2>Quando escolher o TurboVenda</h2>
<ul>
<li>Seu modelo de vendas é <strong>outbound</strong> — você vai atrás do cliente</li>
<li>Precisa de <strong>listas de empresas</strong> segmentadas por região e setor</li>
<li>Quer <strong>prospecção automática</strong> rodando 24/7 sem SDR</li>
<li>Equipe pequena que precisa de <a href="/blog/o-que-e-crm-para-que-serve">CRM simples</a> + prospecção num lugar só</li>
</ul>

<h2>Quando escolher o RD Station</h2>
<ul>
<li>Seu modelo é <strong>inbound</strong> — gera leads via conteúdo e formulários</li>
<li>Precisa de <strong>landing pages</strong> e automação de marketing</li>
<li>Já tem base de leads e quer nurturing por e-mail</li>
</ul>

<p>Para prospecção outbound B2B, o TurboVenda entrega o que o RD Station não faz: encontrar empresas novas. <a href="/cadastro">Teste grátis com 50 leads</a>.</p>
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
                           segmentos=SEGMENTOS,
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
        "Disallow: /logout\n"
        "Disallow: /trial-expirado\n"
        "Disallow: /pagamento/\n"
        "Disallow: /t/\n\n"
        "User-agent: GPTBot\n"
        "Allow: /\n\n"
        "User-agent: ClaudeBot\n"
        "Allow: /\n\n"
        "User-agent: PerplexityBot\n"
        "Allow: /\n\n"
        "User-agent: Google-Extended\n"
        "Allow: /\n\n"
        "Sitemap: https://www.turbovenda.com.br/sitemap.xml\n"
    )
    return app.response_class(txt, mimetype='text/plain')


SEGMENTOS = [
    {
        'slug': 'agronegocio', 'nome': 'Agronegócio',
        'desc': 'Encontre cooperativas, distribuidores de insumos, revendas agrícolas e agroindústrias automaticamente. O TurboVenda prospecta compradores do agro em todo o Brasil.',
        'exemplos': 'cooperativas, revendas de insumos, distribuidores de defensivos, agroindústrias, cerealistas, frigoríficos, fazendas produtoras',
        'dores': [
            'Encontrar decisores de compra (gerentes de compras, diretores de cooperativas) sem depender de indicação ou feira agrícola',
            'Prospectar revendas e distribuidoras em regiões remotas onde visitas presenciais são caras e demoradas',
            'Manter um pipeline constante de leads qualificados entre safras, quando o fluxo comercial diminui',
            'Identificar agroindústrias que estão expandindo capacidade ou abrindo novas unidades',
        ],
        'msg_exemplo': 'Olá [Nome], vi que a [Empresa] atua com distribuição de insumos na região de [Cidade]. Trabalho com uma solução que ajuda fornecedores do agro a encontrar novas revendas e cooperativas para vender — já entregamos listas de mais de 200 compradores por mês para empresas do setor. Posso mostrar como funciona em 5 minutos?',
        'faq': [
            ('Funciona para empresas que vendem para o agro?', 'Sim. O TurboVenda encontra cooperativas, revendas, distribuidores e agroindústrias a partir de buscas inteligentes com IA. Você define o perfil (ex: "distribuidores de fertilizantes no Mato Grosso") e o robô prospecta 24/7.'),
            ('Quais dados o TurboVenda extrai de empresas do agronegócio?', 'Telefone, email, CNPJ, razão social, endereço, site e nome de decisores (quando disponível publicamente). Dados de fontes públicas como Google, LinkedIn e sites institucionais.'),
            ('Consigo filtrar por região ou tipo de cultura?', 'Sim. Você pode definir termos como "cooperativas de soja no Paraná" ou "revendas de sementes em Goiás". A IA gera variações e o robô varre resultados regionalizados.'),
        ],
    },
    {
        'slug': 'industria', 'nome': 'Indústria',
        'desc': 'Prospecte fábricas, metalúrgicas, indústrias alimentícias e manufaturas. Encontre compradores industriais com telefone, email e decisores.',
        'exemplos': 'metalúrgicas, fábricas, indústrias alimentícias, indústrias químicas, manufaturas, siderúrgicas, embalagens',
        'dores': [
            'Mapear compradores industriais (diretores de produção, engenheiros de processo) sem acesso a bases de dados caras como Econodata',
            'Prospectar fábricas de médio porte que não aparecem em feiras ou não têm site atualizado',
            'Encontrar novas indústrias em parques industriais ou distritos que estão expandindo operações',
            'Manter cadência de prospecção outbound mesmo com equipe comercial reduzida',
        ],
        'msg_exemplo': 'Olá [Nome], vi que a [Empresa] é uma metalúrgica em [Cidade] e trabalha com usinagem de peças. Ajudo fornecedores industriais a encontrar novos compradores automaticamente — o sistema gera listas de fábricas com contato direto do decisor. Podemos conversar 5 minutos sobre como funciona?',
        'faq': [
            ('O TurboVenda encontra indústrias de qualquer segmento?', 'Sim. Metalúrgicas, alimentícias, químicas, plásticos, embalagens, usinagem, eletrônica — você define o perfil industrial desejado e a IA adapta a busca.'),
            ('Consigo prospectar por porte ou localização da indústria?', 'Sim. Defina termos como "indústrias alimentícias médio porte em São Paulo" ou "fábricas de embalagens no Sul". O robô filtra e entrega contatos regionalizados.'),
            ('Os dados incluem nome do comprador/decisor?', 'Quando disponível publicamente (LinkedIn, site institucional), sim. O TurboVenda extrai nomes de diretores, gerentes de compras e engenheiros listados em fontes públicas.'),
        ],
    },
    {
        'slug': 'tecnologia', 'nome': 'Tecnologia',
        'desc': 'Encontre software houses, consultorias de TI, startups e empresas de tecnologia. Prospecte decisores de tech com IA.',
        'exemplos': 'software houses, consultorias de TI, startups SaaS, integradores de sistemas, empresas de cloud, fintechs',
        'dores': [
            'Encontrar CTOs e heads de engenharia de empresas que estão contratando ou escalando time (sinal de orçamento disponível)',
            'Prospectar startups em estágio seed/série A que precisam de ferramentas mas não aparecem em diretórios tradicionais',
            'Mapear integradores e consultorias de TI que revendem soluções ou fazem parcerias tecnológicas',
            'Manter pipeline ativo num mercado onde decisores trocam de empresa frequentemente',
        ],
        'msg_exemplo': 'Olá [Nome], vi que a [Empresa] é uma software house em [Cidade] focada em [nicho]. Trabalho com uma ferramenta que encontra empresas de tecnologia que estão expandindo — entrega nome, email e telefone do decisor. Já ajudamos consultorias de TI a gerar 50+ leads qualificados por semana. Quer ver como funciona?',
        'faq': [
            ('Funciona para vender SaaS B2B?', 'Sim. Defina o perfil (ex: "empresas de e-commerce com mais de 50 funcionários") e o TurboVenda entrega contatos com email e telefone do decisor. Ideal para SDRs de SaaS.'),
            ('Consigo encontrar startups que acabaram de receber investimento?', 'O TurboVenda busca em fontes públicas. Se a startup tem site, LinkedIn ou aparece em diretórios, ela será encontrada. Combinando termos como "startup série A fintech" você refina bastante.'),
            ('Integra com meu CRM atual?', 'Você pode exportar em CSV para importar em qualquer CRM. O plano Pro tem API REST para integração direta com HubSpot, Pipedrive e outros via webhook.'),
        ],
    },
    {
        'slug': 'saude', 'nome': 'Saúde',
        'desc': 'Prospecte clínicas, hospitais, laboratórios e distribuidores de equipamentos médicos. Encontre compradores do setor de saúde.',
        'exemplos': 'clínicas, hospitais, laboratórios, distribuidores de equipamentos médicos, farmácias de manipulação, planos de saúde',
        'dores': [
            'Encontrar administradores e diretores de clínicas que tomam decisão de compra (não apenas o médico)',
            'Prospectar laboratórios e clínicas que estão abrindo ou expandindo unidades em novas cidades',
            'Mapear distribuidores de material hospitalar em regiões fora dos grandes centros',
            'Manter pipeline de vendas consultivas com ciclo longo sem perder follow-up',
        ],
        'msg_exemplo': 'Olá [Nome], vi que a [Empresa] atua como distribuidora de equipamentos médicos em [Estado]. Ajudo empresas do setor de saúde a encontrar novas clínicas e laboratórios para prospectar — o sistema entrega lista com telefone e email do responsável. Posso mostrar um exemplo real em 5 minutos?',
        'faq': [
            ('O TurboVenda encontra clínicas e consultórios?', 'Sim. Clínicas médicas, odontológicas, laboratórios, hospitais, farmácias de manipulação — qualquer estabelecimento de saúde com presença online é prospectado.'),
            ('Os dados respeitam sigilo médico/LGPD?', 'Sim. O TurboVenda prospecta apenas dados empresariais públicos (CNPJ, telefone comercial, email institucional). Não coleta dados de pacientes ou informações clínicas.'),
            ('Funciona para vender equipamentos médicos ou insumos hospitalares?', 'Perfeitamente. Defina termos como "clínicas de imagem em Minas Gerais" ou "laboratórios de análises clínicas" e receba contatos dos decisores de compra.'),
        ],
    },
    {
        'slug': 'servicos', 'nome': 'Serviços',
        'desc': 'Encontre empresas de contabilidade, advocacia, engenharia, arquitetura e consultorias. Prospecte prestadores de serviço B2B.',
        'exemplos': 'contabilidades, escritórios de advocacia, consultorias, empresas de engenharia, seguradoras, empresas de RH',
        'dores': [
            'Encontrar empresas que precisam dos seus serviços mas não estão buscando ativamente (demanda latente)',
            'Prospectar escritórios e consultorias de médio porte que pagam ticket alto mas são difíceis de localizar',
            'Mapear empresas novas que acabaram de abrir CNPJ e precisam de contabilidade, advocacia ou seguros',
            'Escalar prospecção outbound sem contratar SDR (custo alto para empresas de serviço)',
        ],
        'msg_exemplo': 'Olá [Nome], vi que a [Empresa] é um escritório de contabilidade em [Cidade]. Ajudo prestadores de serviço B2B a encontrar novas empresas para prospectar — o sistema entrega lista de CNPJs recém-abertos ou empresas em crescimento, com telefone e email do sócio. Quer ver como funciona?',
        'faq': [
            ('Funciona para escritórios de contabilidade ou advocacia prospectarem clientes?', 'Sim. Defina o perfil (ex: "empresas de comércio abertas nos últimos 6 meses em Curitiba") e receba leads prontos para abordar. Ideal para serviços que atendem PMEs.'),
            ('Consigo encontrar empresas que acabaram de abrir?', 'O TurboVenda busca em fontes públicas incluindo dados de CNPJ. Combinando termos como "empresa nova" + região + segmento, você encontra negócios recém-criados.'),
            ('Serve para consultorias B2B que vendem projetos?', 'Sim. Consultorias de RH, engenharia, gestão, TI — defina o ICP (tamanho, setor, região) e o robô entrega contatos do decisor para abordagem outbound.'),
        ],
    },
    {
        'slug': 'comercio', 'nome': 'Comércio',
        'desc': 'Prospecte distribuidoras, atacadistas, varejistas e redes de lojas. Encontre compradores comerciais em qualquer região.',
        'exemplos': 'distribuidoras, atacadistas, redes de lojas, importadoras, exportadoras, representantes comerciais',
        'dores': [
            'Encontrar novos pontos de venda (PDVs) e redes de lojas para expandir distribuição em regiões novas',
            'Mapear atacadistas e distribuidoras que compram em volume mas não estão em cadastros públicos facilmente',
            'Prospectar representantes comerciais ativos em territórios onde não há cobertura própria',
            'Manter visibilidade de novas lojas abrindo (oportunidade de first-mover com produto/serviço)',
        ],
        'msg_exemplo': 'Olá [Nome], vi que a [Empresa] é uma distribuidora de [produto] em [Região]. Ajudo empresas comerciais a encontrar novos PDVs e atacadistas para expandir território — o sistema entrega lista com contato direto do comprador. Posso mostrar em 5 minutos como funciona?',
        'faq': [
            ('O TurboVenda encontra lojas e pontos de venda?', 'Sim. Varejistas, redes, lojas de bairro, e-commerces — qualquer negócio com presença online. Você define o tipo de comércio e a região desejada.'),
            ('Serve para distribuidoras que querem expandir carteira?', 'Perfeitamente. Defina termos como "pet shops em Santa Catarina" ou "farmácias no interior de SP" e receba contatos do proprietário ou comprador.'),
            ('Consigo encontrar representantes comerciais?', 'Sim. Busque por "representante comercial" + segmento + região. O sistema encontra representantes com registro e contato disponível publicamente.'),
        ],
    },
]


@app.route('/para/<slug>')
def segmento_page(slug):
    seg = next((s for s in SEGMENTOS if s['slug'] == slug), None)
    if not seg:
        return render_template('404.html'), 404
    return render_template('segmento.html', seg=seg, segmentos=SEGMENTOS, ga_id=GA_MEASUREMENT_ID)


def _static_sitemap_urls():
    hoje = _dt.date.today().isoformat()
    urls = [
        ('https://www.turbovenda.com.br/', hoje, 'weekly', '1.0'),
        ('https://www.turbovenda.com.br/cadastro', hoje, 'monthly', '0.8'),
        ('https://www.turbovenda.com.br/blog', hoje, 'weekly', '0.9'),
        ('https://www.turbovenda.com.br/login', hoje, 'monthly', '0.6'),
        ('https://www.turbovenda.com.br/precos', hoje, 'monthly', '0.8'),
        ('https://www.turbovenda.com.br/termos', hoje, 'yearly', '0.3'),
        ('https://www.turbovenda.com.br/privacidade', hoje, 'yearly', '0.3'),
        ('https://www.turbovenda.com.br/empresas', hoje, 'weekly', '0.8'),
        ('https://www.turbovenda.com.br/empresas/sobre-os-dados', hoje, 'yearly', '0.5'),
    ]
    for p in BLOG_POSTS:
        urls.append((
            f"https://www.turbovenda.com.br/blog/{p['slug']}",
            p['data'], 'monthly', '0.7'
        ))
    for s in SEGMENTOS:
        urls.append((
            f"https://www.turbovenda.com.br/para/{s['slug']}",
            hoje, 'monthly', '0.8'
        ))
    return urls


def _render_urlset(urls):
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for loc, lastmod, freq, pri in urls:
        xml += (f'  <url>\n    <loc>{loc}</loc>\n'
                f'    <lastmod>{lastmod}</lastmod>\n'
                f'    <changefreq>{freq}</changefreq>\n'
                f'    <priority>{pri}</priority>\n  </url>\n')
    xml += '</urlset>\n'
    return app.response_class(xml, mimetype='application/xml')


@app.route('/sitemap.xml')
def sitemap_xml():
    """Sitemap index quando há páginas pSEO; senão urlset legado."""
    pseo_urls = _pseo_sitemap_urls()
    if not pseo_urls:
        return _render_urlset(_static_sitemap_urls())
    hoje = _dt.date.today().isoformat()
    n_chunks = (len(pseo_urls) + PSEO_SITEMAP_CHUNK - 1) // PSEO_SITEMAP_CHUNK
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    xml += ('  <sitemap>\n    <loc>https://www.turbovenda.com.br/sitemap-pages.xml</loc>\n'
            f'    <lastmod>{hoje}</lastmod>\n  </sitemap>\n')
    for i in range(1, n_chunks + 1):
        xml += (f'  <sitemap>\n    <loc>https://www.turbovenda.com.br/sitemap-empresas-{i}.xml</loc>\n'
                f'    <lastmod>{hoje}</lastmod>\n  </sitemap>\n')
    xml += '</sitemapindex>\n'
    return app.response_class(xml, mimetype='application/xml')


@app.route('/sitemap-pages.xml')
def sitemap_pages_xml():
    return _render_urlset(_static_sitemap_urls())


@app.route('/sitemap-empresas-<int:n>.xml')
def sitemap_empresas_xml(n):
    pseo_urls = _pseo_sitemap_urls()
    inicio = (n - 1) * PSEO_SITEMAP_CHUNK
    chunk = pseo_urls[inicio:inicio + PSEO_SITEMAP_CHUNK]
    if n < 1 or not chunk:
        return render_template('404.html'), 404
    hoje = _dt.date.today().isoformat()
    return _render_urlset([(u, hoje, 'monthly', '0.7') for u in chunk])


_INDEXNOW_KEY = 'b4f7e2a1c9d84f6e8a3b5c7d9e1f0a2b'


@app.route('/llms.txt')
def llms_txt():
    txt = (
        "# TurboVenda\n"
        "> Plataforma de prospecção B2B automática com IA\n\n"
        "## O que é\n"
        "TurboVenda é um SaaS que automatiza a prospecção comercial B2B.\n"
        "Encontra leads qualificados por segmento, cidade e palavras-chave,\n"
        "envia e-mails e WhatsApp personalizados com IA, e gerencia o pipeline\n"
        "comercial em um CRM com Kanban visual.\n\n"
        "## Público-alvo\n"
        "Equipes comerciais e vendedores B2B de PMEs brasileiras.\n\n"
        "## Funcionalidades principais\n"
        "- Prospecção automática (Google Maps, LinkedIn, buscadores)\n"
        "- CRM com pipeline Kanban\n"
        "- E-mail marketing com IA (personalização por lead)\n"
        "- WhatsApp Business integrado\n"
        "- Agendamento automático de reuniões\n"
        "- Relatórios e métricas de conversão\n\n"
        "## Planos\n"
        "- Grátis: 50 leads\n"
        "- Starter (R$97/mês): 500 leads/mês\n"
        "- Pro (R$297/mês): Leads ilimitados + WhatsApp + prioridade\n\n"
        "## Links\n"
        "- Site: https://www.turbovenda.com.br\n"
        "- Criar conta: https://www.turbovenda.com.br/cadastro\n"
        "- Blog: https://www.turbovenda.com.br/blog\n"
        "- Preços: https://www.turbovenda.com.br/precos\n"
        "- Empresas por segmento e cidade (dados abertos CNPJ): "
        "https://www.turbovenda.com.br/empresas\n"
    )
    return app.response_class(txt, mimetype='text/plain')


@app.route(f'/{_INDEXNOW_KEY}.txt')
def indexnow_key():
    return app.response_class(_INDEXNOW_KEY, mimetype='text/plain')


def _ping_indexnow(urls=None):
    """Submit URLs to IndexNow (Bing/Yandex/etc) + ping Google sitemap."""
    import requests as http
    if not urls:
        urls = [
            'https://www.turbovenda.com.br/',
            'https://www.turbovenda.com.br/precos',
            'https://www.turbovenda.com.br/cadastro',
            'https://www.turbovenda.com.br/blog',
        ]
        for p in BLOG_POSTS:
            urls.append(f"https://www.turbovenda.com.br/blog/{p['slug']}")
        for s in SEGMENTOS:
            urls.append(f"https://www.turbovenda.com.br/para/{s['slug']}")
        # páginas pSEO indexáveis (tier >= 15 empresas, cap MAX_PSEO_PAGES)
        urls.extend(_pseo_sitemap_urls())
    results = {}
    statuses = []
    # IndexNow em lotes de 500 URLs por POST
    for i in range(0, len(urls), 500):
        payload = {
            "host": "www.turbovenda.com.br",
            "key": _INDEXNOW_KEY,
            "keyLocation": f"https://www.turbovenda.com.br/{_INDEXNOW_KEY}.txt",
            "urlList": urls[i:i + 500]
        }
        try:
            r = http.post('https://api.indexnow.org/indexnow',
                          json=payload, timeout=10)
            statuses.append(r.status_code)
        except Exception as e:
            statuses.append(str(e))
    results['indexnow'] = statuses[0] if len(statuses) == 1 else statuses
    results['urls_enviadas'] = len(urls)
    try:
        r = http.get(
            'https://www.google.com/ping?sitemap=https://www.turbovenda.com.br/sitemap.xml',
            timeout=10)
        results['google_ping'] = r.status_code
    except Exception as e:
        results['google_ping'] = str(e)
    return results


@app.route('/admin/indexnow', methods=['POST'])
def admin_indexnow():
    if not session.get('admin_auth'):
        return jsonify({'error': 'unauthorized'}), 401
    results = _ping_indexnow()
    return jsonify(results)


# =============================================================================
# pSEO — /empresas/{cnae}/{municipio-uf} com dados abertos CNPJ (Receita)
# =============================================================================

# Rollout gate: nº máx. de páginas de cidade no sitemap/índice (por contagem desc)
MAX_PSEO_PAGES = int(os.environ.get('MAX_PSEO_PAGES', '10000'))
PSEO_SITEMAP_CHUNK = 5000
PSEO_PAGE_SIZE = int(os.environ.get('PSEO_PAGE_SIZE', '50'))
PSEO_MIN_EMPRESAS = 8       # < 8  -> 404
PSEO_MIN_INDEX = 15         # 8-14 -> noindex,follow | >= 15 -> indexável
_PSEO_SQLITE = os.environ.get('PSEO_SQLITE', '')  # SÓ dev local (fallback)
_PSEO_BASE = 'https://www.turbovenda.com.br'


def _pseo_query(sql, params=()):
    """Consulta a empresas_publicas. Postgres em produção; SQLite só em dev
    (env PSEO_SQLITE) para rodar o app localmente sem Postgres."""
    try:
        if _PSEO_SQLITE:
            import sqlite3
            conn = sqlite3.connect(_PSEO_SQLITE)
            conn.row_factory = sqlite3.Row
            try:
                cur = conn.execute(sql.replace('%s', '?'), params)
                return [dict(r) for r in cur.fetchall()]
            finally:
                conn.close()
        if not DATABASE_URL:
            return []
        conn = _conn()
        try:
            c = conn.cursor()
            c.execute(sql, params)
            return [dict(r) for r in c.fetchall()]
        finally:
            conn.close()
    except Exception as e:
        logger.error(f'pseo query error: {e}')
        return []


_pseo_cache = {'ts': 0.0, 'data': None}


def _pseo_agg():
    """Agregação global (cacheada 15 min): contagens por CNAE x cidade."""
    import time
    if _pseo_cache['data'] is not None and time.time() - _pseo_cache['ts'] < 900:
        return _pseo_cache['data']
    rows = _pseo_query(
        "SELECT cnae_principal AS cnae, municipio, uf, COUNT(*) AS n "
        "FROM empresas_publicas WHERE situacao = '02' "
        "GROUP BY cnae_principal, municipio, uf")
    combos = {}      # (cnae_slug, mun_slug) -> combo
    cidades = {}     # mun_slug -> {'municipio','uf','total'}
    por_cnae = {}    # cnae_slug -> {'total', 'cidades': [combos ordenados]}
    por_cidade = {}  # mun_slug -> [combos ordenados]
    for r in rows:
        info = CNAE_POR_CODIGO.get(str(r['cnae']))
        if not info or not r['municipio'] or not r['uf']:
            continue
        mun_slug = slugify(f"{r['municipio']}-{r['uf']}")
        combo = {'cnae_slug': info['slug'], 'cnae': str(r['cnae']),
                 'municipio': r['municipio'], 'uf': r['uf'],
                 'mun_slug': mun_slug, 'n': int(r['n'])}
        combos[(info['slug'], mun_slug)] = combo
        cid = cidades.setdefault(mun_slug, {'municipio': r['municipio'],
                                            'uf': r['uf'], 'total': 0})
        cid['total'] += combo['n']
        pc = por_cnae.setdefault(info['slug'], {'total': 0, 'cidades': []})
        pc['total'] += combo['n']
        pc['cidades'].append(combo)
        por_cidade.setdefault(mun_slug, []).append(combo)
    for pc in por_cnae.values():
        pc['cidades'].sort(key=lambda c: -c['n'])
    for lst in por_cidade.values():
        lst.sort(key=lambda c: -c['n'])
    ranked = sorted((c for c in combos.values() if c['n'] >= PSEO_MIN_INDEX),
                    key=lambda c: -c['n'])
    sitemap_set = {(c['cnae_slug'], c['mun_slug'])
                   for c in ranked[:MAX_PSEO_PAGES]}
    data = {'combos': combos, 'cidades': cidades, 'por_cnae': por_cnae,
            'por_cidade': por_cidade, 'ranked': ranked,
            'sitemap_set': sitemap_set}
    _pseo_cache['data'] = data
    _pseo_cache['ts'] = time.time()
    return data


def _pseo_sitemap_urls():
    """URLs pSEO indexáveis: hub + sobre + páginas CNAE + top cidades (cap)."""
    agg = _pseo_agg()
    if not agg['sitemap_set']:
        return []
    urls = [f'{_PSEO_BASE}/empresas', f'{_PSEO_BASE}/empresas/sobre-os-dados']
    cnaes_no_ar = sorted({cs for cs, _ in agg['sitemap_set']})
    urls += [f'{_PSEO_BASE}/empresas/{cs}' for cs in cnaes_no_ar]
    urls += [f"{_PSEO_BASE}/empresas/{c['cnae_slug']}/{c['mun_slug']}"
             for c in agg['ranked'][:MAX_PSEO_PAGES]]
    return urls


def _pseo_stats(cnae, municipio, uf):
    """Estatísticas reais usadas no texto/FAQ da página de cidade."""
    portes = _pseo_query(
        "SELECT porte, COUNT(*) AS n FROM empresas_publicas "
        "WHERE cnae_principal = %s AND municipio = %s AND uf = %s "
        "AND situacao = '02' GROUP BY porte ORDER BY n DESC",
        (cnae, municipio, uf))
    bairros = _pseo_query(
        "SELECT bairro, COUNT(*) AS n FROM empresas_publicas "
        "WHERE cnae_principal = %s AND municipio = %s AND uf = %s "
        "AND situacao = '02' AND bairro IS NOT NULL AND bairro != '' "
        "GROUP BY bairro ORDER BY n DESC LIMIT 1",
        (cnae, municipio, uf))
    corte5 = (_dt.date.today() - _dt.timedelta(days=5 * 365)).isoformat()
    novas = _pseo_query(
        "SELECT COUNT(*) AS n FROM empresas_publicas "
        "WHERE cnae_principal = %s AND municipio = %s AND uf = %s "
        "AND situacao = '02' AND data_abertura >= %s",
        (cnae, municipio, uf, corte5))
    porte_top = None
    if portes:
        pt = max((p for p in portes if p['porte']), key=lambda p: p['n'],
                 default=None)
        if pt:
            porte_top = {'label': PORTE_LABELS.get(str(pt['porte']),
                                                   'Não informado'),
                         'n': int(pt['n'])}
    return {
        'porte_top': porte_top,
        'bairro_top': ({'nome': bairros[0]['bairro'], 'n': int(bairros[0]['n'])}
                       if bairros else None),
        'novas_5anos': int(novas[0]['n']) if novas else 0,
    }


def _pseo_texto(seg, combo, stats, vizinhos):
    """120-200 palavras com variáveis reais, 4 templates de frase rotacionados
    por hash do slug (nunca idêntico entre páginas)."""
    h = int(hashlib.md5(
        f"{seg['slug']}|{combo['mun_slug']}".encode()).hexdigest(), 16)
    mun, uf, n = combo['municipio'], combo['uf'], combo['n']
    nome, label = seg['nome'], seg['label']
    uf_nome = UF_NOMES.get(uf, uf)

    intro = [
        f"{mun} - {uf} concentra {n} empresas ativas de {nome}, segundo os dados abertos do CNPJ da Receita Federal. É um dos mercados mapeados pelo TurboVenda no {uf_nome} para quem vende produtos ou serviços a esse segmento e precisa de uma lista confiável para começar a prospectar.",
        f"Segundo os dados abertos do CNPJ da Receita Federal, existem {n} empresas ativas de {nome} em {mun} - {uf}. A lista completa abaixo vem da base oficial de CNPJs e traz razão social, bairro, porte e ano de abertura de cada uma delas.",
        f"O mercado de {nome} em {mun} - {uf} soma {n} CNPJs ativos na base oficial da Receita Federal. Para quem prospecta {label.lower()}, é um território do {uf_nome} que merece entrar no radar do time comercial — a relação completa está na tabela abaixo.",
        f"Quem vende para {label.lower()} encontra em {mun} - {uf} um mercado com {n} empresas ativas, conforme os dados públicos do CNPJ da Receita Federal consolidados pelo TurboVenda — cada uma listada abaixo com bairro, porte e ano de abertura.",
    ]
    porte_txts = []
    if stats['porte_top']:
        pl, pn = stats['porte_top']['label'], stats['porte_top']['n']
        porte_txts = [
            f"O porte predominante é {pl}: são {pn} das {n} empresas do segmento na cidade, o que ajuda a calibrar o discurso comercial e o ticket médio da abordagem.",
            f"Entre elas, {pn} são classificadas como {pl} — o perfil mais comum do segmento na cidade, um dado útil na hora de definir a proposta de valor.",
            f"Em porte, destaque para {pl}, com {pn} empresas — informação que vale ouro para segmentar a oferta antes do primeiro contato.",
            f"A classificação de porte mais frequente é {pl} ({pn} empresas), o que indica o tamanho típico do cliente que você vai encontrar por lá.",
        ]
    bairro_txts = []
    if stats['bairro_top']:
        bn, bq = stats['bairro_top']['nome'], stats['bairro_top']['n']
        bairro_txts = [
            f"Geograficamente, o bairro {bn} lidera com {bq} empresas registradas do segmento.",
            f"O endereço mais comum é o bairro {bn}, com {bq} CNPJs do segmento.",
            f"Dentro da cidade, {bn} é o bairro com mais empresas do ramo: {bq} no total.",
            f"A maior concentração está no bairro {bn}, que reúne {bq} dessas empresas.",
        ]
    viz_txts = []
    if len(vizinhos) >= 2:
        v1, v2 = vizinhos[0], vizinhos[1]
        viz_txts = [
            f"Na comparação regional, {v1['municipio']} - {v1['uf']} tem {v1['n']} empresas do mesmo segmento e {v2['municipio']} - {v2['uf']} tem {v2['n']} — ampliar o raio de prospecção pode multiplicar sua lista.",
            f"Perto dali, o mesmo CNAE soma {v1['n']} empresas em {v1['municipio']} - {v1['uf']} e {v2['n']} em {v2['municipio']} - {v2['uf']}, boas opções para expandir o território.",
            f"Se a meta pedir volume, vale somar as vizinhas: {v1['municipio']} - {v1['uf']} ({v1['n']} empresas) e {v2['municipio']} - {v2['uf']} ({v2['n']}) no mesmo segmento.",
            f"Para efeito de comparação, {v1['municipio']} - {v1['uf']} registra {v1['n']} e {v2['municipio']} - {v2['uf']} registra {v2['n']} empresas ativas do mesmo CNAE.",
        ]
    fecho = [
        f"Com o TurboVenda, essas {n} empresas viram uma lista de prospecção com enriquecimento por IA: telefone, e-mail e site localizados em fontes públicas, prontos para a primeira abordagem comercial — sem planilha manual.",
        f"O TurboVenda transforma esses {n} CNPJs em pipeline de vendas: a IA enriquece cada empresa com contatos de fontes públicas e escreve mensagens personalizadas de abordagem para e-mail e WhatsApp.",
        f"Em vez de garimpar CNPJ por CNPJ, o TurboVenda entrega essas {n} empresas organizadas em um CRM com Kanban, contatos enriquecidos por IA e mensagens de prospecção prontas para enviar.",
        f"São {n} oportunidades reais de negócio na cidade — e o TurboVenda automatiza a prospecção de todas elas com IA, do primeiro contato até o agendamento da reunião comercial.",
    ]

    partes = [intro[h % 4]]
    if porte_txts:
        partes.append(porte_txts[(h // 4) % 4])
    if bairro_txts:
        partes.append(bairro_txts[(h // 16) % 4])
    if viz_txts:
        partes.append(viz_txts[(h // 64) % 4])
    partes.append(fecho[(h // 256) % 4])
    # 2 parágrafos: contexto (intro+porte+bairro) e ação (vizinhos+fecho)
    corte = 3 if len(partes) >= 4 else 2
    return [' '.join(partes[:corte]), ' '.join(partes[corte:])]


def _pseo_404():
    return render_template('404.html'), 404


@app.route('/empresas')
def pseo_hub():
    agg = _pseo_agg()
    cnaes = []
    for seg in CNAE_B2B:
        pc = agg['por_cnae'].get(seg['slug'])
        if pc and pc['total'] > 0:
            cnaes.append({'seg': seg, 'total': pc['total']})
    cnaes.sort(key=lambda x: -x['total'])
    top_cidades = []
    for mun_slug, cid in sorted(agg['cidades'].items(),
                                key=lambda kv: -kv[1]['total'])[:20]:
        melhores = [c for c in agg['por_cidade'].get(mun_slug, [])
                    if c['n'] >= PSEO_MIN_EMPRESAS]
        top_cidades.append({
            'municipio': cid['municipio'], 'uf': cid['uf'],
            'total': cid['total'],
            'url': (f"/empresas/{melhores[0]['cnae_slug']}/{mun_slug}"
                    if melhores else None)})
    total_empresas = sum(x['total'] for x in cnaes)
    return render_template('empresas_hub.html', cnaes=cnaes,
                           top_cidades=top_cidades,
                           total_empresas=total_empresas,
                           ga_id=GA_MEASUREMENT_ID)


@app.route('/empresas/busca')
def pseo_busca():
    seg_slug = request.args.get('segmento', '').strip()
    cidade = request.args.get('cidade', '').strip()
    if seg_slug not in CNAE_POR_SLUG:
        return redirect('/empresas')
    if cidade:
        agg = _pseo_agg()
        alvo = slugify(cidade)
        for c in agg['por_cnae'].get(seg_slug, {}).get('cidades', []):
            if c['n'] >= PSEO_MIN_EMPRESAS and c['mun_slug'].startswith(alvo):
                return redirect(f"/empresas/{seg_slug}/{c['mun_slug']}")
    return redirect(f'/empresas/{seg_slug}')


@app.route('/empresas/sobre-os-dados')
def pseo_sobre_dados():
    return render_template('empresas_sobre.html', ga_id=GA_MEASUREMENT_ID)


@app.route('/empresas/<cnae_slug>')
def pseo_cnae(cnae_slug):
    seg = CNAE_POR_SLUG.get(cnae_slug)
    if not seg:
        return _pseo_404()
    agg = _pseo_agg()
    pc = agg['por_cnae'].get(cnae_slug)
    if not pc or pc['total'] == 0:
        return _pseo_404()
    por_uf = {}
    for c in pc['cidades']:
        d = por_uf.setdefault(c['uf'], {'uf': c['uf'],
                                        'uf_nome': UF_NOMES.get(c['uf'], c['uf']),
                                        'total': 0, 'cidades': []})
        d['total'] += c['n']
        d['cidades'].append({**c, 'tem_pagina': c['n'] >= PSEO_MIN_EMPRESAS})
    ufs = sorted(por_uf.values(), key=lambda d: -d['total'])
    return render_template('empresas_cnae.html', seg=seg, ufs=ufs,
                           total=pc['total'],
                           cnae_fmt=cnae_formatado(seg['codigo']),
                           ga_id=GA_MEASUREMENT_ID)


@app.route('/empresas/<cnae_slug>/<mun_slug>')
def pseo_cidade(cnae_slug, mun_slug):
    seg = CNAE_POR_SLUG.get(cnae_slug)
    if not seg:
        return _pseo_404()
    agg = _pseo_agg()
    combo = agg['combos'].get((cnae_slug, mun_slug))
    # QUALITY GATE: < 8 empresas -> 404
    if not combo or combo['n'] < PSEO_MIN_EMPRESAS:
        return _pseo_404()
    n = combo['n']
    mun, uf = combo['municipio'], combo['uf']
    try:
        pagina = max(1, int(request.args.get('pagina', 1)))
    except (TypeError, ValueError):
        pagina = 1
    total_paginas = max(1, (n + PSEO_PAGE_SIZE - 1) // PSEO_PAGE_SIZE)
    if pagina > total_paginas:
        return _pseo_404()

    rows = _pseo_query(
        "SELECT razao_social, nome_fantasia, bairro, porte, data_abertura "
        "FROM empresas_publicas WHERE cnae_principal = %s AND municipio = %s "
        "AND uf = %s AND situacao = '02' "
        "ORDER BY COALESCE(razao_social, nome_fantasia, cnpj_basico) "
        "LIMIT %s OFFSET %s",
        (combo['cnae'], mun, uf, PSEO_PAGE_SIZE,
         (pagina - 1) * PSEO_PAGE_SIZE))
    empresas = []
    for r in rows:
        empresas.append({
            'nome': r['razao_social'] or r['nome_fantasia'] or 'Empresa sem razão social divulgada',
            'fantasia': (r['nome_fantasia']
                         if r['nome_fantasia'] and r['razao_social'] else None),
            'bairro': r['bairro'] or '—',
            'porte': PORTE_LABELS.get(str(r['porte'] or '00'), 'Não informado'),
            'ano': str(r['data_abertura'])[:4] if r['data_abertura'] else '—',
        })

    stats = _pseo_stats(combo['cnae'], mun, uf)
    vizinhos = [c for c in agg['por_cnae'][cnae_slug]['cidades']
                if c['mun_slug'] != mun_slug and c['uf'] == uf][:2]
    if len(vizinhos) < 2:
        vizinhos = [c for c in agg['por_cnae'][cnae_slug]['cidades']
                    if c['mun_slug'] != mun_slug][:2]
    texto = _pseo_texto(seg, combo, stats, vizinhos)

    # Links cruzados: 10 cidades do mesmo CNAE + 10 CNAEs da mesma cidade
    links_cidades = [c for c in agg['por_cnae'][cnae_slug]['cidades']
                     if c['mun_slug'] != mun_slug
                     and c['n'] >= PSEO_MIN_EMPRESAS][:10]
    links_cnaes = []
    for c in agg['por_cidade'].get(mun_slug, []):
        if c['cnae_slug'] != cnae_slug and c['n'] >= PSEO_MIN_EMPRESAS:
            links_cnaes.append({**c, 'seg': CNAE_POR_SLUG[c['cnae_slug']]})
    links_cnaes = links_cnaes[:10]

    # FAQ com números reais
    cnae_fmt = cnae_formatado(seg['codigo'])
    faq = [
        (f"Quantas empresas de {seg['nome']} existem em {mun}?",
         f"Segundo os dados abertos do CNPJ da Receita Federal, {mun} - {uf} "
         f"tem {n} empresas ativas de {seg['nome']} (CNAE {cnae_fmt}). "
         f"Dessas, {stats['novas_5anos']} abriram nos últimos 5 anos."),
        (f"Como conseguir os contatos dessas {n} empresas?",
         f"Esta página mostra apenas dados cadastrais públicos. No TurboVenda, "
         f"a IA enriquece cada uma das {n} empresas com telefone, e-mail e site "
         f"localizados em fontes públicas, e gera mensagens de prospecção "
         f"personalizadas. O plano grátis inclui 50 leads."),
    ]

    # Indexação: só tier >= 15 dentro do rollout gate; paginações nunca
    indexavel = (pagina == 1 and n >= PSEO_MIN_INDEX
                 and (cnae_slug, mun_slug) in agg['sitemap_set'])
    robots_meta = 'index, follow' if indexavel else 'noindex, follow'
    canonical = f'{_PSEO_BASE}/empresas/{cnae_slug}/{mun_slug}'

    # JSON-LD (montado em Python -> sempre parseável)
    ld_breadcrumb = json.dumps({
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home",
             "item": f"{_PSEO_BASE}/"},
            {"@type": "ListItem", "position": 2, "name": "Empresas",
             "item": f"{_PSEO_BASE}/empresas"},
            {"@type": "ListItem", "position": 3, "name": seg['label'],
             "item": f"{_PSEO_BASE}/empresas/{cnae_slug}"},
            {"@type": "ListItem", "position": 4,
             "name": f"{mun} - {uf}", "item": canonical},
        ]}, ensure_ascii=False)
    ld_itemlist = json.dumps({
        "@context": "https://schema.org", "@type": "ItemList",
        "name": f"Empresas de {seg['nome']} em {mun} - {uf}",
        "numberOfItems": n,
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1,
             "item": {"@type": "Organization", "name": e['nome'],
                      "address": {"@type": "PostalAddress",
                                  "addressLocality": mun,
                                  "addressRegion": uf,
                                  "addressCountry": "BR"}}}
            for i, e in enumerate(empresas[:10])
        ]}, ensure_ascii=False)
    ld_faq = json.dumps({
        "@context": "https://schema.org", "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q,
             "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in faq
        ]}, ensure_ascii=False)

    titulo = (f"Empresas de {seg['nome']} em {mun} - {uf} "
              f"({n} ativas) | TurboVenda")
    descricao = (f"Lista com {n} empresas ativas de {seg['nome']} em "
                 f"{mun} - {uf}, com bairro, porte e ano de abertura. "
                 f"Dados abertos do CNPJ. Prospecte com IA grátis.")
    cta_url = (f"/cadastro?utm_source=pseo&utm_medium=organic"
               f"&utm_campaign={cnae_slug}-{mun_slug}")

    return render_template('empresas_cidade.html', seg=seg, combo=combo,
                           n=n, municipio=mun, uf=uf,
                           uf_nome=UF_NOMES.get(uf, uf),
                           empresas=empresas, pagina=pagina,
                           total_paginas=total_paginas, texto=texto,
                           faq=faq, links_cidades=links_cidades,
                           links_cnaes=links_cnaes, cnae_fmt=cnae_fmt,
                           robots_meta=robots_meta, canonical=canonical,
                           ld_breadcrumb=ld_breadcrumb,
                           ld_itemlist=ld_itemlist, ld_faq=ld_faq,
                           titulo=titulo, descricao=descricao,
                           cta_url=cta_url, ga_id=GA_MEASUREMENT_ID)


@app.route('/manifest.json')
def manifest_json():
    m = {
        "name": "TurboVenda",
        "short_name": "TurboVenda",
        "description": "Prospecção B2B automática com IA",
        "start_url": "/dashboard",
        "display": "standalone",
        "background_color": "#060b18",
        "theme_color": "#6366f1",
        "icons": [
            {"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"}
        ]
    }
    return jsonify(m)


@app.route('/.well-known/security.txt')
def security_txt():
    txt = (
        "Contact: mailto:suporte@turbovenda.com.br\n"
        "Preferred-Languages: pt-BR, en\n"
        "Canonical: https://www.turbovenda.com.br/.well-known/security.txt\n"
        "Expires: 2027-06-01T00:00:00.000Z\n"
    )
    return app.response_class(txt, mimetype='text/plain')


@app.route('/termos')
def termos():
    return render_template('termos.html', ga_id=GA_MEASUREMENT_ID)


@app.route('/privacidade')
def privacidade():
    return render_template('privacidade.html', ga_id=GA_MEASUREMENT_ID)


@app.route('/precos')
def precos():
    return render_template('precos.html', ga_id=GA_MEASUREMENT_ID)


@app.route('/trial-expirado')
@login_required
def trial_expirado():
    user = get_current_user()
    if not user:
        return redirect(url_for('login'))
    plano = (user.get('plano') or 'trial')
    if plano != 'trial':
        return redirect(url_for('dashboard'))
    expira = user.get('plano_expira')
    if expira:
        from datetime import datetime
        if isinstance(expira, str):
            expira = datetime.fromisoformat(expira)
        if expira >= datetime.now():
            return redirect(url_for('dashboard'))
    schema = user.get('schema_name') or f'emp_{user["id"]}'
    stats = get_stats(schema)
    return render_template('trial_expirado.html', user=user, stats=stats,
                           ga_id=GA_MEASUREMENT_ID)


@app.route('/dashboard')
@login_required
def dashboard():
    uid = session.get('user_id')
    schema = f'emp_{uid}'
    user = get_current_user() or {'id': uid, 'schema_name': schema,
                                   'empresa_nome': '', 'email': ''}
    # Redirecionar para tela de trial expirado (exceto se veio para upgrade)
    upgrade_param = request.args.get('upgrade')
    if (user.get('plano') or 'trial') == 'trial' and user.get('plano_expira'):
        from datetime import datetime
        _exp = user['plano_expira']
        if isinstance(_exp, str):
            _exp = datetime.fromisoformat(_exp)
        if _exp < datetime.now() and not upgrade_param:
            return redirect(url_for('trial_expirado'))
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
                           color_bd='rgba(99,102,241,.18)',
                           ga_id=GA_MEASUREMENT_ID,
                           mp_public_key=MP_PUBLIC_KEY)


@app.route('/configurar')
@login_required
def config_page():
    user = get_current_user()
    schema = _get_schema()
    if not schema and user:
        schema = user.get('schema_name')
    cfg = get_bot_config(schema) if schema else {}
    just_registered = session.pop('just_registered', False)
    return render_template('config.html', user=user, cfg=cfg,
                           just_registered=just_registered,
                           oauth_google=_oauth_ativo('google'),
                           oauth_microsoft=_oauth_ativo('microsoft'),
                           dominio_ativo=bool(os.environ.get('RESEND_API_KEY')),
                           email_ok=request.args.get('email_ok', ''),
                           email_erro=request.args.get('email_erro', ''),
                           ga_id=GA_MEASUREMENT_ID)


# =============================================================================
# ROUTES — API (requer sessão ou token)
# =============================================================================

@app.route('/api/<bot>/stats')
@login_required
def api_stats(bot):
    return jsonify(get_stats(_get_schema()))


@app.route('/api/pipeline')
@login_required
def api_pipeline():
    schema = _get_schema()
    if not schema:
        return jsonify({})
    stages = ['novo', 'contactada', 'respondeu', 'qualificado', 'demo', 'convertido']
    per_page = request.args.get('per_page', 50, type=int)
    conn = None
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
        return jsonify(result)
    except Exception as e:
        logger.error(f'pipeline/{schema}: {e}')
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


@app.route('/api/<bot>/leads')
@login_required
def api_leads(bot):
    schema = _get_schema()
    page = max(1, request.args.get('page', 1, type=int) or 1)
    per_page = request.args.get('per_page', 50, type=int) or 50
    per_page = max(1, min(per_page, 1000))  # teto pra nao derrubar o servidor
    return jsonify(get_leads(schema, per_page=per_page, page=page))


@app.route('/api/<bot>/logs')
@login_required
def api_logs(bot):
    return jsonify(get_logs(_get_schema()))


@app.route('/api/<bot>/status')
@login_required
def api_bot_status(bot):
    schema = _get_schema()
    wa_proc = _procs.get(schema, {}).get('wa')
    wa_running = wa_proc is not None and wa_proc.poll() is None
    wa_exit = None
    if wa_proc is not None and wa_proc.poll() is not None:
        wa_exit = wa_proc.returncode
        _procs.setdefault(schema, {})['wa'] = None
    # Estado real do WhatsApp (não só se o processo está vivo)
    wa_real_status = None
    wa_detail = None
    if wa_running:
        try:
            base = os.path.dirname(os.path.abspath(__file__))
            sf = os.path.join(base, 'robo_pili', 'wa_status.json')
            with open(sf, 'r', encoding='utf-8') as f:
                ws = json.load(f)
            wa_real_status = ws.get('status')
            wa_detail = ws.get('detail')
        except Exception:
            wa_real_status = 'iniciando'
    elif not wa_running:
        # Limpa status file quando processo não está rodando
        try:
            base = os.path.dirname(os.path.abspath(__file__))
            sf = os.path.join(base, 'robo_pili', 'wa_status.json')
            if os.path.exists(sf):
                os.remove(sf)
        except Exception:
            pass
    return jsonify({
        'busca': _proc_running(schema, 'busca'),
        'wa': wa_running,
        'wa_exit': wa_exit,
        'wa_status': wa_real_status,
        'wa_detail': wa_detail,
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
    schema = _get_schema()
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
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500
    _procs.setdefault(schema, {})
    _procs[schema][canal] = proc
    return jsonify({'status': 'started', 'pid': proc.pid, 'canal': canal})


@app.route('/api/<bot>/stop', methods=['POST'])
@login_required
def api_bot_stop(bot):
    schema = _get_schema()
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
        logger.exception(f'{request.path}'); return jsonify({'lines': [], 'error': 'Erro interno'})


# --- Lead CRUD ---

@app.route('/api/<bot>/add-lead', methods=['POST'])
@login_required
def api_add_lead(bot):
    schema = _get_schema()
    ok, msg = _check_lead_limit(schema)
    if not ok:
        return jsonify({'error': msg, 'limit_reached': True}), 403
    data = request.get_json(silent=True) or {}
    nome = (data.get('nome_fantasia') or '').strip()
    if not nome:
        return jsonify({'error': 'nome_fantasia obrigatorio'}), 400
    conn = None
    try:
        conn = _conn(schema)
        c = conn.cursor()
        wa = (data.get('whatsapp') or '').strip() or None
        if wa:
            c.execute('SELECT id FROM empresas WHERE whatsapp = %s', (wa,))
            ex = c.fetchone()
            if ex:
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
        return jsonify({'ok': True, 'id': new_id})
    except Exception as e:
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


@app.route('/api/<bot>/lead/<int:lead_id>', methods=['PUT'])
@login_required
def api_update_lead(bot, lead_id):
    schema = _get_schema()
    data = request.get_json(silent=True) or {}
    allowed = {'nome_fantasia', 'whatsapp', 'telefone', 'email', 'segmento',
               'status', 'score', 'cidade', 'estado', 'website', 'linkedin',
               'instagram', 'porte', 'demo_status', 'cnpj', 'observacoes'}
    fields = {k: v for k, v in data.items() if k in allowed}
    if not fields:
        return jsonify({'error': 'nenhum campo valido'}), 400
    conn = None
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
        return jsonify({'ok': True})
    except Exception as e:
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


@app.route('/api/<bot>/lead/<int:lead_id>', methods=['DELETE'])
@login_required
def api_delete_lead(bot, lead_id):
    schema = _get_schema()
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
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500


@app.route('/api/<bot>/clear-all', methods=['POST'])
@login_required
def api_clear_all(bot):
    """Limpa todos os leads, contatos, interações, buscas, logs e contadores."""
    schema = _get_schema()
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
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500


# --- Atividades (Timeline) ---

@app.route('/api/<bot>/lead/<int:lead_id>/atividades')
@login_required
def api_lead_atividades(bot, lead_id):
    schema = _get_schema()
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
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500


@app.route('/api/<bot>/lead/<int:lead_id>/atividade', methods=['POST'])
@login_required
def api_add_atividade(bot, lead_id):
    schema = _get_schema()
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
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500


# --- Tarefas ---

@app.route('/api/<bot>/lead/<int:lead_id>/tarefas')
@login_required
def api_lead_tarefas(bot, lead_id):
    schema = _get_schema()
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
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500


@app.route('/api/<bot>/lead/<int:lead_id>/tarefa', methods=['POST'])
@login_required
def api_add_tarefa(bot, lead_id):
    schema = _get_schema()
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
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500


@app.route('/api/<bot>/tarefa/<int:tarefa_id>', methods=['PUT'])
@login_required
def api_update_tarefa(bot, tarefa_id):
    schema = _get_schema()
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
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500


@app.route('/api/<bot>/tarefa/<int:tarefa_id>', methods=['DELETE'])
@login_required
def api_delete_tarefa(bot, tarefa_id):
    schema = _get_schema()
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute('DELETE FROM tarefas WHERE id = %s', (tarefa_id,))
        conn.commit()
        conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500


@app.route('/api/<bot>/tarefas/pendentes')
@login_required
def api_tarefas_pendentes(bot):
    schema = _get_schema()
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
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500


# --- Enriquecimento CNPJ ---

@app.route('/api/<bot>/lead/<int:lead_id>/enriquecer', methods=['POST'])
@login_required
def api_enriquecer_lead(bot, lead_id):
    schema = _get_schema()
    result = _enriquecer_cnpj(schema, lead_id)
    if result.get('ok'):
        return jsonify(result)
    return jsonify(result), 400


# DDD -> UF (deriva o estado do telefone, sem CNPJ/API)
_DDD_UF = {
    '11': 'SP', '12': 'SP', '13': 'SP', '14': 'SP', '15': 'SP', '16': 'SP',
    '17': 'SP', '18': 'SP', '19': 'SP', '21': 'RJ', '22': 'RJ', '24': 'RJ',
    '27': 'ES', '28': 'ES', '31': 'MG', '32': 'MG', '33': 'MG', '34': 'MG',
    '35': 'MG', '37': 'MG', '38': 'MG', '41': 'PR', '42': 'PR', '43': 'PR',
    '44': 'PR', '45': 'PR', '46': 'PR', '47': 'SC', '48': 'SC', '49': 'SC',
    '51': 'RS', '53': 'RS', '54': 'RS', '55': 'RS', '61': 'DF', '62': 'GO',
    '64': 'GO', '63': 'TO', '65': 'MT', '66': 'MT', '67': 'MS', '68': 'AC',
    '69': 'RO', '71': 'BA', '73': 'BA', '74': 'BA', '75': 'BA', '77': 'BA',
    '79': 'SE', '81': 'PE', '87': 'PE', '82': 'AL', '83': 'PB', '84': 'RN',
    '85': 'CE', '88': 'CE', '86': 'PI', '89': 'PI', '91': 'PA', '93': 'PA',
    '94': 'PA', '92': 'AM', '97': 'AM', '95': 'RR', '96': 'AP', '98': 'MA',
    '99': 'MA',
}


def _uf_do_ddd(raw) -> str:
    if not raw:
        return ''
    d = ''.join(ch for ch in str(raw) if ch.isdigit())
    if len(d) > 11 and d.startswith('55'):
        d = d[2:]
    if len(d) < 10:
        return ''
    return _DDD_UF.get(d[:2], '')


def _preencher_estado_por_ddd(schema, lead_id):
    """Preenche e salva o estado pelo DDD do telefone (grátis, sem API)."""
    conn = _conn(schema)
    c = conn.cursor()
    c.execute('SELECT estado, whatsapp, telefone FROM empresas WHERE id=%s',
              (lead_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return {'ok': False, 'error': 'Lead não encontrado'}
    if (row.get('estado') or '').strip():
        conn.close()
        return {'ok': True, 'estado': row['estado'], 'ja_tinha': True}
    uf = _uf_do_ddd(row.get('whatsapp') or row.get('telefone') or '')
    if not uf:
        conn.close()
        return {'ok': False, 'error': 'Sem telefone com DDD válido'}
    c.execute('UPDATE empresas SET estado=%s WHERE id=%s', (uf, lead_id))
    conn.commit()
    conn.close()
    return {'ok': True, 'estado': uf, 'fonte': 'ddd'}


@app.route('/api/<bot>/lead/<int:lead_id>/requalificar', methods=['POST'])
@login_required
def api_requalificar_lead(bot, lead_id):
    """Requalifica fazendo o máximo de graça: com CNPJ -> enriquece
    (estado/situação/sócio via Receita); sem CNPJ -> ao menos preenche o
    estado pelo DDD do telefone."""
    schema = _get_schema()
    passos = {}
    cn = _descobrir_cnpj(schema, lead_id)
    passos['cnpj'] = cn
    if cn.get('ok') and cn.get('cnpj'):
        passos['enriquecimento'] = _enriquecer_cnpj(schema, lead_id)
    else:
        passos['ddd'] = _preencher_estado_por_ddd(schema, lead_id)
    ok = bool(passos.get('enriquecimento', {}).get('ok')
              or passos.get('ddd', {}).get('ok'))
    return jsonify({'ok': ok, 'passos': passos})


def _buscar_redes_decisor(schema, lead_id):
    """Busca LinkedIn/Instagram do decisor via Serper e salva no contato."""
    conn = _conn(schema)
    c = conn.cursor()
    c.execute('SELECT e.nome_fantasia, ct.id AS cid, ct.nome AS cnome '
              'FROM empresas e '
              'JOIN contatos ct ON ct.empresa_id=e.id AND ct.decisor=1 '
              'WHERE e.id=%s LIMIT 1', (lead_id,))
    row = c.fetchone()
    conn.close()
    if not row or not row.get('cnome'):
        return {'ok': False, 'error': 'Lead sem decisor cadastrado'}
    nome = row['cnome']
    empresa = row.get('nome_fantasia') or ''
    found = {'linkedin': None, 'instagram': None}
    r1 = _serper_search(schema, f'{nome} {empresa} linkedin', num=8)
    if r1.get('ok'):
        for it in r1['results']:
            link = it.get('link', '')
            if 'linkedin.com/in/' in link:
                found['linkedin'] = link
                break
    r2 = _serper_search(schema, f'{nome} {empresa} instagram', num=8)
    if r2.get('ok'):
        for it in r2['results']:
            link = it.get('link', '')
            if 'instagram.com/' in link and '/p/' not in link:
                found['instagram'] = link
                break
    if found['linkedin'] or found['instagram']:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute('UPDATE contatos SET linkedin=COALESCE(%s,linkedin), '
                  'instagram=COALESCE(%s,instagram) WHERE id=%s',
                  (found['linkedin'], found['instagram'], row['cid']))
        conn.commit()
        conn.close()
    return {'ok': True, **found}


@app.route('/api/<bot>/lead/<int:lead_id>/redes-decisor', methods=['POST'])
@login_required
def api_redes_decisor(bot, lead_id):
    schema = _get_schema()
    return jsonify(_buscar_redes_decisor(schema, lead_id))


# --- Relatórios ---

@app.route('/api/<bot>/relatorios')
@login_required
def api_relatorios(bot):
    schema = _get_schema()
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
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500


# --- Sequências de Email ---

@app.route('/api/<bot>/sequencias')
@login_required
def api_list_sequencias(bot):
    schema = _get_schema()
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
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500


@app.route('/api/<bot>/sequencias', methods=['POST'])
@login_required
def api_create_sequencia(bot):
    ok, msg = _check_feature('sequencias')
    if not ok:
        return jsonify({'error': msg}), 403
    schema = _get_schema()
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
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500


@app.route('/api/<bot>/sequencia/<int:seq_id>', methods=['PUT'])
@login_required
def api_update_sequencia(bot, seq_id):
    schema = _get_schema()
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
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500


@app.route('/api/<bot>/sequencia/<int:seq_id>', methods=['DELETE'])
@login_required
def api_delete_sequencia(bot, seq_id):
    schema = _get_schema()
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute('DELETE FROM sequencias WHERE id = %s', (seq_id,))
        conn.commit()
        conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500


@app.route('/api/<bot>/sequencia/<int:seq_id>/enroll',
           methods=['POST'])
@login_required
def api_enroll_leads(bot, seq_id):
    schema = _get_schema()
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
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500


@app.route('/api/<bot>/sequencia/<int:seq_id>/leads')
@login_required
def api_sequencia_leads(bot, seq_id):
    schema = _get_schema()
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
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500


@app.route('/api/<bot>/sequencias/processar', methods=['POST'])
@login_required
def api_processar_sequencias(bot):
    ok, msg = _check_feature('sequencias')
    if not ok:
        return jsonify({'error': msg}), 403
    schema = _get_schema()
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
            seq_base_url = os.environ.get('BASE_URL', 'https://www.turbovenda.com.br')
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
                logger.error(f'seq: {e}')
                erros += 1
        conn.commit()
        conn.close()
        return jsonify({'ok': True,
                        'enviados': enviados, 'erros': erros})
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500


# --- CSV Export ---

@app.route('/api/<bot>/leads/export')
@login_required
def api_export_leads(bot):
    import io
    import csv
    schema = _get_schema()
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute("""SELECT e.nome_fantasia, e.cnpj, e.telefone, e.whatsapp, e.email,
                            e.website, e.cidade, e.estado, e.segmento, e.score, e.status,
                            e.situacao_cadastral,
                            e.observacoes, e.encontrado_em, e.email_enviado,
                            (SELECT ct.nome || ' - ' || ct.cargo
                             FROM contatos ct WHERE ct.empresa_id = e.id AND ct.decisor = 1
                             LIMIT 1) AS decisor,
                            (SELECT ct.linkedin FROM contatos ct
                             WHERE ct.empresa_id = e.id AND ct.decisor = 1
                             LIMIT 1) AS decisor_linkedin
                     FROM empresas e ORDER BY e.encontrado_em DESC""")
        rows = c.fetchall()
        conn.close()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Empresa', 'CNPJ', 'Telefone', 'WhatsApp', 'Email',
                         'Website', 'Cidade', 'Estado', 'Segmento', 'Score', 'Status',
                         'Situação', 'Observações', 'Encontrado em',
                         'Email enviado', 'Decisor', 'LinkedIn Decisor'])
        for r in rows:
            writer.writerow([r.get('nome_fantasia', ''), r.get('cnpj', ''),
                             _fmt_tel(r.get('telefone', '')),
                             _fmt_tel(r.get('whatsapp', '')),
                             r.get('email', ''), r.get('website', ''),
                             r.get('cidade', ''), r.get('estado', ''),
                             r.get('segmento', ''), r.get('score', ''),
                             r.get('status', ''),
                             r.get('situacao_cadastral', ''),
                             r.get('observacoes', ''),
                             str(r.get('encontrado_em') or ''),
                             str(r.get('email_enviado') or ''),
                             r.get('decisor', ''),
                             r.get('decisor_linkedin', '')])
        from flask import Response
        return Response(output.getvalue(),
                        mimetype='text/csv',
                        headers={'Content-Disposition': 'attachment;filename=leads.csv'})
    except Exception as e:
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500


# --- Bulk Actions ---

@app.route('/api/<bot>/leads/bulk', methods=['POST'])
@login_required
def api_bulk_action(bot):
    schema = _get_schema()
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
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500


# --- Email em massa ---

_SMTP_EXACT = {
    'gmail.com': ('smtp.gmail.com', 587),
    'googlemail.com': ('smtp.gmail.com', 587),
    'yahoo.com': ('smtp.mail.yahoo.com', 587),
    'yahoo.com.br': ('smtp.mail.yahoo.com', 587),
    'uol.com.br': ('smtps.uol.com.br', 587),
    'bol.com.br': ('smtps.bol.com.br', 587),
    'terra.com.br': ('smtp.terra.com.br', 587),
    'ig.com.br': ('smtp.ig.com.br', 587),
    'zoho.com': ('smtp.zoho.com', 587),
}
_SMTP_MICROSOFT = ('outlook', 'hotmail', 'live', 'msn')

def _detect_smtp(email: str) -> tuple:
    domain = email.rsplit('@', 1)[-1].lower() if '@' in email else ''
    if domain in _SMTP_EXACT:
        return _SMTP_EXACT[domain]
    base = domain.split('.')[0]
    if base in _SMTP_MICROSOFT:
        return ('smtp-mail.outlook.com', 587)
    if 'google' in domain:
        return ('smtp.gmail.com', 587)
    return (f'smtp.{domain}', 587)


def _get_email_config(schema: str) -> dict:
    """Config de envio. Ordem: OAuth > domínio próprio > SMTP > global."""
    cfg = get_bot_config(schema) if schema else {}
    user = get_current_user() or {}
    client_email = cfg.get('email_remetente') or ''
    client_password = cfg.get('smtp_password') or ''
    client_resend = cfg.get('resend_api_key') or ''
    nome_remetente = (cfg.get('email_remetente_nome')
                      or cfg.get('empresa_nome') or '')

    # 1. OAuth (Gmail/Outlook) — HTTPS, imune a bloqueio de porta SMTP
    provider = cfg.get('oauth_provider') or ''
    refresh = cfg.get('oauth_refresh_token') or ''
    oauth_email = cfg.get('oauth_email') or ''
    if provider and refresh and oauth_email:
        return {
            'sender_email': oauth_email,
            'sender_name': nome_remetente,
            'reply_to': '',
            'smtp_host': '', 'smtp_port': 587, 'smtp_user': '',
            'smtp_password': '', 'resend_api_key': '',
            'oauth_provider': provider, 'oauth_refresh_token': refresh,
            'compartilhado': False,
        }

    # 2. Domínio próprio verificado — envia pela Resend com o domínio do cliente
    dominio = cfg.get('dominio_proprio') or ''
    if dominio and cfg.get('dominio_verificado'):
        remetente = client_email
        if not remetente.endswith('@' + dominio):
            remetente = f'contato@{dominio}'
        return {
            'sender_email': remetente,
            'sender_name': nome_remetente,
            'reply_to': client_email if client_email != remetente else '',
            'smtp_host': '', 'smtp_port': 587, 'smtp_user': '',
            'smtp_password': '',
            'resend_api_key': os.environ.get('RESEND_API_KEY', '') or '',
            'oauth_provider': '', 'oauth_refresh_token': '',
            'compartilhado': False,
        }

    # 3. SMTP do cliente — só se o teste passou. Muitos hosts (Railway
    # incluso) bloqueiam saída SMTP; sem essa trava as campanhas
    # falhariam silenciosamente em vez de cair no remetente global.
    has_client_smtp = bool(client_email and client_password
                           and cfg.get('smtp_verificado'))
    if has_client_smtp:
        smtp_host, smtp_port = _detect_smtp(client_email)
        return {
            'sender_email': client_email,
            'sender_name': (cfg.get('email_remetente_nome') or
                            cfg.get('empresa_nome') or ''),
            'reply_to': '',
            'smtp_host': cfg.get('smtp_host') or smtp_host,
            'smtp_port': cfg.get('smtp_port') or smtp_port,
            'smtp_user': client_email,
            'smtp_password': client_password,
            'resend_api_key': '',
        }
    if client_resend and client_email:
        return {
            'sender_email': client_email,
            'sender_name': (cfg.get('email_remetente_nome') or
                            cfg.get('empresa_nome') or ''),
            'reply_to': '',
            'smtp_host': '', 'smtp_port': 587, 'smtp_user': '', 'smtp_password': '',
            'resend_api_key': client_resend,
        }
    return _email_config_global(
        nome_remetente, client_email or user.get('email') or '')


# =============================================================================
# ENVIO PELO EMAIL DO PROPRIO CLIENTE — OAuth (HTTPS, nao bloqueado) e dominio
# =============================================================================

_OAUTH = {
    'google': {
        'nome': 'Gmail',
        'client_id': os.environ.get('GOOGLE_CLIENT_ID', ''),
        'client_secret': os.environ.get('GOOGLE_CLIENT_SECRET', ''),
        'auth': 'https://accounts.google.com/o/oauth2/v2/auth',
        'token': 'https://oauth2.googleapis.com/token',
        'scope': ('https://www.googleapis.com/auth/gmail.send openid email'),
        'extra': {'access_type': 'offline', 'prompt': 'consent'},
    },
    'microsoft': {
        'nome': 'Outlook',
        'client_id': os.environ.get('MS_CLIENT_ID', ''),
        'client_secret': os.environ.get('MS_CLIENT_SECRET', ''),
        'auth': ('https://login.microsoftonline.com/common/oauth2/v2.0/'
                 'authorize'),
        'token': ('https://login.microsoftonline.com/common/oauth2/v2.0/'
                  'token'),
        'scope': 'offline_access Mail.Send User.Read',
        'extra': {'prompt': 'consent'},
    },
}


def _oauth_ativo(provider):
    p = _OAUTH.get(provider) or {}
    return bool(p.get('client_id') and p.get('client_secret'))


def _oauth_redirect_uri(provider):
    base = os.environ.get('BASE_URL', '').rstrip('/')
    if not base:
        base = request.host_url.rstrip('/').replace('http://', 'https://')
    return f'{base}/oauth/{provider}/callback'


def _oauth_troca_token(provider, dados):
    """Troca code/refresh_token por tokens. Devolve dict ou None."""
    p = _OAUTH.get(provider)
    if not p:
        return None
    try:
        import requests as http
        payload = dict(dados)
        payload.update({'client_id': p['client_id'],
                        'client_secret': p['client_secret']})
        r = http.post(p['token'], data=payload, timeout=15)
        if r.status_code != 200:
            logger.error('OAuth %s token %s: %s', provider, r.status_code,
                         r.text[:300])
            return None
        return r.json()
    except Exception:
        logger.exception('OAuth %s falha na troca de token', provider)
        return None


def _oauth_access_token(provider, refresh_token):
    """Access token novo a partir do refresh token."""
    d = _oauth_troca_token(provider, {
        'refresh_token': refresh_token, 'grant_type': 'refresh_token'})
    return (d or {}).get('access_token', '')


def _oauth_identidade(provider, access_token):
    """Descobre o email da conta autorizada."""
    try:
        import requests as http
        h = {'Authorization': f'Bearer {access_token}'}
        if provider == 'google':
            r = http.get('https://www.googleapis.com/oauth2/v2/userinfo',
                         headers=h, timeout=15)
            return (r.json() or {}).get('email', '') if r.ok else ''
        r = http.get('https://graph.microsoft.com/v1.0/me', headers=h,
                     timeout=15)
        if not r.ok:
            return ''
        j = r.json() or {}
        return j.get('mail') or j.get('userPrincipalName') or ''
    except Exception:
        logger.exception('OAuth %s falha ao ler identidade', provider)
        return ''


@app.route('/oauth/<provider>/start')
@login_required
def oauth_start(provider):
    if not _oauth_ativo(provider):
        return redirect('/configurar?email_erro=indisponivel')
    state = secrets.token_urlsafe(24)
    session['oauth_state'] = state
    session['oauth_provider'] = provider
    p = _OAUTH[provider]
    params = {
        'client_id': p['client_id'],
        'redirect_uri': _oauth_redirect_uri(provider),
        'response_type': 'code',
        'scope': p['scope'],
        'state': state,
    }
    params.update(p.get('extra') or {})
    from urllib.parse import urlencode
    return redirect(f"{p['auth']}?{urlencode(params)}")


@app.route('/oauth/<provider>/callback')
@login_required
def oauth_callback(provider):
    esperado = session.pop('oauth_state', None)
    session.pop('oauth_provider', None)
    recebido = request.args.get('state', '')
    if not esperado or not recebido or not _hmac.compare_digest(
            str(esperado), str(recebido)):
        return redirect('/configurar?email_erro=state')
    if request.args.get('error') or not request.args.get('code'):
        return redirect('/configurar?email_erro=negado')
    if not _oauth_ativo(provider):
        return redirect('/configurar?email_erro=indisponivel')

    tok = _oauth_troca_token(provider, {
        'code': request.args['code'],
        'grant_type': 'authorization_code',
        'redirect_uri': _oauth_redirect_uri(provider)})
    refresh = (tok or {}).get('refresh_token', '')
    access = (tok or {}).get('access_token', '')
    if not refresh:
        # sem refresh_token nao da pra enviar depois que o access expira
        return redirect('/configurar?email_erro=sem_refresh')

    email_conta = _oauth_identidade(provider, access)
    if not email_conta:
        return redirect('/configurar?email_erro=identidade')

    schema = _get_schema()
    try:
        with _conn(schema) as conn:
            with conn.cursor() as c:
                c.execute(
                    """UPDATE bot_config SET email_metodo=%s,
                       oauth_provider=%s, oauth_refresh_token=%s,
                       oauth_email=%s, atualizado_em=NOW()""",
                    (provider, provider, _encrypt_field(refresh),
                     email_conta))
            conn.commit()
    except Exception:
        logger.exception('falha ao salvar OAuth')
        return redirect('/configurar?email_erro=salvar')
    return redirect('/configurar?email_ok=' + provider)


@app.route('/api/<bot>/config/email/desconectar', methods=['POST'])
@login_required
def api_email_desconectar(bot):
    schema = _get_schema()
    try:
        with _conn(schema) as conn:
            with conn.cursor() as c:
                c.execute("""UPDATE bot_config SET email_metodo='global',
                             oauth_provider=NULL, oauth_refresh_token=NULL,
                             oauth_email=NULL, atualizado_em=NOW()""")
            conn.commit()
        return jsonify({'ok': True})
    except Exception:
        logger.exception('falha ao desconectar email')
        return jsonify({'ok': False, 'error': 'Erro interno'}), 500


def _send_oauth(provider, refresh_token, sender_email, sender_name,
                to_email, subject, html, reply_to=''):
    """Envia pela API do Gmail/Graph — HTTPS, nao sofre bloqueio de SMTP."""
    import base64
    from email.mime.text import MIMEText
    access = _oauth_access_token(provider, refresh_token)
    if not access:
        logger.error('OAuth %s: nao consegui access token', provider)
        return False
    try:
        import requests as http
        if provider == 'google':
            msg = MIMEText(html, 'html', 'utf-8')
            msg['To'] = to_email
            msg['From'] = (f'{sender_name} <{sender_email}>' if sender_name
                           else sender_email)
            msg['Subject'] = subject
            if reply_to:
                msg['Reply-To'] = reply_to
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            r = http.post(
                'https://gmail.googleapis.com/gmail/v1/users/me/messages/send',
                headers={'Authorization': f'Bearer {access}'},
                json={'raw': raw}, timeout=20)
        else:
            corpo = {
                'message': {
                    'subject': subject,
                    'body': {'contentType': 'HTML', 'content': html},
                    'toRecipients': [
                        {'emailAddress': {'address': to_email}}],
                },
                'saveToSentItems': True,
            }
            if reply_to:
                corpo['message']['replyTo'] = [
                    {'emailAddress': {'address': reply_to}}]
            r = http.post('https://graph.microsoft.com/v1.0/me/sendMail',
                          headers={'Authorization': f'Bearer {access}'},
                          json=corpo, timeout=20)
        if r.status_code in (200, 201, 202):
            logger.info('OAuth %s OK -> %s', provider, to_email)
            return True
        logger.error('OAuth %s erro %s: %s', provider, r.status_code,
                     r.text[:300])
    except Exception:
        logger.exception('OAuth %s falha no envio', provider)
    return False


# ── Dominio proprio via Resend ────────────────────────────────────────────

def _resend_admin():
    return os.environ.get('RESEND_API_KEY', '')


_PROVEDOR_PESSOAL = {
    'gmail.com': 'google', 'googlemail.com': 'google',
    'outlook.com': 'microsoft', 'hotmail.com': 'microsoft',
    'live.com': 'microsoft', 'msn.com': 'microsoft',
    'yahoo.com': 'outro', 'yahoo.com.br': 'outro',
    'uol.com.br': 'outro', 'bol.com.br': 'outro', 'terra.com.br': 'outro',
    'ig.com.br': 'outro', 'globo.com': 'outro', 'icloud.com': 'outro',
}


@lru_cache(maxsize=512)
def _mx_provider(dominio):
    """Onde o email desse domínio está hospedado, pelo MX.

    Metade dos domínios de empresa no Brasil usa Microsoft 365 ou Google
    Workspace. Nesses casos o OAuth envia do endereço real do cliente sem
    tocar em DNS — sem essa checagem eles cairiam no caminho de SPF/DKIM
    à toa. Consulta por DNS-over-HTTPS porque UDP/53 costuma ser bloqueado.
    """
    try:
        import requests as http
        r = http.get('https://cloudflare-dns.com/dns-query',
                     params={'name': dominio, 'type': 'MX'},
                     headers={'Accept': 'application/dns-json'}, timeout=8)
        if not r.ok:
            return ''
        alvos = ' '.join(a.get('data', '').lower()
                         for a in (r.json().get('Answer') or []))
        if 'google' in alvos or 'googlemail' in alvos:
            return 'google'
        if 'outlook' in alvos or 'microsoft' in alvos:
            return 'microsoft'
    except Exception:
        logger.info('MX de %s indisponivel', dominio)
    return ''


def _classificar_email(email):
    """Descobre sozinho qual caminho de envio serve para este endereço."""
    dominio = email.rsplit('@', 1)[-1].lower().strip() if '@' in email else ''
    if not dominio:
        return {'tipo': 'invalido', 'dominio': ''}
    if dominio in _PROVEDOR_PESSOAL:
        prov = _PROVEDOR_PESSOAL[dominio]
    else:
        base = dominio.split('.')[0]
        if base in _SMTP_MICROSOFT:
            prov = 'microsoft'
        elif 'google' in dominio:
            prov = 'google'
        else:
            # domínio da empresa: se o email dele mora no Google/Microsoft,
            # OAuth resolve sem DNS nenhum
            prov = _mx_provider(dominio)
    if prov in ('google', 'microsoft'):
        return {'tipo': 'oauth', 'provider': prov, 'dominio': dominio,
                'empresarial': dominio not in _PROVEDOR_PESSOAL,
                'disponivel': _oauth_ativo(prov)}
    if prov == 'outro':
        # provedor pessoal sem OAuth nosso — só resta o remetente global
        return {'tipo': 'pessoal', 'dominio': dominio}
    return {'tipo': 'dominio', 'dominio': dominio}


def _resend_criar_dominio(dominio):
    """Registra o domínio na Resend. Devolve (id, registros, erro)."""
    key = _resend_admin()
    if not key:
        return None, [], 'indisponivel'
    try:
        import requests as http
        h = {'Authorization': f'Bearer {key}'}
        r = http.post('https://api.resend.com/domains', headers=h,
                      json={'name': dominio}, timeout=20)
        j = r.json() if r.content else {}
        if r.status_code in (200, 201):
            return j.get('id'), j.get('records') or [], None
        # já cadastrado antes: recupera em vez de falhar
        lst = http.get('https://api.resend.com/domains', headers=h, timeout=20)
        for d in (lst.json() or {}).get('data', []) if lst.ok else []:
            if d.get('name') == dominio:
                det = http.get(f"https://api.resend.com/domains/{d['id']}",
                               headers=h, timeout=20)
                dj = det.json() if det.ok else {}
                return d['id'], dj.get('records') or [], None
        return None, [], (j.get('message') or 'falha ao registrar')
    except Exception:
        logger.exception('resend: erro ao criar dominio')
        return None, [], 'erro interno'


@app.route('/api/<bot>/config/email/auto', methods=['POST'])
@login_required
@limiter.limit("10 per minute")
def api_email_auto(bot):
    """Cliente informa nome + email; o resto é decidido aqui."""
    schema = _get_schema()
    data = request.get_json(silent=True) or {}
    nome = (data.get('nome') or '').strip()[:120]
    email = (data.get('email') or '').strip().lower()
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[a-z]{2,}', email or ''):
        return jsonify({'ok': False, 'error': 'Informe um email válido'}), 400

    info = _classificar_email(email)
    dom_id, registros, erro_dom = None, [], None
    if info['tipo'] == 'dominio':
        dom_id, registros, erro_dom = _resend_criar_dominio(info['dominio'])

    try:
        with _conn(schema) as conn:
            with conn.cursor() as c:
                c.execute("""UPDATE bot_config SET email_remetente=%s,
                             email_remetente_nome=%s, atualizado_em=NOW()""",
                          (email, nome or None))
                if dom_id:
                    c.execute("""UPDATE bot_config SET dominio_proprio=%s,
                                 dominio_id=%s""", (info['dominio'], dom_id))
            conn.commit()
    except Exception:
        logger.exception('falha ao salvar email do remetente')
        return jsonify({'ok': False, 'error': 'Erro interno'}), 500

    resp = {'ok': True, 'tipo': info['tipo'], 'dominio': info['dominio'],
            'registros': registros}
    if info['tipo'] == 'oauth':
        resp['provider'] = info['provider']
        resp['disponivel'] = info['disponivel']
        resp['empresarial'] = info.get('empresarial', False)
    if erro_dom:
        resp['aviso_dominio'] = erro_dom
    return jsonify(resp)


@app.route('/api/<bot>/config/dominio', methods=['POST'])
@login_required
@limiter.limit("5 per minute")
def api_dominio_criar(bot):
    """Registra o dominio do cliente na Resend e devolve os registros DNS."""
    schema = _get_schema()
    data = request.get_json(silent=True) or {}
    dominio = (data.get('dominio') or '').strip().lower()
    dominio = re.sub(r'^https?://', '', dominio).strip('/')
    dominio = dominio.split('/')[0]
    if not re.fullmatch(r'[a-z0-9.-]+\.[a-z]{2,}', dominio or ''):
        return jsonify({'ok': False, 'error': 'Domínio inválido'}), 400
    key = _resend_admin()
    if not key:
        return jsonify({'ok': False,
                        'error': 'Envio por domínio indisponível'}), 503
    try:
        import requests as http
        r = http.post('https://api.resend.com/domains',
                      headers={'Authorization': f'Bearer {key}'},
                      json={'name': dominio}, timeout=20)
        j = r.json() if r.content else {}
        if r.status_code not in (200, 201):
            return jsonify({'ok': False, 'error':
                            j.get('message') or 'Falha ao registrar domínio'
                            }), 400
        with _conn(schema) as conn:
            with conn.cursor() as c:
                c.execute("""UPDATE bot_config SET dominio_proprio=%s,
                             dominio_id=%s, dominio_verificado=FALSE,
                             atualizado_em=NOW()""", (dominio, j.get('id')))
            conn.commit()
        return jsonify({'ok': True, 'dominio': dominio,
                        'registros': j.get('records') or []})
    except Exception:
        logger.exception('falha ao criar dominio')
        return jsonify({'ok': False, 'error': 'Erro interno'}), 500


@app.route('/api/<bot>/config/dominio/verificar', methods=['POST'])
@login_required
@limiter.limit("10 per minute")
def api_dominio_verificar(bot):
    """Pede verificacao do DNS e grava o resultado."""
    schema = _get_schema()
    cfg = get_bot_config(schema) or {}
    dom_id = cfg.get('dominio_id')
    key = _resend_admin()
    if not dom_id or not key:
        return jsonify({'ok': False,
                        'error': 'Cadastre o domínio primeiro'}), 400
    try:
        import requests as http
        h = {'Authorization': f'Bearer {key}'}
        http.post(f'https://api.resend.com/domains/{dom_id}/verify',
                  headers=h, timeout=20)
        r = http.get(f'https://api.resend.com/domains/{dom_id}', headers=h,
                     timeout=20)
        j = r.json() if r.content else {}
        verificado = (j.get('status') == 'verified')
        with _conn(schema) as conn:
            with conn.cursor() as c:
                c.execute("""UPDATE bot_config SET dominio_verificado=%s,
                             email_metodo=CASE WHEN %s THEN 'dominio'
                             ELSE email_metodo END, atualizado_em=NOW()""",
                          (verificado, verificado))
            conn.commit()
        return jsonify({'ok': True, 'verificado': verificado,
                        'status': j.get('status'),
                        'registros': j.get('records') or []})
    except Exception:
        logger.exception('falha ao verificar dominio')
        return jsonify({'ok': False, 'error': 'Erro interno'}), 500


def _send_email(ecfg, to_email, to_name, subject, html):
    """Envia via OAuth do cliente, Resend ou SMTP — nessa ordem."""
    provider = ecfg.get('oauth_provider', '')
    refresh = ecfg.get('oauth_refresh_token', '')
    if provider and refresh:
        ok = _send_oauth(provider, refresh, ecfg.get('sender_email', ''),
                         ecfg.get('sender_name', ''), to_email, subject,
                         html, ecfg.get('reply_to', ''))
        if ok:
            return True
        logger.warning('OAuth falhou, caindo para o remetente global')
        ecfg = dict(ecfg, **_email_config_global(ecfg.get('sender_name', ''),
                                                 ecfg.get('sender_email', '')))
    return _send_email_classico(ecfg, to_email, to_name, subject, html)


# Teto diário por cliente no remetente COMPARTILHADO. Todos os clientes sem
# domínio/OAuth próprio dividem a reputação de um mesmo domínio — sem teto,
# um cliente sozinho manda o email de todos os outros para o spam.
LIMITE_DIARIO_COMPARTILHADO = {
    'trial': 30, 'starter': 150, 'pro': 400, 'enterprise': 800,
}


def _emails_hoje(schema):
    """Quantos emails este cliente já disparou hoje."""
    try:
        with _conn(schema) as conn:
            with conn.cursor() as c:
                c.execute('SELECT COUNT(*) AS n FROM empresas '
                          'WHERE email_enviado::date = CURRENT_DATE')
                row = c.fetchone()
                return (row['n'] if row else 0) or 0
    except Exception:
        logger.exception('falha ao contar envios do dia')
        return 0


def _email_config_global(sender_name='', reply_to=''):
    """Remetente do TurboVenda, com resposta indo pro email do cliente."""
    return {
        'compartilhado': True,
        'sender_email': os.environ.get('EMAIL_FROM',
                                       'contato@turbovenda.com.br'),
        'sender_name': sender_name,
        'reply_to': reply_to,
        'smtp_host': '', 'smtp_port': 587, 'smtp_user': '',
        'smtp_password': '',
        'resend_api_key': os.environ.get('RESEND_API_KEY', '') or '',
        'oauth_provider': '', 'oauth_refresh_token': '',
    }


def _send_email_classico(ecfg, to_email, to_name, subject, html):
    """Envia via Resend API (prioridade) ou SMTP direto."""
    sender_email = ecfg.get('sender_email', '')
    sender_name = ecfg.get('sender_name', '')
    logger.info(f'to={to_email} from={sender_email}')
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
                logger.info(f'Resend OK enviado para {to_email}')
                return True
            else:
                logger.error(f'Resend erro {r.status_code}: {r.text}')
        except Exception as e:
            logger.error(f'Resend erro: {e}')

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
                        import socket as _sk
                        _i = _sk.getaddrinfo(smtp_host, p, _sk.AF_INET,
                                             _sk.SOCK_STREAM)[0][4]
                        with smtplib.SMTP_SSL(_i[0], p, timeout=15) as s:
                            s._host = smtp_host
                            s.login(smtp_user, smtp_pass)
                            s.sendmail(sender_email, to_email, msg.as_string())
                    else:
                        # IPv4 explícito: ver comentário em _smtp_conectar
                        with _smtp_conectar(smtp_host, p, timeout=15) as s:
                            s.ehlo()
                            s.starttls()
                            s.login(smtp_user, smtp_pass)
                            s.sendmail(sender_email, to_email, msg.as_string())
                    logger.info(f'SMTP OK porta {p}')
                    return True
                except Exception as e:
                    logger.error(f'SMTP porta {p} erro: {e}')
                    continue
        except Exception as e:
            logger.error(f'SMTP erro geral: {e}')

    logger.error('nenhum metodo de envio disponivel')
    return False


@app.route('/api/<bot>/send-emails', methods=['POST'])
@login_required
def api_send_emails(bot):
    schema = _get_schema()
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

    # Teto só no remetente compartilhado: quem envia pelo próprio domínio
    # ou pela própria conta responde pela reputação dele, não pela de todos.
    if ecfg.get('compartilhado'):
        teto = LIMITE_DIARIO_COMPARTILHADO.get(_get_user_plano(), 30)
        ja = _emails_hoje(schema)
        se_restam = teto - ja
        if se_restam <= 0:
            return jsonify({'error':
                            f'Você já enviou {ja} emails hoje, o limite do '
                            f'remetente compartilhado. Configure o email da '
                            f'sua empresa em Configurações para enviar sem '
                            f'esse teto — ele existe para proteger a entrega '
                            f'de todos os clientes.'}), 429
        if len(leads) > se_restam:
            cortados = len(leads) - se_restam
            leads = leads[:se_restam]
        else:
            cortados = 0
    else:
        cortados = 0

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
            logger.error(f'send-emails erro lead {lead["id"]}: {e}')
            erros += 1
    resp = {'ok': True, 'enviados': enviados, 'erros': erros}
    if cortados:
        resp['aviso'] = (
            f'{cortados} lead(s) ficaram para amanhã: você atingiu o limite '
            f'diário do remetente compartilhado. Configure o email da sua '
            f'empresa em Configurações para enviar sem esse teto.')
    return jsonify(resp)


@app.route('/api/<bot>/email/campanha', methods=['POST'])
@login_required
def api_email_campanha(bot):
    ok, msg = _check_feature('email_massa')
    if not ok:
        return jsonify({'error': msg}), 403
    schema = _get_schema()
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
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500

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
            logger.error(f'campanha erro lead {lead["id"]}: {e}')
            erros += 1
    return jsonify({'ok': True, 'enviados': enviados, 'erros': erros})


# --- Config do bot ---

@app.route('/api/<bot>/config', methods=['GET'])
@login_required
def api_get_config(bot):
    schema = _get_schema()
    cfg = get_bot_config(schema)
    # Não retorna senha do LinkedIn
    cfg.pop('linkedin_password', None)
    return jsonify(cfg)


@app.route('/api/<bot>/config/test-email', methods=['POST'])
@login_required
@limiter.limit("3 per minute")
def api_test_email(bot):
    """Testa envio de email com as configs do cliente."""
    schema = _get_schema()
    data = request.get_json(silent=True) or {}
    email = data.get('email', '').strip()
    password = data.get('password', '').strip()
    if not email or not password:
        return jsonify({'ok': False, 'error': 'Preencha email e senha'}), 400
    smtp_host, smtp_port = _detect_smtp(email)
    import smtplib
    # Sonda as portas ANTES do handshake. Se a hospedagem bloqueia, isso
    # responde em segundos em vez de gastar o timeout inteiro do SMTP e
    # estourar o limite do navegador.
    if _smtp_bloqueado(smtp_host):
        _set_smtp_verificado(schema, False)
        logger.warning('SMTP bloqueado pelo host (%s)', smtp_host)
        return jsonify({
            'ok': False, 'bloqueado': True, 'error':
            'Nosso servidor não consegue enviar direto pelo seu provedor '
            '(a hospedagem bloqueia esse tipo de conexão). Sem problema: '
            'suas campanhas saem pelo TurboVenda com o seu nome, e as '
            'respostas chegam normalmente no seu email.'}), 200
    try:
        from email.mime.text import MIMEText
        msg = MIMEText('Este é um email de teste do TurboVenda. Se você recebeu, a configuração está correta!', 'plain', 'utf-8')
        msg['From'] = f'TurboVenda Teste <{email}>'
        msg['To'] = email
        msg['Subject'] = 'TurboVenda — Teste de email OK'
        server = _smtp_conectar(smtp_host, smtp_port, timeout=8)
        server.starttls()
        server.login(email, password)
        server.sendmail(email, [email], msg.as_string())
        server.quit()
        _set_smtp_verificado(schema, True)
        return jsonify({'ok': True,
                        'msg': f'Email de teste enviado para {email}',
                        'smtp_host': smtp_host})
    except smtplib.SMTPAuthenticationError:
        _set_smtp_verificado(schema, False)
        return jsonify({'ok': False, 'bloqueado': False, 'error':
                        'Senha incorreta ou acesso não autorizado. '
                        'Para Gmail, use uma Senha de App.'}), 400
    except Exception as e:
        # A porta abre (sondamos antes), então aqui é problema de credencial
        # ou do próprio provedor — não bloqueio da hospedagem.
        _set_smtp_verificado(schema, False)
        logger.warning('SMTP %s:%s falhou: %s', smtp_host, smtp_port, e)
        return jsonify({'ok': False, 'bloqueado': False, 'error':
                        f'Não consegui enviar por {smtp_host}. '
                        f'Confira o email e a senha. ({e})'}), 400


def _set_smtp_verificado(schema, valor):
    """Marca se o SMTP do cliente foi testado com sucesso."""
    if not schema:
        return
    try:
        with _conn(schema) as conn:
            with conn.cursor() as c:
                c.execute('UPDATE bot_config SET smtp_verificado = %s',
                          (valor,))
            conn.commit()
    except Exception:
        logger.exception('falha ao gravar smtp_verificado')


def _smtp_conectar(host, port, timeout=8):
    """Conecta forçando IPv4.

    'Network is unreachable' num container costuma ser o resolver
    devolvendo AAAA sem haver rota IPv6 — o que parece bloqueio da
    hospedagem e não é. Resolvemos o A na mão e mantemos o hostname
    para o certificado do STARTTLS bater.
    """
    import smtplib
    import socket
    infos = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
    if not infos:
        raise OSError(f'sem registro A para {host}')
    ultimo = None
    for info in infos:
        ip = info[4][0]
        try:
            s = smtplib.SMTP(ip, port, timeout=timeout)
            s._host = host  # SNI/cert usam o nome, não o IP
            return s
        except OSError as e:
            ultimo = e
    raise ultimo or OSError('falha ao conectar')


@app.route('/api/<bot>/config/smtp-diag')
@login_required
@limiter.limit("4 per minute")
def api_smtp_diag(bot):
    """Diz se o host realmente bloqueia SMTP ou se era só IPv6."""
    import socket
    host = request.args.get('host', 'smtp-mail.outlook.com')
    if not re.fullmatch(r'[a-z0-9.-]+', host.lower() or ''):
        return jsonify({'error': 'host inválido'}), 400
    out = {'host': host, 'ipv4': [], 'ipv6': [], 'portas': {}}
    for fam, chave in ((socket.AF_INET, 'ipv4'), (socket.AF_INET6, 'ipv6')):
        try:
            out[chave] = sorted({i[4][0] for i in socket.getaddrinfo(
                host, 587, fam, socket.SOCK_STREAM)})
        except Exception as e:
            out[chave] = [f'erro: {e}']
    for porta in (587, 465, 25):
        r = {}
        for fam, chave in ((socket.AF_INET, 'v4'), (socket.AF_INET6, 'v6')):
            try:
                infos = socket.getaddrinfo(host, porta, fam,
                                           socket.SOCK_STREAM)
                with socket.create_connection(infos[0][4], 4):
                    r[chave] = 'abriu'
            except Exception as e:
                r[chave] = f'{type(e).__name__}: {e}'
        out['portas'][porta] = r
    abriu_v4 = any(v.get('v4') == 'abriu' for v in out['portas'].values())
    out['veredito'] = ('SMTP funciona por IPv4 — o erro anterior era IPv6'
                       if abriu_v4 else
                       'A hospedagem bloqueia mesmo a saída SMTP')
    return jsonify(out)


def _smtp_bloqueado(host, portas=(587, 465, 25), timeout=3):
    """True se nenhuma porta SMTP abre — indica bloqueio da hospedagem."""
    import socket
    for porta in portas:
        try:
            infos = socket.getaddrinfo(host, porta, socket.AF_INET,
                                       socket.SOCK_STREAM)
            with socket.create_connection(infos[0][4], timeout):
                return False
        except OSError:
            continue
    return True


@app.route('/api/<bot>/config', methods=['POST'])
@login_required
def api_save_config(bot):
    schema = _get_schema()
    data = request.get_json(silent=True) or {}
    empresa_nome = data.get('empresa_nome', '')
    website = data.get('website', '')
    descricao = data.get('descricao', '')
    termos = data.get('termos_busca') or None  # None = não alterar
    estados_atuacao = data.get('estados_atuacao') or []
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
    brave_api_key = data.get('brave_api_key', '')
    google_cse_key = data.get('google_cse_key', '')
    google_cse_cx = data.get('google_cse_cx', '')

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
        logger.info(f'save_config/{schema}: Iniciando save...')
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
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS smtp_verificado BOOLEAN DEFAULT FALSE",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS segmentos_evitar JSONB DEFAULT '[]'",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS email_metodo TEXT DEFAULT 'global'",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS oauth_provider TEXT",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS oauth_refresh_token TEXT",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS oauth_email TEXT",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS dominio_proprio TEXT",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS dominio_id TEXT",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS dominio_verificado BOOLEAN DEFAULT FALSE",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS serper_api_key TEXT",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS brave_api_key TEXT",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS google_cse_key TEXT",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS google_cse_cx TEXT",
            "ALTER TABLE bot_config ADD COLUMN IF NOT EXISTS estados_atuacao JSONB DEFAULT '[]'",
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
                         descricao=%s, termos_busca=%s, estados_atuacao=%s,
                         linkedin_email=%s,
                         linkedin_cargos=%s, msg_inicial=%s,
                         email_assunto_padrao=%s, email_html_template=%s,
                         email_remetente=%s, email_remetente_nome=%s,
                         email_cor_header=%s, email_cor_botao=%s, email_cor_texto=%s,
                         resend_api_key=%s,
                         smtp_host=%s, smtp_port=%s,
                         smtp_user=%s, smtp_password=%s,
                         smtp_verificado=%s,
                         serper_api_key=%s, brave_api_key=%s,
                         google_cse_key=%s, google_cse_cx=%s,
                         atualizado_em=NOW()"""
            params = [empresa_nome, website, descricao, psycopg2.extras.Json(termos),
                      psycopg2.extras.Json(estados_atuacao),
                      li_email or None, psycopg2.extras.Json(li_cargos),
                      msg_inicial or None, email_assunto or None,
                      email_html or None,
                      email_remetente or None,
                      email_remetente_nome or None,
                      email_cor_header or '#1a2332',
                      email_cor_botao or '#2563eb',
                      email_cor_texto or '#ffffff',
                      _encrypt_field(resend_api_key) if resend_api_key else exists.get('resend_api_key'),
                      smtp_host or exists.get('smtp_host'),
                      smtp_port or exists.get('smtp_port') or 587,
                      smtp_user or exists.get('smtp_user'),
                      _encrypt_field(smtp_password) if smtp_password else exists.get('smtp_password'),
                      # trocou email ou senha -> precisa testar de novo
                      (bool(exists.get('smtp_verificado'))
                       and not smtp_password
                       and (email_remetente or None) == exists.get('email_remetente')),
                      _encrypt_field(serper_api_key) if serper_api_key else exists.get('serper_api_key'),
                      _encrypt_field(brave_api_key) if brave_api_key else exists.get('brave_api_key'),
                      _encrypt_field(google_cse_key) if google_cse_key else exists.get('google_cse_key'),
                      google_cse_cx or exists.get('google_cse_cx')]
            if li_password:
                sql += ", linkedin_password=%s"
                params.append(_encrypt_field(li_password))
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
                       _encrypt_field(li_password) or None,
                       psycopg2.extras.Json(li_cargos),
                       msg_inicial or None, email_assunto or None,
                       email_html or None,
                       email_remetente or None,
                       email_remetente_nome or None,
                       _encrypt_field(resend_api_key) or None,
                       smtp_host or None, smtp_port or 587,
                       smtp_user or None,
                       _encrypt_field(smtp_password) or None))
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

        logger.info(f'save_config/{schema}: OK - salvou {len(termos)} termos')
        return jsonify({'ok': True, 'redirect': '/dashboard', 'termos': termos})
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f'save_config/{schema}: {e}')
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


# =============================================================================
# GERACAO POR IA (Claude) — copy de prospeccao e ICP
# =============================================================================

_AI_KEY = (os.environ.get('ANTHROPIC_API_KEY', '')
           or os.environ.get('CLAUDE_API_KEY', '')
           or os.environ.get('ANTHROPIC_KEY', ''))
_AI_MODEL = os.environ.get('AI_MODEL', 'claude-sonnet-5')
_AI_FALLBACK = 'claude-haiku-4-5-20251001'


def _ai_json(prompt: str, max_tokens: int = 1000):
    """Chama Claude e devolve o JSON da resposta. None se indisponivel."""
    if not _AI_KEY:
        logger.info('IA desativada: nenhuma API key da Anthropic definida')
        return None
    modelos = [_AI_MODEL] + ([_AI_FALLBACK] if _AI_MODEL != _AI_FALLBACK
                             else [])
    for modelo in modelos:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=_AI_KEY, timeout=30.0)
            # thinking desligado: o Sonnet 5 raciocina por padrão e gastava
            # o orçamento inteiro pensando (stop_reason=max_tokens, zero
            # blocos de texto), então o JSON voltava vazio e tudo caía no
            # gerador heurístico. Copy curta não precisa de raciocínio.
            kwargs = {'model': modelo, 'max_tokens': max_tokens,
                      'messages': [{'role': 'user', 'content': prompt}]}
            try:
                resp = client.messages.create(
                    thinking={'type': 'disabled'}, **kwargs)
            except TypeError:
                resp = client.messages.create(**kwargs)
            txt = ''.join(b.text for b in resp.content
                          if getattr(b, 'type', '') == 'text').strip()
            m = re.search(r'\{.*\}', txt, re.S)
            if m:
                return json.loads(m.group(0))
            logger.warning('IA (%s) nao devolveu JSON', modelo)
        except Exception as e:
            logger.warning('IA falhou (%s): %s', modelo, e)
    return None


_REGRAS_COPY = """Regras de escrita:
- Portugues do Brasil, tom profissional, direto e humano.
- Frases curtas e SEMPRE completas — nunca corte uma frase no meio.
- PROIBIDO: "revolucionario", "inovador", "solucao completa", "parceiro
  estrategico", "alavancar", "potencializar", "sinergia", "excelencia".
- Nunca invente fato que nao esteja na descricao. Sem promessa vaga.
- Se a descricao citar numero, norma ou certificacao concreta, use."""


def _ai_copy(empresa: str, descricao: str, website: str = '') -> dict:
    """Gera copy de prospeccao. Dict vazio se IA indisponivel."""
    return dict(_ai_copy_cached(empresa.strip(), descricao.strip(),
                                (website or '').strip()))


@lru_cache(maxsize=128)
def _ai_copy_cached(empresa: str, descricao: str, website: str = '') -> tuple:
    """Cache do copy — onboarding chama generate-msg e generate-email."""
    return tuple(_ai_copy_uncached(empresa, descricao, website).items())


def _ai_copy_uncached(empresa: str, descricao: str, website: str = '') -> dict:
    if not descricao.strip():
        return {}
    prompt = f"""Voce e copywriter B2B senior. Escreva copy de prospeccao fria.

EMPRESA REMETENTE: {empresa}
O QUE ELA FAZ (descricao escrita pelo proprio dono):
{descricao}
SITE: {website or 'nao informado'}

{_REGRAS_COPY}

A variavel {{{{nome}}}} e o nome da empresa QUE VAI RECEBER a mensagem.

Responda SO com este JSON, sem texto antes ou depois:
{{
  "pitch": "1 frase completa, ate 130 caracteres, dizendo o que a {empresa} faz e o ganho concreto pro cliente. NAO cite o nome da {empresa}. Nao termine com virgula.",
  "whatsapp": "WhatsApp de primeiro contato, ate 320 caracteres. Comece com 'Oi {{{{nome}}}}, tudo bem?'. Diga que voce e da {empresa}, o que ela faz, e termine perguntando se pode mostrar em 15 min. Sem link. No maximo 1 emoji.",
  "whatsapp_followup": "Follow-up curto, ate 220 caracteres, com {{{{nome}}}}. Retoma o contato anterior sem cobrar. Sem link.",
  "assunto": "Assunto de email, ate 55 caracteres, contendo {{{{nome}}}}. Especifico, sem clickbait.",
  "email_intro": "1 frase de abertura do email, vem logo apos 'Ola {{{{nome}}}},'. Ate 150 caracteres. Diz quem voce e e por que escreveu. NAO use as variaveis segmento nem cidade."
}}"""
    d = _ai_json(prompt, max_tokens=900) or {}
    out = {}
    for k in ('pitch', 'whatsapp', 'whatsapp_followup',
              'assunto', 'email_intro'):
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            out[k] = v.strip().rstrip(' ,;:')
    return out


def _ai_icp(empresa: str, descricao: str) -> dict:
    """Gera segmentos-alvo e cargos do ICP. Dict vazio se IA indisponivel."""
    if not descricao.strip():
        return {}
    prompt = f"""Voce e especialista em prospeccao B2B no Brasil.

EMPRESA: {empresa}
O QUE ELA VENDE:
{descricao}

Liste o ICP dela — que TIPOS DE EMPRESA ela deve prospectar como cliente.

Regras para "segmentos":
- Sao termos que aparecem no nome ou na descricao de empresas reais no Google.
- Substantivo do tipo de empresa, minusculo, SEM cidade e SEM estado.
- Bons: "construtora", "industria metalurgica", "cooperativa agricola",
  "frigorifico", "usina de acucar", "fabrica de embalagens".
- Ruins: "empresas de medio porte", "clientes do Sul", "industria em geral".
- De 8 a 14 itens, do mais provavel para o menos provavel.

Regras para "cargos": 6 a 10 cargos de quem decide a compra, sem acento.

Regras para "evitar" — CRITICO:
- Palavras que denunciam um CONCORRENTE dela, nao um cliente.
- Se a {empresa} e uma consultoria de qualidade, entao "consultoria",
  "assessoria", "certificadora", "auditoria" sao concorrentes — nunca
  clientes. Quem vende software nao prospecta software house.
- Inclua tambem o proprio ramo dela e sinonimos.
- De 4 a 10 palavras, minusculas, sem acento.

Responda SO com este JSON:
{{"segmentos": ["..."], "cargos": ["..."], "evitar": ["..."]}}"""
    d = _ai_json(prompt, max_tokens=800) or {}
    segs = [s.strip().lower() for s in (d.get('segmentos') or [])
            if isinstance(s, str) and 3 < len(s.strip()) < 40]
    cargos = [c.strip().title() for c in (d.get('cargos') or [])
              if isinstance(c, str) and 3 < len(c.strip()) < 40]
    evitar = [e.strip().lower() for e in (d.get('evitar') or [])
              if isinstance(e, str) and 2 < len(e.strip()) < 40]
    # nunca deixa um termo a evitar virar segmento-alvo
    segs = [s for s in segs if not any(e in s for e in evitar)]
    if not segs:
        return {}
    return {'segmentos': list(dict.fromkeys(segs)),
            'cargos': list(dict.fromkeys(cargos)),
            'evitar': list(dict.fromkeys(evitar))}


@app.route('/api/<bot>/config/ia-status')
@login_required
@limiter.limit("6 per minute")
def api_ia_status(bot):
    """Diz se a IA está mesmo respondendo — sem isso a queda pro gerador
    heurístico é silenciosa e o cliente só vê 'o texto está ruim'."""
    if not _AI_KEY:
        return jsonify({
            'ativa': False,
            'motivo': 'O servidor não tem a chave da Anthropic configurada '
                      '(ANTHROPIC_API_KEY).'})
    if _ai_json('Responda somente com este JSON: {"ok": true}',
                max_tokens=32):
        return jsonify({'ativa': True, 'modelo': _AI_MODEL})
    return jsonify({
        'ativa': False,
        'motivo': f'A chave existe, mas a chamada ao modelo {_AI_MODEL} '
                  f'falhou. Veja o log do servidor.'})


@app.route('/api/<bot>/config/generate-terms', methods=['POST'])
@login_required
def api_generate_terms(bot):
    data = request.get_json(silent=True) or {}
    result = _gerar_termos(
        data.get('empresa_nome', ''),
        data.get('descricao', ''),
        data.get('website', ''),
        data.get('estados') or []
    )
    schema = _get_schema()
    evitar = result.get('evitar') or []
    if schema and evitar:
        try:
            with _conn(schema) as conn:
                with conn.cursor() as c:
                    c.execute('UPDATE bot_config SET segmentos_evitar=%s',
                              (psycopg2.extras.Json(evitar),))
                conn.commit()
        except Exception:
            logger.exception('falha ao salvar segmentos_evitar')
    return jsonify({'ok': True, 'termos': result['termos'],
                    'cargos': result['cargos'], 'evitar': evitar})


def _gerar_termos(empresa_nome: str, descricao: str, website: str, estados_selecionados: list = None) -> dict:
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

    _UF_REGIAO = {
        'PR': 'sul', 'SC': 'sul', 'RS': 'sul',
        'GO': 'centro-oeste', 'MT': 'centro-oeste', 'MS': 'centro-oeste', 'DF': 'centro-oeste',
        'SP': 'sudeste', 'MG': 'sudeste', 'RJ': 'sudeste', 'ES': 'sudeste',
        'BA': 'nordeste', 'PE': 'nordeste', 'CE': 'nordeste', 'MA': 'nordeste',
        'RN': 'nordeste', 'PB': 'nordeste', 'SE': 'nordeste', 'AL': 'nordeste', 'PI': 'nordeste',
        'AM': 'norte', 'PA': 'norte', 'TO': 'norte', 'RO': 'norte',
        'AC': 'norte', 'RR': 'norte', 'AP': 'norte',
    }

    if estados_selecionados:
        regioes_match = list({_UF_REGIAO[uf] for uf in estados_selecionados if uf in _UF_REGIAO})
        estados = list(estados_selecionados)
    else:
        regioes_match = []
        for regiao in TODAS_CIDADES:
            if re.search(r'\b' + re.escape(regiao) + r'\b', desc_lower):
                regioes_match.append(regiao)
        for uf, reg in _UF_REGIAO.items():
            if re.search(r'\b' + uf + r'\b', descricao):
                if reg not in regioes_match:
                    regioes_match.append(reg)
        if not regioes_match:
            regioes_match = list(TODAS_CIDADES.keys())
        estados = []
        for reg in regioes_match:
            estados.extend(ESTADOS_POR_REGIAO.get(reg, []))
        estados = list(dict.fromkeys(estados))

    cidades = []
    for reg in regioes_match:
        cidades.extend(TODAS_CIDADES.get(reg, []))
    cidades = list(dict.fromkeys(cidades))

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

    # ── 3.5 IA: substitui segmentos/cargos heuristicos quando disponivel ──
    _icp = _ai_icp(empresa_nome, descricao)
    evitar = _icp.get('evitar') or []
    if _icp.get('segmentos'):
        segmentos = _icp['segmentos']
    if _icp.get('cargos'):
        cargos = list(dict.fromkeys(_icp['cargos'] + cargos_base))
    # Sem isso, "A X é uma consultoria..." fazia "consultoria" virar
    # segmento-alvo e a busca trazia os concorrentes do cliente.
    if evitar:
        segmentos = [s for s in segmentos
                     if not any(e in s.lower() for e in evitar)]

    if not segmentos:
        segmentos = ['industria', 'distribuidora', 'construtora',
                     'cooperativa', 'transportadora']
    if not cidades:
        cidades = ['Brasil']

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
    return {'termos': lista, 'cargos': cargos, 'evitar': evitar}






# --- API Tokens ---

@app.route('/api/<bot>/tokens', methods=['GET'])
@login_required
def api_list_tokens(bot):
    uid = session.get('user_id')
    conn = None
    try:
        conn = _conn()
        c = conn.cursor()
        c.execute("""SELECT id, label, ativo, criado_em,
                            '••••' || RIGHT(token, 6) AS token_preview
                     FROM api_tokens WHERE user_id = %s ORDER BY criado_em DESC""", (uid,))
        rows = [dict(r) for r in c.fetchall()]
        return jsonify(rows)
    except Exception as e:
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


@app.route('/api/<bot>/tokens', methods=['POST'])
@login_required
def api_create_token(bot):
    ok, msg = _check_feature('api_tokens')
    if not ok:
        return jsonify({'error': msg}), 403
    uid = session.get('user_id')
    data = request.get_json(silent=True) or {}
    label = data.get('label', 'Token API')
    token = secrets.token_urlsafe(32)
    conn = None
    try:
        conn = _conn()
        c = conn.cursor()
        c.execute('INSERT INTO api_tokens (user_id, token, label) VALUES (%s,%s,%s) RETURNING id',
                  (uid, token, label))
        tid = c.fetchone()['id']
        conn.commit()
        return jsonify({'ok': True, 'id': tid, 'token': token,
                        'aviso': 'Salve este token — não será exibido novamente'})
    except Exception as e:
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


@app.route('/api/<bot>/tokens/<int:token_id>', methods=['DELETE'])
@login_required
def api_revoke_token(bot, token_id):
    uid = session.get('user_id')
    conn = None
    try:
        conn = _conn()
        c = conn.cursor()
        c.execute('UPDATE api_tokens SET ativo=FALSE WHERE id=%s AND user_id=%s', (token_id, uid))
        conn.commit()
        return jsonify({'ok': True})
    except Exception as e:
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


# =============================================================================
# API PÚBLICA — Bearer token
# =============================================================================

@app.route('/api/v1/leads', methods=['GET'])
@token_required
def public_list_leads():
    schema = request.token_user['schema_name']
    page = request.args.get('page', 1, type=int)
    per_page = max(1, min(request.args.get('per_page', 50, type=int), 200))
    offset = (max(1, page) - 1) * per_page
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
        sql += ' ORDER BY encontrado_em DESC LIMIT %s OFFSET %s'
        params.extend([per_page, offset])
        c.execute(sql, params)
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return jsonify({'leads': rows, 'total': len(rows),
                        'page': page, 'per_page': per_page})
    except Exception as e:
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500


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
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500


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
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500


# =============================================================================
# AGENDA (Calendário interno)
# =============================================================================

@app.route('/api/<bot>/agenda')
@login_required
def api_agenda(bot):
    schema = _get_schema()
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
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500


@app.route('/api/<bot>/agenda', methods=['POST'])
@login_required
def api_add_evento(bot):
    schema = _get_schema()
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
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500


@app.route('/api/<bot>/agenda/<int:evento_id>', methods=['PUT'])
@login_required
def api_update_evento(bot, evento_id):
    schema = _get_schema()
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
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500


@app.route('/api/<bot>/agenda/<int:evento_id>', methods=['DELETE'])
@login_required
def api_delete_evento(bot, evento_id):
    schema = _get_schema()
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute('DELETE FROM agenda WHERE id = %s', (evento_id,))
        conn.commit()
        conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500


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

    tipo = data.get('tipo', 'whatsapp')

    site_link = ''
    if website:
        url = website if website.startswith('http') else f'https://{website}'
        site_link = '\n\n🔗 ' + url

    ia = _ai_copy(empresa, descricao, website)
    link_var = '{{link_agenda}}' if tipo == 'followup' else '{{cal_link}}'
    texto_ia = ia.get('whatsapp_followup' if tipo == 'followup'
                      else 'whatsapp')

    if texto_ia:
        mensagem = texto_ia + '\n\n' + link_var + site_link
    else:
        pitch = _extrair_pitch(descricao, empresa, max_chars=100)
        if tipo == 'followup':
            mensagem = (
                "{{nome}}, tudo bem? Te mandei uma mensagem recentemente.\n\n"
                "Sou da " + empresa + ". " + pitch + ".\n\n"
                "Teria 15 min para uma conversa rápida?\n"
                + link_var + site_link
            )
        else:
            mensagem = (
                "Oi {{nome}}, tudo bem? 👋\n\n"
                "Sou da " + empresa + ". " + pitch + ".\n\n"
                "Posso te mostrar em 15 min como funciona na prática?\n"
                + link_var + site_link
            )

    return jsonify({'ok': True, 'mensagem': mensagem, 'ia': bool(texto_ia)})


@app.route('/api/<bot>/config/generate-email', methods=['POST'])
@login_required
def api_generate_email(bot):
    data = request.get_json(silent=True) or {}
    empresa = data.get('empresa_nome', '') or 'Sua Empresa'
    descricao = data.get('descricao', '')
    website = data.get('website', '').strip()
    if not descricao:
        return jsonify({'error': 'Preencha a descrição da empresa'}), 400

    ia = _ai_copy(empresa, descricao, website)
    pitch = ia.get('pitch') or _extrair_pitch(descricao, empresa, max_chars=150)
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

    intro = ia.get('email_intro') or ''
    html = _build_email_html(
        empresa=empresa, pitch=pitch, cor_header=cor_header,
        cor_btn=cor_btn, cor_texto=cor_texto,
        site_link_inline=site_link_inline, site_footer=site_footer,
        site_url=site_url, intro=intro)

    assunto = ia.get('assunto') or '{{nome}}, posso te mostrar algo?'
    return jsonify({'ok': True, 'html': html, 'assunto': assunto,
                    'ia': bool(ia)})


def _build_email_html(*, empresa, pitch, cor_header, cor_btn, cor_texto,
                      site_link_inline, site_footer, site_url, intro=''):
    """Monta o HTML profissional do email de prospecção."""
    site_display = site_url.replace("https://", "").replace("http://", "").rstrip("/") if site_url else ''

    if intro:
        intro_txt = (intro.replace('&', '&amp;').replace('<', '&lt;')
                     .replace('>', '&gt;'))
    else:
        intro_txt = ('Sou da <strong>' + empresa + '</strong>' + site_link_inline
                     + ' e estou entrando em contato para apresentar '
                     'rapidamente o que fazemos.')

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
{intro_txt}
</p>
</td></tr>

<!-- PITCH CARD -->
<tr><td style="background-color:#ffffff;padding:24px 48px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
       style="background-color:{btn_bg};border-left:4px solid {cor_btn};border-radius:0 8px 8px 0;">
<tr><td style="padding:20px 24px;">
<p style="margin:0;font-family:Segoe UI,Arial,sans-serif;font-size:14px;line-height:1.7;color:#1e293b;">
<strong style="font-size:15px;">Sobre a {empresa}:</strong><br>
{pitch}.
</p>
</td></tr>
</table>
</td></tr>

<!-- CTA TEXT -->
<tr><td style="background-color:#ffffff;padding:0 48px 28px;">
<p style="margin:0;font-family:Segoe UI,Arial,sans-serif;font-size:15px;line-height:1.75;color:#374151;">
Teria <strong>15 minutos</strong> para uma conversa rápida? Posso te mostrar como funciona na prática.
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


def _polir_final(t):
    """Remove sobra pendurada no fim da frase (infinitivo, preposição)."""
    ant = None
    while t != ant:
        ant = t
        t = t.strip().rstrip(' ,;:.')
        # "...construtoras a implantar" -> "...construtoras"
        t = re.sub(r'\s+(?:a|para|de|em|com)\s+\w+(?:ar|er|ir)$', '', t,
                   flags=re.IGNORECASE)
        # preposição/conjunção solta no fim
        t = re.sub(r'\s+(?:e|ou|de|da|do|das|dos|em|para|a|o|que|com|'
                   r'na|no|nas|nos)$', '', t, flags=re.IGNORECASE)
    return t


def _cortar_frase(p, limite):
    """Corta em fronteira de oração — nunca no meio de uma ideia."""
    p = p.strip().rstrip(' ,;:.')
    if len(p) <= limite:
        return _polir_final(p) if p.endswith((' a', ' de', ' e')) else p
    corte = p[:limite]
    minimo = limite * 0.35

    cand = ''
    if ',' in corte:
        c = corte.rsplit(',', 1)[0].strip()
        if len(c) >= minimo:
            cand = c

    if not cand:
        melhor = -1
        for con in (' que ', ' para ', ' com ', ' e ', ' a '):
            idx = corte.rfind(con)
            if idx > melhor:
                melhor = idx
        if melhor >= minimo:
            cand = corte[:melhor]

    if not cand:
        cand = corte.rsplit(' ', 1)[0]

    return _polir_final(cand)


def _extrair_pitch(descricao, empresa_nome='', max_chars=150):
    """Extrai a frase de PRODUTO/SERVIÇO da descrição para usar em mensagens."""
    _REJEITAR = [
        'nosso cliente', 'cliente ideal', 'público-alvo', 'publico-alvo',
        'atendemos', 'atuamos', 'foco em', 'focamos',
        'pequeno porte', 'médio porte', 'grande porte',
        'centro-oeste', 'sul do brasil', 'norte do brasil',
    ]
    _PRODUTO = [
        'vendemos', 'fabricamos', 'produzimos', 'oferecemos',
        'desenvolvemos', 'fornecemos', 'trabalhamos com',
        'somos', 'é uma', 'é um',
    ]
    _BENEFICIO = [
        'produtividade', 'economia', 'reduz', 'aumenta', 'controle',
        'proteg', 'seguran', 'resultado', 'otimiz', 'eficiên',
        'automatiz', 'agilidade', 'evita', 'elimin',
        'garante', 'melhora', 'simplifica', 'acelera', 'monitora',
        'permite', 'ajuda', 'facilita',
    ]

    frases = re.split(r'(?<=[.!?])\s+', descricao.strip())
    frases = [f.rstrip('.').strip() for f in frases if len(f.strip()) > 10]
    if not frases:
        return descricao[:max_chars]

    def _limpar(frase):
        p = frase
        # "A AndersTech é uma consultoria..." -> "consultoria..."
        # exige artigo depois do verbo, pra não confundir "é" com "e" conjunção
        p = re.sub(r'^(?:O|A)\s+(?:\S+\s+){1,3}?(?:é|e|eh)\s+(?:um|uma)\s+',
                    '', p, flags=re.IGNORECASE)
        # "A AndersTech ajuda ..." -> "ajuda ..." (verbo sem ambiguidade)
        p = re.sub(r'^(?:O|A)\s+(?:\S+\s+){1,3}?'
                    r'(?:é|permite|ajuda|oferece|fornece|atua|desenvolve)\s+',
                    '', p, flags=re.IGNORECASE)
        p = re.sub(r'^(?:O objetivo [eé]|A meta [eé]|O foco [eé]|Nosso objetivo [eé]|Nós)\s+',
                    '', p, flags=re.IGNORECASE)
        p = re.sub(r'^O sistema\s+', '', p, flags=re.IGNORECASE)
        p = re.sub(r'^(?:Vendemos|Fabricamos|Produzimos|Oferecemos|Desenvolvemos|Fornecemos)\s+',
                    '', p, flags=re.IGNORECASE)
        p = re.sub(r'^Somos\s+(?:uma?\s+)?', '', p, flags=re.IGNORECASE)
        if p:
            p = p[0].upper() + p[1:]
        return _cortar_frase(p, max_chars)

    def _rejeitada(frase):
        fl = frase.lower()
        return any(r in fl for r in _REJEITAR)

    for frase in reversed(frases):
        fl = frase.lower()
        if not _rejeitada(frase) and any(b in fl for b in _BENEFICIO):
            return _limpar(frase)

    for frase in frases:
        fl = frase.lower()
        if not _rejeitada(frase) and any(p in fl for p in _PRODUTO):
            return _limpar(frase)

    for frase in frases:
        if not _rejeitada(frase):
            return _limpar(frase)

    return _limpar(frases[0])


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
# LGPD — DIREITOS DO TITULAR (Art. 18)
# =============================================================================

@app.route('/api/meus-dados/exportar', methods=['GET'])
@login_required
def api_exportar_dados():
    """Exporta todos os dados pessoais do usuario (LGPD Art. 18)."""
    uid = session.get('user_id')
    schema = _get_schema()
    dados = {'usuario': {}, 'leads': [], 'contatos': [], 'config': {}, 'pagamentos': []}
    conn = None
    try:
        conn = _conn()
        c = conn.cursor()
        c.execute('SELECT id, email, empresa_nome, website, plano, plano_expira, criado_em FROM users WHERE id = %s', (uid,))
        user = c.fetchone()
        if user:
            dados['usuario'] = _serialize_row(dict(user))
        c.execute('SELECT * FROM pagamentos WHERE user_id = %s ORDER BY criado_em DESC', (uid,))
        dados['pagamentos'] = [_serialize_row(dict(r)) for r in c.fetchall()]
    except Exception:
        logger.exception('Erro ao exportar dados publicos')
    finally:
        if conn:
            conn.close()
    conn2 = None
    try:
        conn2 = _conn(schema)
        c2 = conn2.cursor()
        c2.execute('SELECT * FROM empresas ORDER BY id')
        dados['leads'] = [_serialize_row(dict(r)) for r in c2.fetchall()]
        c2.execute('SELECT * FROM contatos ORDER BY id')
        dados['contatos'] = [_serialize_row(dict(r)) for r in c2.fetchall()]
        c2.execute('SELECT empresa_nome, website, descricao, termos_busca, email_remetente, email_remetente_nome FROM bot_config LIMIT 1')
        cfg = c2.fetchone()
        if cfg:
            dados['config'] = _serialize_row(dict(cfg))
    except Exception:
        logger.exception('Erro ao exportar dados do schema')
    finally:
        if conn2:
            conn2.close()
    resp = make_response(json.dumps(dados, ensure_ascii=False, indent=2, default=str))
    resp.headers['Content-Type'] = 'application/json; charset=utf-8'
    resp.headers['Content-Disposition'] = f'attachment; filename=turbovenda_dados_{uid}.json'
    return resp


@app.route('/api/meus-dados/excluir', methods=['POST'])
@limiter.limit("3 per hour")
@login_required
def api_excluir_dados():
    """Exclui conta e todos os dados pessoais (LGPD Art. 18 - direito ao esquecimento)."""
    uid = session.get('user_id')
    schema = _get_schema()
    conn = None
    try:
        conn = _conn()
        c = conn.cursor()
        c.execute(psql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(psql.Identifier(schema)))
        c.execute('DELETE FROM pagamentos WHERE user_id = %s', (uid,))
        c.execute('DELETE FROM api_tokens WHERE user_id = %s', (uid,))
        c.execute('DELETE FROM users WHERE id = %s', (uid,))
        conn.commit()
        logger.info(f'LGPD: usuario {uid} excluido com sucesso')
    except Exception:
        logger.exception(f'Erro ao excluir dados do usuario {uid}')
        if conn:
            conn.rollback()
        return jsonify({'error': 'Erro ao excluir dados. Contate suporte@turbovenda.com.br'}), 500
    finally:
        if conn:
            conn.close()
    session.clear()
    return jsonify({'ok': True, 'msg': 'Conta e dados excluidos com sucesso.'})


# =============================================================================
# HEALTH
# =============================================================================

@app.route('/health')
def health():
    try:
        conn = _conn()
        try:
            c = conn.cursor()
            c.execute('SELECT 1')
        finally:
            conn.close()
        return jsonify({'status': 'ok', 'version': '2.1', 'db': 'ok'})
    except Exception as e:
        return jsonify({'status': 'degraded', 'version': '2.1', 'db': str(e)}), 503


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
    conn = None
    try:
        conn = psycopg2.connect(
            DATABASE_URL,
            cursor_factory=psycopg2.extras.RealDictCursor)
        c = conn.cursor()
        c.execute('SELECT id, schema_name FROM users')
        users = c.fetchall()
        conn.close()
        conn = None
        for u in users:
            sch = u.get('schema_name')
            if not sch:
                continue
            conn2 = None
            try:
                conn2 = _conn(sch)
                c2 = conn2.cursor()
                c2.execute(
                    'SELECT id FROM empresas WHERE email_track_token=%s',
                    (token,))
                row = c2.fetchone()
                if row:
                    return sch, row['id']
            except Exception:
                pass
            finally:
                if conn2:
                    try:
                        conn2.close()
                    except Exception:
                        pass
    except Exception:
        pass
    finally:
        if conn:
            try:
                conn.close()
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
@login_required
def email_track_test():
    """Diagnóstico do tracking — protegido, só admin/logado vê."""
    base = os.environ.get('BASE_URL', request.host_url.rstrip('/'))
    base_https = base.replace('http://', 'https://')
    return jsonify({
        'ok': True,
        'base_url_final': base_https,
        'pixel_example': f'{base_https}/t/TEST_TOKEN/open.png',
        'scheme': request.scheme,
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
            logger.error(f'track/open: {e}')
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
    # Anti-open-redirect: só permitir URLs internas ou do próprio domínio
    parsed = _urlparse(redirect_url)
    if parsed.netloc and parsed.netloc not in ('turbovenda.com.br', request.host):
        redirect_url = '/'
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
            logger.error(f'track/click: {e}')
    return redirect(redirect_url)


@app.route('/webhook/email', methods=['POST'])
def webhook_email():
    """Webhook do Resend para eventos de email (bounce, complaint, etc)."""
    # Verificar assinatura do Resend (svix-signature)
    # Fail-closed: se RESEND_WEBHOOK_SECRET nao estiver configurado, rejeita
    resend_wh_secret = os.environ.get('RESEND_WEBHOOK_SECRET', '')
    if not resend_wh_secret:
        logger.warning("[EMAIL] RESEND_WEBHOOK_SECRET nao configurado — webhook rejeitado")
        return jsonify({'error': 'webhook not configured'}), 403
    svix_sig = request.headers.get('svix-signature', '')
    svix_ts = request.headers.get('svix-timestamp', '')
    svix_id = request.headers.get('svix-id', '')
    if not svix_sig or not svix_ts:
        return jsonify({'error': 'missing signature'}), 401
    body = request.get_data(as_text=True)
    to_sign = f'{svix_id}.{svix_ts}.{body}'
    import base64
    secret_bytes = base64.b64decode(resend_wh_secret.split('_')[-1]
                                    if '_' in resend_wh_secret
                                    else resend_wh_secret)
    sig = base64.b64encode(
        _hmac.new(secret_bytes, to_sign.encode(), 'sha256').digest()
    ).decode()
    sigs = [s.split(',')[-1] for s in svix_sig.split(' ')]
    if not any(_hmac.compare_digest(sig, s) for s in sigs):
        logger.error('Webhook assinatura invalida')
        return jsonify({'error': 'invalid signature'}), 401

    data = request.get_json(silent=True) or {}
    event_type = data.get('type', '')
    payload = data.get('data', {})
    to_email = ''
    if isinstance(payload.get('to'), list) and payload['to']:
        to_email = payload['to'][0]
    elif isinstance(payload.get('to'), str):
        to_email = payload['to']
    logger.info(f'webhook {event_type} to={to_email}')
    if event_type in ('email.bounced', 'email.complained'):
        conn = None
        try:
            conn = psycopg2.connect(
                DATABASE_URL,
                cursor_factory=psycopg2.extras.RealDictCursor)
            c = conn.cursor()
            c.execute('SELECT id, schema_name FROM users')
            users = c.fetchall()
            conn.close()
            conn = None
            for u in users:
                sch = u.get('schema_name')
                if not sch:
                    continue
                conn2 = None
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
                        break
                except Exception:
                    pass
                finally:
                    if conn2:
                        try:
                            conn2.close()
                        except Exception:
                            pass
        except Exception as e:
            logger.error(f'webhook erro: {e}')
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
    return jsonify({'ok': True})


def _busca_ddg(query, num=10):
    """Busca gratuita via DuckDuckGo HTML (sem API key). Mesmo formato
    de resultado do Serper: [{'link','title','snippet'}]."""
    import requests as http
    import html as _html
    import urllib.parse as _up
    try:
        r = http.get(
            'https://html.duckduckgo.com/html/',
            params={'q': query, 'kl': 'br-pt'},
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; '
                     'x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                     'Chrome/120.0 Safari/537.36'},
            timeout=15)
        if r.status_code != 200:
            return []
        txt = r.text
    except Exception:
        return []
    results = []
    for m in re.finditer(
            r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            txt, re.S):
        href = m.group(1)
        title = re.sub(r'<[^>]+>', '', m.group(2)).strip()
        if 'uddg=' in href:
            mm = re.search(r'uddg=([^&]+)', href)
            if mm:
                try:
                    href = _up.unquote(mm.group(1))
                except Exception:
                    pass
        results.append({'link': _html.unescape(href),
                        'title': _html.unescape(title), 'snippet': ''})
        if len(results) >= num:
            break
    snips = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', txt, re.S)
    for i, s in enumerate(snips):
        if i < len(results):
            results[i]['snippet'] = _html.unescape(
                re.sub(r'<[^>]+>', '', s).strip())
    return results


def _busca_brave(schema, query, num=10):
    """Busca via Brave Search API. Grátis 2k/mês. Chave do Config
    (brave_api_key) ou env BRAVE_API_KEY."""
    import requests as http
    key = ''
    try:
        key = (get_bot_config(schema) or {}).get('brave_api_key') or ''
    except Exception:
        key = ''
    key = key or os.environ.get('BRAVE_API_KEY', '')
    if not key:
        return []
    try:
        r = http.get(
            'https://api.search.brave.com/res/v1/web/search',
            headers={'X-Subscription-Token': key,
                     'Accept': 'application/json'},
            params={'q': query, 'country': 'br', 'count': num},
            timeout=15)
        if r.status_code != 200:
            return []
        web = (r.json().get('web') or {}).get('results') or []
        return [{'link': it.get('url', ''), 'title': it.get('title', ''),
                 'snippet': it.get('description', '')} for it in web]
    except Exception:
        return []


def _busca_google_cse(schema, query, num=10):
    """Busca via Google Custom Search JSON API. Grátis 100/dia, sem cartão.
    Chave/cx do Config ou env GOOGLE_CSE_KEY / GOOGLE_CSE_CX."""
    import requests as http
    key = cx = ''
    try:
        cfg = get_bot_config(schema) or {}
        key = cfg.get('google_cse_key') or ''
        cx = cfg.get('google_cse_cx') or ''
    except Exception:
        key = cx = ''
    key = key or os.environ.get('GOOGLE_CSE_KEY', '')
    cx = cx or os.environ.get('GOOGLE_CSE_CX', '')
    if not key or not cx:
        return []
    try:
        r = http.get(
            'https://www.googleapis.com/customsearch/v1',
            params={'key': key, 'cx': cx, 'q': query, 'gl': 'br',
                    'num': min(num, 10)},
            timeout=15)
        if r.status_code != 200:
            return []
        items = r.json().get('items') or []
        return [{'link': it.get('link', ''), 'title': it.get('title', ''),
                 'snippet': it.get('snippet', '')} for it in items]
    except Exception:
        return []


def _busca_serper(schema, query, num=10):
    """Busca via Serper.dev. Chave do Config ou env SERPER_API_KEY."""
    import requests as http
    key = ''
    try:
        key = (get_bot_config(schema) or {}).get('serper_api_key') or ''
    except Exception:
        key = ''
    key = key or os.environ.get('SERPER_API_KEY', '')
    if not key:
        return []
    try:
        r = http.post(
            'https://google.serper.dev/search',
            headers={'X-API-KEY': key, 'Content-Type': 'application/json'},
            json={'q': query, 'gl': 'br', 'hl': 'pt-br', 'num': num},
            timeout=15)
        if r.status_code != 200:
            return []
        return [{'link': it.get('link', ''), 'title': it.get('title', ''),
                 'snippet': it.get('snippet', '')}
                for it in (r.json().get('organic') or [])]
    except Exception:
        return []


def _serper_search(schema, query, num=10):
    """Busca web multi-provedor (tudo automático no servidor). Tenta, em
    ordem, os provedores configurados por ENV/Config e cai no DuckDuckGo
    como último recurso. Retorna {'ok', 'results', 'fonte'}.
    Basta UMA chave no ambiente: BRAVE_API_KEY (recomendado, grátis) ou
    SERPER_API_KEY ou GOOGLE_CSE_KEY+GOOGLE_CSE_CX."""
    provedores = [
        ('serper', lambda: _busca_serper(schema, query, num)),
        ('brave', lambda: _busca_brave(schema, query, num)),
        ('google_cse', lambda: _busca_google_cse(schema, query, num)),
        ('duckduckgo', lambda: _busca_ddg(query, num)),
    ]
    for fonte, fn in provedores:
        try:
            res = fn()
        except Exception:
            res = []
        if res:
            return {'ok': True, 'results': res, 'fonte': fonte}
    return {'ok': False, 'sem_provedor': True,
            'error': 'Busca não configurada: em Config → "Busca automática" '
                     'preencha o Google (grátis, sem cartão) ou o Brave para '
                     'descobrir CNPJ automaticamente.',
            'results': []}


_CNPJ_RE = re.compile(r'\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}')
# Termos genéricos ignorados na conferência de nome
_NOME_STOP = {
    'LTDA', 'ME', 'EPP', 'EIRELI', 'SA', 'S', 'A', 'CIA', 'LIMITADA',
    'EMPRESA', 'GRUPO', 'COMERCIO', 'COMERCIAL', 'INDUSTRIA', 'INDUSTRIAL',
    'IND', 'COM', 'SERVICOS', 'SERVICO', 'E', 'DE', 'DA', 'DO', 'DAS',
    'DOS', 'EM', 'DISTRIBUIDORA', 'REPRESENTACOES', 'EIRELLI',
}


def _cnpj_valido(d):
    """Valida os dígitos verificadores do CNPJ (garante que não é lixo)."""
    if len(d) != 14 or len(set(d)) == 1:
        return False
    w1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    w2 = [6] + w1
    s1 = sum(int(d[i]) * w1[i] for i in range(12))
    r1 = s1 % 11
    dv1 = 0 if r1 < 2 else 11 - r1
    if dv1 != int(d[12]):
        return False
    s2 = sum(int(d[i]) * w2[i] for i in range(13))
    r2 = s2 % 11
    dv2 = 0 if r2 < 2 else 11 - r2
    return dv2 == int(d[13])


def _tokens_nome(s):
    import unicodedata
    s = (s or '').upper()
    s = ''.join(ch for ch in unicodedata.normalize('NFKD', s)
                if not unicodedata.combining(ch))
    s = re.sub(r'[^A-Z0-9 ]', ' ', s)
    return [t for t in s.split() if len(t) > 1 and t not in _NOME_STOP]


def _nome_confere(nome_lead, *oficiais):
    """True se o nome do lead bate com a razão social/fantasia da Receita."""
    t_lead = set(_tokens_nome(nome_lead))
    if not t_lead:
        return False
    minimo = max(1, round(len(t_lead) * 0.5))
    for of in oficiais:
        t_of = set(_tokens_nome(of))
        if t_of and len(t_lead & t_of) >= minimo:
            return True
    return False


def _descobrir_cnpj(schema, lead_id):
    """Descobre o CNPJ do lead via Serper e VALIDA antes de salvar:
    1) dígito verificador do CNPJ; 2) nome confere com a Receita."""
    import time
    import requests as http
    conn = _conn(schema)
    c = conn.cursor()
    c.execute('SELECT nome_fantasia, razao_social, cidade, estado, cnpj '
              'FROM empresas WHERE id=%s', (lead_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return {'ok': False, 'error': 'Lead não encontrado'}
    if row.get('cnpj'):
        conn.close()
        return {'ok': True, 'cnpj': row['cnpj'], 'ja_tinha': True}
    nome = row.get('nome_fantasia') or row.get('razao_social') or ''
    if not nome:
        conn.close()
        return {'ok': False, 'error': 'Lead sem nome'}
    cidade = row.get('cidade') or ''
    local = ' '.join(x for x in [cidade, row.get('estado')] if x)
    conn.close()
    res = _serper_search(schema, f'{nome} {local} CNPJ'.strip(), num=10)
    if not res['ok']:
        return res
    # 1) Coleta candidatos com dígito verificador válido (ordem dos results)
    candidatos = []
    for item in res['results']:
        blob = ' '.join([item.get('title', ''), item.get('snippet', ''),
                         item.get('link', '')])
        for m in _CNPJ_RE.finditer(blob):
            digits = ''.join(ch for ch in m.group(0) if ch.isdigit())
            if len(digits) == 14 and _cnpj_valido(digits) \
                    and digits not in candidatos:
                candidatos.append(digits)
    if not candidatos:
        return {'ok': False, 'error': 'Nenhum CNPJ válido encontrado na busca'}
    # 2) Valida nome contra a Receita (BrasilAPI) — só salva se conferir
    sugerido = None
    for digits in candidatos[:6]:
        try:
            rr = http.get(
                f'https://brasilapi.com.br/api/cnpj/v1/{digits}', timeout=10)
            if rr.status_code != 200:
                time.sleep(0.3)
                continue
            dd = rr.json()
        except Exception:
            continue
        cidade_ok = (not cidade) or (
            (dd.get('municipio') or '').upper().strip()
            == cidade.upper().strip())
        if _nome_confere(nome, dd.get('razao_social'),
                         dd.get('nome_fantasia')) and cidade_ok:
            cnpj_fmt = (f'{digits[:2]}.{digits[2:5]}.{digits[5:8]}/'
                        f'{digits[8:12]}-{digits[12:]}')
            conn = _conn(schema)
            c = conn.cursor()
            try:
                c.execute('UPDATE empresas SET cnpj=%s WHERE id=%s',
                          (cnpj_fmt, lead_id))
                conn.commit()
                conn.close()
                return {'ok': True, 'cnpj': cnpj_fmt,
                        'validado': True,
                        'razao_social': dd.get('razao_social')}
            except Exception:
                conn.rollback()
                conn.close()
                return {'ok': False, 'error': 'CNPJ já existe em outro lead'}
        if not sugerido:
            sugerido = (f'{digits[:2]}.{digits[2:5]}.{digits[5:8]}/'
                        f'{digits[8:12]}-{digits[12:]}')
        time.sleep(0.3)
    return {'ok': False,
            'error': 'CNPJ encontrado não confere com o nome — '
                     'revise manualmente',
            'cnpj_sugerido': sugerido}


def _enriquecer_cnpj(schema, lead_id):
    """Enriquece dados do lead via BrasilAPI (CNPJ)."""
    import requests as http
    try:
        conn = _conn(schema)
        c = conn.cursor()
        # Garante colunas que o enrich escreve (tenants antigos podem não ter)
        for stmt in (
            "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS razao_social TEXT",
            "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS natureza_juridica TEXT",
            "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS situacao_cadastral "
            "TEXT",
            "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS enriquecido BOOLEAN "
            "DEFAULT FALSE",
            "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS enriquecido_em "
            "TIMESTAMP",
            "ALTER TABLE contatos ADD COLUMN IF NOT EXISTS instagram TEXT",
            "ALTER TABLE contatos ADD COLUMN IF NOT EXISTS fonte TEXT",
        ):
            try:
                c.execute(stmt)
                conn.commit()
            except Exception:
                conn.rollback()
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
        # Sócios (QSA) -> cadastra o sócio-administrador como decisor
        socio_nome = None
        qsa = d.get('qsa') or []
        if qsa:
            adm = next(
                (s for s in qsa
                 if 'ADMIN' in (s.get('qualificacao_socio') or '').upper()),
                None)
            socio = adm or qsa[0]
            socio_nome = (socio.get('nome_socio') or '').strip()
            cargo = (socio.get('qualificacao_socio') or 'Sócio').strip()
            if socio_nome:
                c.execute(
                    'SELECT id FROM contatos WHERE empresa_id=%s '
                    'AND decisor=1 LIMIT 1', (lead_id,))
                if not c.fetchone():
                    c.execute(
                        "INSERT INTO contatos "
                        "(empresa_id, nome, cargo, decisor, fonte) "
                        "VALUES (%s, %s, %s, 1, 'qsa')",
                        (lead_id, socio_nome, cargo))
        c.execute("""INSERT INTO atividades (empresa_id, tipo, descricao)
            VALUES (%s, 'enriquecimento', %s)""",
            (lead_id, f'CNPJ enriquecido: {razao} | {porte} | {situacao}'
             + (f' | Sócio: {socio_nome}' if socio_nome else '')))
        conn.commit()
        conn.close()
        return {'ok': True, 'razao_social': razao, 'porte': porte,
                'cidade': mun, 'estado': uf, 'situacao': situacao,
                'socio': socio_nome}
    except Exception as e:
        logger.exception('agendar'); return {'ok': False, 'error': 'Erro interno'}


def _get_link_agenda(schema, lead_id):
    """Retorna URL pública de agendamento para o lead."""
    token = _get_agenda_token(schema, lead_id)
    base = os.environ.get('BASE_URL', request.host_url.rstrip('/'))
    return f'{base}/agendar/{token}'


def _find_lead_by_token(token):
    """Busca lead e schema pelo token de agendamento."""
    if not DATABASE_URL or not token:
        return None, None
    conn = None
    try:
        conn = psycopg2.connect(
            DATABASE_URL,
            cursor_factory=psycopg2.extras.RealDictCursor)
        c = conn.cursor()
        c.execute('SELECT id, schema_name FROM users')
        users = c.fetchall()
        conn.close()
        conn = None
        for u in users:
            sch = u.get('schema_name')
            if not sch:
                continue
            conn2 = None
            try:
                conn2 = _conn(sch)
                c2 = conn2.cursor()
                c2.execute(
                    'SELECT * FROM empresas WHERE agenda_token=%s',
                    (token,))
                lead = c2.fetchone()
                if lead:
                    return dict(lead), sch
            except Exception:
                continue
            finally:
                if conn2:
                    try:
                        conn2.close()
                    except Exception:
                        pass
    except Exception:
        pass
    finally:
        if conn:
            try:
                conn.close()
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
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500


@app.route('/api/<bot>/lead/<int:lead_id>/link-agenda')
@login_required
def api_lead_link_agenda(bot, lead_id):
    """Retorna link de agendamento para um lead específico."""
    schema = _get_schema()
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
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500


@app.route('/webhook/mercadopago', methods=['POST'])
@limiter.limit("30 per minute")
def webhook_mercadopago():
    """Webhook do Mercado Pago — atualiza plano do user."""
    import requests as http
    # Verificar assinatura do webhook (x-signature header do MP)
    # Fail-closed: se MP_WEBHOOK_SECRET nao estiver configurado, rejeita
    mp_webhook_secret = os.environ.get('MP_WEBHOOK_SECRET', '')
    if not mp_webhook_secret:
        logger.warning("[MP] MP_WEBHOOK_SECRET nao configurado — webhook rejeitado")
        return jsonify({'error': 'webhook not configured'}), 403
    x_sig = request.headers.get('x-signature', '')
    x_req_id = request.headers.get('x-request-id', '')
    # MP envia ts=xxx,v1=hash no x-signature
    sig_parts = dict(p.split('=', 1) for p in x_sig.split(',') if '=' in p)
    ts = sig_parts.get('ts', '')
    v1 = sig_parts.get('v1', '')
    data_id = request.args.get('data.id', request.args.get('id', ''))
    manifest = f'id:{data_id};request-id:{x_req_id};ts:{ts};'
    expected = _hmac.new(mp_webhook_secret.encode(), manifest.encode(),
                         'sha256').hexdigest()
    if not _hmac.compare_digest(v1, expected):
        logger.warning('MP webhook assinatura invalida')
        return jsonify({'error': 'invalid signature'}), 401

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

        conn = _conn()
        try:
            c = conn.cursor()

            c.execute("""INSERT INTO pagamentos
                (user_id, mp_payment_id, status, valor, plano)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (mp_payment_id) DO UPDATE SET status = EXCLUDED.status""",
                (user_id, str(payment_id), status, valor, plano))

            if status == 'approved':
                c.execute("""UPDATE users SET
                    plano = %s,
                    plano_expira = NOW() + INTERVAL '30 days',
                    mp_subscription_id = %s
                    WHERE id = %s""",
                    (plano, str(payment_id), user_id))
                logger.info(f'MP: user {user_id} -> plano {plano} (payment {payment_id})')

            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        logger.exception("Erro no webhook Mercado Pago")
        return jsonify({'error': 'internal'}), 500

    return jsonify({'ok': True})


@app.route('/api/pagamento/pix', methods=['POST'])
@limiter.limit("5 per minute")
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
                'X-Idempotency-Key': f"pix_{user['id']}_{plano_id}",
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
            conn = None
            try:
                conn = _conn()
                c = conn.cursor()
                c.execute("""INSERT INTO pagamentos
                    (user_id, mp_payment_id, status,
                     valor, plano)
                    VALUES (%s,%s,%s,%s,%s)
                    ON CONFLICT (mp_payment_id) DO UPDATE SET status = EXCLUDED.status""",
                    (user['id'], str(pay.get('id')),
                     pay.get('status'), plano['valor'],
                     plano_id))
                if pay.get('status') == 'approved':
                    c.execute("""UPDATE users SET
                        plano = %s,
                        plano_expira = NOW() + INTERVAL '30 days'
                        WHERE id = %s""",
                        (plano_id, user['id']))
                conn.commit()
            except Exception:
                logger.exception("Erro ao registrar pagamento PIX")
            finally:
                if conn:
                    try:
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
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500


@app.route('/api/pagamento/cartao', methods=['POST'])
@limiter.limit("5 per minute")
@login_required
def api_pagamento_cartao():
    """Processa pagamento com cartão via MP — recebe token gerado no frontend pelo MercadoPago.js."""
    import requests as http
    if not MP_ACCESS_TOKEN:
        return jsonify({'error': 'MP não configurado'}), 500
    data = request.get_json(silent=True) or {}
    plano_id = data.get('plano', 'pro')
    plano = MP_PLANOS.get(plano_id)
    if not plano:
        return jsonify({'error': 'Plano inválido'}), 400
    user = get_current_user()
    card_token = data.get('token', '').strip()
    payment_method = data.get('payment_method_id', 'visa')
    cpf = data.get('cpf', '').replace('.', '').replace('-', '')
    installments = data.get('installments', 1)
    if not card_token:
        return jsonify({'error': 'Token do cartão é obrigatório. Use MercadoPago.js para tokenizar no navegador.'}), 400
    if not cpf:
        return jsonify({'error': 'CPF é obrigatório'}), 400
    try:
        r = http.post(
            'https://api.mercadopago.com/v1/payments',
            headers={
                'Authorization': f'Bearer {MP_ACCESS_TOKEN}',
                'Content-Type': 'application/json',
                'X-Idempotency-Key': f"card_{user['id']}_{plano_id}",
            },
            json={
                'transaction_amount': plano['valor'],
                'token': card_token,
                'description': plano['nome'],
                'installments': installments,
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
        conn = None
        try:
            conn = _conn()
            c = conn.cursor()
            c.execute("""INSERT INTO pagamentos
                (user_id, mp_payment_id, status,
                 valor, plano)
                VALUES (%s,%s,%s,%s,%s)
                ON CONFLICT (mp_payment_id) DO UPDATE SET status = EXCLUDED.status""",
                (user['id'], str(pay.get('id')),
                 status, plano['valor'], plano_id))
            if status == 'approved':
                c.execute("""UPDATE users SET
                    plano = %s,
                    plano_expira = NOW() + INTERVAL '30 days'
                    WHERE id = %s""",
                    (plano_id, user['id']))
            conn.commit()
        except Exception:
            logger.exception("Erro ao registrar pagamento cartao")
        finally:
            if conn:
                try:
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
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500


@app.route('/api/pagamento/boleto', methods=['POST'])
@limiter.limit("5 per minute")
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
                'X-Idempotency-Key': f"boleto_{user['id']}_{plano_id}",
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
            conn = None
            try:
                conn = _conn()
                c = conn.cursor()
                c.execute("""INSERT INTO pagamentos
                    (user_id, mp_payment_id, status,
                     valor, plano)
                    VALUES (%s,%s,%s,%s,%s)
                    ON CONFLICT (mp_payment_id) DO UPDATE SET status = EXCLUDED.status""",
                    (user['id'], str(pay.get('id')),
                     pay.get('status'), plano['valor'],
                     plano_id))
                if pay.get('status') == 'approved':
                    c.execute("""UPDATE users SET
                        plano = %s,
                        plano_expira = NOW() + INTERVAL '30 days'
                        WHERE id = %s""",
                        (plano_id, user['id']))
                conn.commit()
            except Exception:
                logger.exception("Erro ao registrar pagamento boleto")
            finally:
                if conn:
                    try:
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
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500


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
    plano = user.get('plano') or 'trial'
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
    features = PLAN_FEATURES.get(plano, PLAN_FEATURES['trial'])
    return jsonify({
        'plano': plano,
        'ativo': ativo,
        'expira': str(expira) if expira else None,
        'limite_leads': limite,
        'total_leads': total_leads,
        'features': features,
        'trial_expirado': plano == 'trial' and not ativo,
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
@limiter.limit("5 per minute", methods=["POST"])
def admin_login():
    error = None
    if request.method == 'POST':
        key = request.form.get('admin_key', '')
        admin_key = os.environ.get('ADMIN_KEY', '')
        if not admin_key:
            error = 'ADMIN_KEY não configurado no servidor'
        elif _hmac.compare_digest(key, admin_key):
            session['admin_auth'] = True
            return redirect(url_for('admin_dashboard'))
        else:
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
    conn = None
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
            if not re.match(r'^emp_\d+$', schema):
                continue
            try:
                c.execute(psql.SQL('SELECT COUNT(*) AS cnt FROM {}.empresas').format(
                    psql.Identifier(schema)))
                total_leads += c.fetchone()['cnt']
            except Exception:
                conn.rollback()
            try:
                c.execute(psql.SQL(
                    'SELECT COUNT(*) AS cnt FROM {}.empresas '
                    'WHERE email_enviado IS NOT NULL').format(
                    psql.Identifier(schema)))
                total_emails += c.fetchone()['cnt']
            except Exception:
                conn.rollback()
        return jsonify({
            'total_users': total_users,
            'active_users': active_users,
            'total_leads': total_leads,
            'total_emails': total_emails,
            'total_payments': total_payments,
        })
    except Exception as e:
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


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
            if schema and re.match(r'^emp_\d+$', schema):
                try:
                    c.execute(psql.SQL('SELECT COUNT(*) AS cnt FROM {}.empresas').format(
                        psql.Identifier(schema)))
                    lead_count = c.fetchone()['cnt']
                except Exception:
                    conn.rollback()
            row['lead_count'] = lead_count
            _serialize_row(row)
            result.append(row)
        conn.close()
        return jsonify(result)
    except Exception as e:
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500


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
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500


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
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500


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
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500


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
        logger.exception(f'{request.path}'); return jsonify({'error': 'Erro interno'}), 500


# =============================================================================
# CRON — Trial lifecycle emails
# =============================================================================

CRON_SECRET = os.environ.get('CRON_SECRET', '')

APP_URL = os.environ.get('APP_URL', 'https://turbovenda.com.br')


def _send_system_email(to_email, subject, html):
    """Envia email de sistema via Resend API (usa RESEND_API_KEY global)."""
    resend_key = os.environ.get('RESEND_API_KEY', '')
    sender_email = os.environ.get('EMAIL_FROM', 'contato@turbovenda.com.br')
    if not resend_key:
        logger.warning('RESEND_API_KEY nao configurada — email nao enviado')
        return False
    try:
        import requests as http
        payload = {
            'from': f'TurboVenda <{sender_email}>',
            'to': [to_email],
            'subject': subject,
            'html': html,
        }
        r = http.post('https://api.resend.com/emails',
                      headers={'Authorization': f'Bearer {resend_key}',
                               'Content-Type': 'application/json'},
                      json=payload,
                      timeout=15)
        if r.status_code in (200, 201):
            logger.info(f'Email enviado para {to_email}: {subject}')
            return True
        else:
            logger.error(f'Resend erro {r.status_code}: {r.text}')
            return False
    except Exception as e:
        logger.error(f'Erro ao enviar email: {e}')
        return False


def _trial_email_3d_html(empresa_nome, total_leads, upgrade_url):
    """HTML do email '3 dias restantes no trial'."""
    return f'''<div style="font-family:Arial,Helvetica,sans-serif;max-width:600px;margin:0 auto;padding:24px;color:#1e293b">
  <div style="text-align:center;margin-bottom:32px">
    <h1 style="color:#6366f1;font-size:24px;margin:0">TurboVenda</h1>
  </div>
  <p style="font-size:16px;line-height:1.6">Olá, <strong>{empresa_nome}</strong>.</p>
  <p style="font-size:16px;line-height:1.6">
    Seu período de teste do TurboVenda expira em <strong>3 dias</strong>.
  </p>
  <div style="background:#f8fafc;border-left:4px solid #6366f1;padding:16px 20px;margin:24px 0;border-radius:0 8px 8px 0">
    <p style="margin:0 0 8px;font-size:15px;color:#475569">Até agora você gerou:</p>
    <p style="margin:0;font-size:28px;font-weight:700;color:#6366f1">{total_leads} leads</p>
  </div>
  <p style="font-size:16px;line-height:1.6">
    Ao expirar o trial, você perde acesso à prospecção automatizada, busca de leads por IA
    e todas as ferramentas de outreach. Seus dados ficam salvos, mas não será possível
    gerar novos leads ou enviar emails.
  </p>
  <div style="text-align:center;margin:32px 0">
    <a href="{upgrade_url}" style="display:inline-block;background:#6366f1;color:#ffffff;text-decoration:none;padding:14px 32px;border-radius:8px;font-size:16px;font-weight:600">
      Fazer upgrade agora
    </a>
  </div>
  <p style="font-size:14px;color:#94a3b8;line-height:1.5">
    Tem dúvidas? Responda este email — nossa equipe responde em até 24h.
  </p>
  <hr style="border:none;border-top:1px solid #e2e8f0;margin:32px 0">
  <p style="font-size:12px;color:#94a3b8;text-align:center">
    TurboVenda — Prospecção comercial inteligente
  </p>
</div>'''


def _trial_email_expired_html(empresa_nome, total_leads, upgrade_url):
    """HTML do email 'trial expirou'."""
    return f'''<div style="font-family:Arial,Helvetica,sans-serif;max-width:600px;margin:0 auto;padding:24px;color:#1e293b">
  <div style="text-align:center;margin-bottom:32px">
    <h1 style="color:#6366f1;font-size:24px;margin:0">TurboVenda</h1>
  </div>
  <p style="font-size:16px;line-height:1.6">Olá, <strong>{empresa_nome}</strong>.</p>
  <p style="font-size:16px;line-height:1.6">
    Seu período de teste do TurboVenda <strong>expirou</strong>.
  </p>
  <div style="background:#f8fafc;border-left:4px solid #6366f1;padding:16px 20px;margin:24px 0;border-radius:0 8px 8px 0">
    <p style="margin:0 0 8px;font-size:15px;color:#475569">Durante o trial você construiu:</p>
    <p style="margin:0;font-size:28px;font-weight:700;color:#6366f1">{total_leads} leads</p>
    <p style="margin:8px 0 0;font-size:14px;color:#64748b">Todos os seus dados continuam salvos.</p>
  </div>
  <p style="font-size:16px;line-height:1.6">
    Para voltar a prospectar e acessar seus leads, ative um plano.
    Você não perde nenhum dado — tudo continua exatamente onde parou.
  </p>
  <div style="text-align:center;margin:32px 0">
    <a href="{upgrade_url}" style="display:inline-block;background:#6366f1;color:#ffffff;text-decoration:none;padding:14px 32px;border-radius:8px;font-size:16px;font-weight:600">
      Reativar minha conta
    </a>
  </div>
  <p style="font-size:14px;color:#94a3b8;line-height:1.5">
    Precisa de ajuda para escolher o plano certo? Responda este email.
  </p>
  <hr style="border:none;border-top:1px solid #e2e8f0;margin:32px 0">
  <p style="font-size:12px;color:#94a3b8;text-align:center">
    TurboVenda — Prospecção comercial inteligente
  </p>
</div>'''


def _get_lead_count(schema):
    """Retorna total de leads do user (0 se erro)."""
    try:
        conn = _conn(schema)
        c = conn.cursor()
        c.execute('SELECT COUNT(*) AS n FROM empresas')
        n = c.fetchone()['n']
        conn.close()
        return n
    except Exception:
        return 0


@app.route('/api/cron/trial-emails')
@limiter.limit("6 per hour")
def cron_trial_emails():
    """Endpoint chamado por cron externo para enviar emails do ciclo de trial.

    Protegido por CRON_SECRET. Envia:
    - Aviso de 3 dias restantes (plano_expira entre 2 e 4 dias no futuro)
    - Aviso de trial expirado (plano_expira entre ontem e anteontem)

    Janelas de 2 dias em vez de exatas para tolerar cron que roda 1x/dia.
    """
    token = request.args.get('token', '') or request.headers.get('X-Cron-Secret', '')
    if not CRON_SECRET or not token or not _hmac.compare_digest(token, CRON_SECRET):
        return jsonify({'error': 'Não autorizado'}), 401

    if not DATABASE_URL:
        return jsonify({'error': 'DATABASE_URL não configurado'}), 500

    upgrade_url = f'{APP_URL}/dashboard?upgrade=starter'
    sent_3d = 0
    sent_expired = 0
    errors = 0

    try:
        conn = _conn()
        c = conn.cursor()

        # --- Usuarios cujo trial expira em 2-4 dias (janela para "3 dias") ---
        c.execute("""
            SELECT id, email, empresa_nome, schema_name, plano_expira
            FROM users
            WHERE plano = 'trial'
              AND plano_expira IS NOT NULL
              AND plano_expira > NOW()
              AND plano_expira <= NOW() + INTERVAL '4 days'
              AND plano_expira > NOW() + INTERVAL '2 days'
              AND ativo = TRUE
              AND (trial_email_3d_sent IS NULL OR trial_email_3d_sent = FALSE)
        """)
        users_3d = c.fetchall()

        for u in users_3d:
            schema = u.get('schema_name') or f'emp_{u["id"]}'
            total = _get_lead_count(schema)
            empresa = u.get('empresa_nome') or 'Equipe'
            html = _trial_email_3d_html(empresa, total, upgrade_url)
            ok = _send_system_email(
                u['email'],
                'Seu trial do TurboVenda expira em 3 dias',
                html
            )
            if ok:
                c.execute('UPDATE users SET trial_email_3d_sent = TRUE WHERE id = %s',
                          (u['id'],))
                conn.commit()
                sent_3d += 1
            else:
                errors += 1

        # --- Usuarios cujo trial expirou entre ontem e anteontem ---
        c.execute("""
            SELECT id, email, empresa_nome, schema_name, plano_expira
            FROM users
            WHERE plano = 'trial'
              AND plano_expira IS NOT NULL
              AND plano_expira < NOW()
              AND plano_expira >= NOW() - INTERVAL '2 days'
              AND ativo = TRUE
              AND (trial_email_expired_sent IS NULL OR trial_email_expired_sent = FALSE)
        """)
        users_expired = c.fetchall()

        for u in users_expired:
            schema = u.get('schema_name') or f'emp_{u["id"]}'
            total = _get_lead_count(schema)
            empresa = u.get('empresa_nome') or 'Equipe'
            html = _trial_email_expired_html(empresa, total, upgrade_url)
            ok = _send_system_email(
                u['email'],
                'Seu trial do TurboVenda expirou',
                html
            )
            if ok:
                c.execute('UPDATE users SET trial_email_expired_sent = TRUE WHERE id = %s',
                          (u['id'],))
                conn.commit()
                sent_expired += 1
            else:
                errors += 1

        conn.close()
    except Exception as e:
        logger.error(f'Erro geral cron: {e}')
        return jsonify({'error': 'Erro interno'}), 500

    result = {
        'ok': True,
        'sent_3d_warning': sent_3d,
        'sent_expired': sent_expired,
        'errors': errors,
    }
    logger.info(f'trial-emails concluido: {result}')
    return jsonify(result)


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == '__main__':
    _init_public_schema()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
