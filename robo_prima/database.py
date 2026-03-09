# -*- coding: utf-8 -*-
"""
Banco de dados do Agente de Prospecção — PostgreSQL (Neon)
"""

import os
import psycopg2
import psycopg2.extras

from config import DB_SCHEMA


def _fix_url(url: str) -> str:
    """Garante que a URL use o scheme 'postgresql://' exigido pelo psycopg2."""
    url = (url or '').strip()
    if '://' in url:
        scheme, rest = url.split('://', 1)
        if scheme in ('psql', 'postgres'):
            return 'postgresql://' + rest
    return url


def get_connection():
    url = _fix_url(os.environ.get('DATABASE_URL', ''))
    conn = psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
    with conn.cursor() as c:
        c.execute("SET search_path TO %s, public", (DB_SCHEMA,))
    return conn


def init_database():
    conn = get_connection()
    c = conn.cursor()

    c.execute("CREATE SCHEMA IF NOT EXISTS " + psycopg2.extensions.quote_ident(DB_SCHEMA, conn))
    c.execute("SET search_path TO %s, public", (DB_SCHEMA,))

    c.execute("""CREATE TABLE IF NOT EXISTS empresas (
        id            BIGSERIAL PRIMARY KEY,
        cnpj          TEXT UNIQUE,
        razao_social  TEXT,
        nome_fantasia TEXT,
        segmento      TEXT,
        porte         TEXT,
        funcionarios  TEXT,
        endereco      TEXT,
        cidade        TEXT,
        estado        TEXT,
        telefone      TEXT,
        telefone2     TEXT,
        whatsapp      TEXT,
        email         TEXT,
        website       TEXT,
        linkedin      TEXT,
        instagram     TEXT,
        fonte         TEXT,
        score         INTEGER DEFAULT 0,
        encontrado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status        TEXT DEFAULT 'novo',
        demo_agendado TIMESTAMP,
        demo_status   TEXT,
        email_enviado TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS contatos (
        id         BIGSERIAL PRIMARY KEY,
        empresa_id BIGINT REFERENCES empresas(id),
        nome TEXT, cargo TEXT, telefone TEXT, whatsapp TEXT,
        email TEXT, linkedin TEXT, decisor INTEGER DEFAULT 0
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS interacoes (
        id            BIGSERIAL PRIMARY KEY,
        empresa_id    BIGINT REFERENCES empresas(id),
        contato_id    BIGINT REFERENCES contatos(id),
        canal TEXT, tipo TEXT, mensagem TEXT,
        enviado_em    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        respondeu     INTEGER DEFAULT 0,
        resposta TEXT, respondido_em TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS buscas (
        id BIGSERIAL PRIMARY KEY, termo TEXT, fonte TEXT,
        resultados INTEGER DEFAULT 0,
        executado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS acoes_diarias (
        id BIGSERIAL PRIMARY KEY, data DATE DEFAULT CURRENT_DATE,
        tipo TEXT, quantidade INTEGER DEFAULT 0, UNIQUE(data, tipo)
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS logs (
        id BIGSERIAL PRIMARY KEY,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        tipo TEXT, mensagem TEXT, detalhes TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS execucao (
        id INTEGER PRIMARY KEY, status TEXT DEFAULT 'parado',
        ultima_execucao TIMESTAMP, modo TEXT DEFAULT 'busca'
    )""")

    # Tabela de leads encontrados via LinkedIn / Sales Nav / Apollo
    c.execute("""CREATE TABLE IF NOT EXISTS leads_linkedin (
        id           BIGSERIAL PRIMARY KEY,
        nome         TEXT,
        cargo        TEXT,
        empresa      TEXT,
        url_perfil   TEXT UNIQUE,
        termo_busca  TEXT,
        status       TEXT DEFAULT 'encontrado',
        encontrado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        conexao_em   TIMESTAMP,
        dm_enviada_em TIMESTAMP,
        respondeu    INTEGER DEFAULT 0,
        ultima_resposta TEXT,
        demo_status  TEXT,
        email        TEXT,
        telefone     TEXT,
        fonte        TEXT DEFAULT 'linkedin'
    )""")

    # Migração: adiciona colunas novas se tabela já existia
    for col, tipo, default in [
        ('email', 'TEXT', None),
        ('telefone', 'TEXT', None),
        ('fonte', 'TEXT', "'linkedin'"),
    ]:
        try:
            ddl = f"ALTER TABLE leads_linkedin ADD COLUMN IF NOT EXISTS {col} {tipo}"
            if default:
                ddl += f" DEFAULT {default}"
            c.execute(ddl)
        except Exception:
            conn.rollback()
            c.execute("SET search_path TO %s, public", (DB_SCHEMA,))

    # Migração: adiciona email_enviado em empresas (tabela já existente)
    try:
        c.execute("ALTER TABLE empresas ADD COLUMN IF NOT EXISTS email_enviado TIMESTAMP")
    except Exception:
        conn.rollback()
        c.execute("SET search_path TO %s, public", (DB_SCHEMA,))

    c.execute("INSERT INTO execucao (id, status) VALUES (1, 'parado') ON CONFLICT (id) DO NOTHING")
    conn.commit()
    conn.close()


# =============================================================================
# LOGS
# =============================================================================

def log_acao(tipo, mensagem, detalhes=None):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO logs (tipo, mensagem, detalhes) VALUES (%s, %s, %s)",
              (tipo, mensagem, detalhes))
    conn.commit()
    conn.close()


# =============================================================================
# CONTAGEM DIÁRIA
# =============================================================================

def get_contagem_diaria(tipo):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT quantidade FROM acoes_diarias WHERE data = CURRENT_DATE AND tipo = %s",
              (tipo,))
    result = c.fetchone()
    conn.close()
    return result['quantidade'] if result else 0


def incrementar_contagem(tipo):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""INSERT INTO acoes_diarias (data, tipo, quantidade) VALUES (CURRENT_DATE, %s, 1)
        ON CONFLICT(data, tipo) DO UPDATE SET quantidade = acoes_diarias.quantidade + 1""",
              (tipo,))
    conn.commit()
    conn.close()


# =============================================================================
# VERIFICAÇÕES
# =============================================================================

def whatsapp_ja_contactado(whatsapp):
    if not whatsapp:
        return False
    numero = ''.join(filter(str.isdigit, str(whatsapp)))
    if len(numero) < 10:
        return False
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id, status FROM empresas WHERE whatsapp LIKE %s OR telefone LIKE %s",
              (f'%{numero[-8:]}%', f'%{numero[-8:]}%'))
    result = c.fetchone()
    conn.close()
    return bool(result and result['status'] in ('contactada', 'respondeu', 'convertido'))


def telefone_existe(telefone):
    if not telefone:
        return False
    numero = ''.join(filter(str.isdigit, str(telefone)))
    if len(numero) < 10:
        return False
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id FROM empresas WHERE whatsapp LIKE %s OR telefone LIKE %s",
              (f'%{numero[-8:]}%', f'%{numero[-8:]}%'))
    result = c.fetchone()
    conn.close()
    return result is not None


# =============================================================================
# EMPRESAS
# =============================================================================

def salvar_empresa(dados):
    conn = get_connection()
    c = conn.cursor()
    try:
        for field in ('cnpj', 'website'):
            if dados.get(field):
                c.execute(f"SELECT id FROM empresas WHERE {field} = %s", (dados[field],))
                existing = c.fetchone()
                if existing:
                    conn.close()
                    return existing['id']

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
        # Re-setar search_path após rollback (rollback reverte SET)
        c.execute(
            "SET search_path TO %s, public", (DB_SCHEMA,)
        )
        if dados.get('cnpj'):
            c.execute(
                "SELECT id FROM empresas WHERE cnpj = %s",
                (dados['cnpj'],)
            )
            result = c.fetchone()
            if result:
                return result['id']
        return None
    finally:
        conn.close()


def atualizar_campos_empresa(empresa_id: int, campos: dict):
    """Atualiza campos específicos de uma empresa (só os que têm valor)."""
    if not empresa_id or not campos:
        return
    allowed = {'segmento', 'porte', 'cidade', 'estado', 'cnpj', 'razao_social'}
    updates = {k: v for k, v in campos.items() if k in allowed and v}
    if not updates:
        return
    conn = get_connection()
    c = conn.cursor()
    sets = ', '.join(f'{k} = %s' for k in updates)
    vals = list(updates.values()) + [empresa_id]
    c.execute(f"UPDATE empresas SET {sets} WHERE id = %s", vals)
    conn.commit()
    conn.close()


def atualizar_status_empresa(empresa_id, status):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE empresas SET status = %s WHERE id = %s", (status, empresa_id))
    conn.commit()
    conn.close()


def get_empresas_sem_contato(limite=10):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""SELECT e.* FROM empresas e LEFT JOIN interacoes i ON e.id = i.empresa_id
        WHERE i.id IS NULL AND e.status IN ('novo', 'enriquecido')
        AND (
            (e.whatsapp IS NOT NULL AND e.whatsapp != '')
            OR (e.telefone IS NOT NULL AND e.telefone != '')
        )
        ORDER BY e.score DESC, e.encontrado_em ASC LIMIT %s""", (limite,))
    results = [dict(row) for row in c.fetchall()]
    conn.close()
    return results


def get_empresas_para_followup(dias, tipo_followup):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""SELECT e.*, MAX(i.enviado_em) as ultima_msg, COUNT(i.id) as total_msgs
        FROM empresas e INNER JOIN interacoes i ON e.id = i.empresa_id
        WHERE i.respondeu = 0 AND i.canal = 'whatsapp'
        AND e.status NOT IN ('sem_whatsapp', 'encerrado', 'robo_wa')
        AND NOT EXISTS (SELECT 1 FROM interacoes i2 WHERE i2.empresa_id = e.id AND i2.tipo = %s)
        GROUP BY e.id, e.cnpj, e.razao_social, e.nome_fantasia, e.segmento, e.porte,
                 e.funcionarios, e.endereco, e.cidade, e.estado, e.telefone, e.telefone2,
                 e.whatsapp, e.email, e.website, e.linkedin, e.instagram, e.fonte,
                 e.score, e.encontrado_em, e.status, e.demo_agendado, e.demo_status
        HAVING EXTRACT(EPOCH FROM (NOW() - MAX(i.enviado_em))) / 86400 >= %s
        LIMIT 10""", (tipo_followup, dias))
    results = [dict(row) for row in c.fetchall()]
    conn.close()
    return results


def get_empresas_contactadas(limite=20):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""SELECT DISTINCT e.id, e.nome_fantasia, e.whatsapp, e.status, e.demo_status,
               MAX(i.enviado_em) as ultima_msg, COUNT(i.id) as total_msgs
        FROM empresas e INNER JOIN interacoes i ON e.id = i.empresa_id
        WHERE i.canal = 'whatsapp' AND e.whatsapp IS NOT NULL AND e.whatsapp != ''
        AND e.status NOT IN ('convertido', 'encerrado', 'robo_wa', 'sem_whatsapp')
        GROUP BY e.id, e.nome_fantasia, e.whatsapp, e.status, e.demo_status
        ORDER BY MAX(i.enviado_em) DESC LIMIT %s""", (limite,))
    results = [dict(row) for row in c.fetchall()]
    conn.close()
    return results


def get_empresa_por_whatsapp(numero):
    if not numero:
        return None
    digitos = ''.join(filter(str.isdigit, str(numero)))
    if len(digitos) < 10:
        return None
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(
            "SELECT * FROM empresas WHERE whatsapp LIKE %s",
            (f'%{digitos[-8:]}%',)
        )
        row = c.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()



def get_decisor_empresa(empresa_id):
    """Retorna o contato decisor (decisor=1) da empresa, se existir."""
    if not empresa_id:
        return None
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """SELECT * FROM contatos
           WHERE empresa_id = %s AND decisor = 1
           ORDER BY id DESC LIMIT 1""",
        (empresa_id,)
    )
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def decisor_ja_existe(empresa_id, nome):
    """Verifica se ja existe contato decisor com esse nome."""
    if not empresa_id or not nome:
        return False
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT id FROM contatos WHERE empresa_id = %s AND nome = %s AND decisor = 1",
        (empresa_id, nome)
    )
    row = c.fetchone()
    conn.close()
    return row is not None

# =============================================================================
# CONTATOS
# =============================================================================

def salvar_contato(empresa_id, dados):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""INSERT INTO contatos (empresa_id, nome, cargo, telefone, whatsapp, email, linkedin, decisor)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (empresa_id, dados.get('nome'), dados.get('cargo'), dados.get('telefone'),
         dados.get('whatsapp'), dados.get('email'), dados.get('linkedin'), dados.get('decisor', 0)))
    contato_id = c.fetchone()['id']
    conn.commit()
    conn.close()
    return contato_id


# =============================================================================
# INTERAÇÕES
# =============================================================================

def registrar_busca(termo, fonte, resultados):
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO buscas (termo, fonte, resultados) VALUES (%s, %s, %s)",
              (termo, fonte, resultados))
    conn.commit()
    conn.close()
    incrementar_contagem('buscas')


def registrar_interacao(empresa_id, contato_id, canal, tipo, mensagem):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""INSERT INTO interacoes (empresa_id, contato_id, canal, tipo, mensagem)
        VALUES (%s, %s, %s, %s, %s)""",
              (empresa_id, contato_id, canal, tipo, mensagem))
    conn.commit()
    conn.close()
    incrementar_contagem(f'{canal}_enviados')


def marcar_resposta(interacao_id, resposta):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""UPDATE interacoes SET respondeu = 1, resposta = %s, respondido_em = CURRENT_TIMESTAMP
        WHERE id = %s""", (resposta, interacao_id))
    conn.commit()
    conn.close()


# =============================================================================
# DEMO
# =============================================================================

def get_estagio_conversa(empresa_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""SELECT tipo FROM interacoes WHERE empresa_id = %s AND canal = 'whatsapp'
        ORDER BY enviado_em DESC LIMIT 1""", (empresa_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return 'inicial'
    tipo = row['tipo']
    if tipo == 'demo_proposto':
        return 'demo_proposta'
    if tipo == 'demo_confirmado':
        return 'demo_confirmada'
    return 'inicial'


def marcar_demo_proposto(empresa_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE empresas SET demo_status = 'proposto' WHERE id = %s", (empresa_id,))
    conn.commit()
    conn.close()


def marcar_demo_confirmado(empresa_id, data_hora=None):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE empresas SET demo_status = 'confirmado', demo_agendado = %s WHERE id = %s",
              (data_hora, empresa_id))
    conn.commit()
    conn.close()


# =============================================================================
# EXECUÇÃO
# =============================================================================

def atualizar_status_execucao(status, modo=None):
    conn = get_connection()
    c = conn.cursor()
    if modo:
        c.execute("""UPDATE execucao SET status = %s, modo = %s, ultima_execucao = CURRENT_TIMESTAMP
            WHERE id = 1""", (status, modo))
    else:
        c.execute("""UPDATE execucao SET status = %s, ultima_execucao = CURRENT_TIMESTAMP
            WHERE id = 1""", (status,))
    conn.commit()
    conn.close()


def get_status_execucao():
    conn = get_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM execucao WHERE id = 1')
    result = c.fetchone()
    conn.close()
    return dict(result) if result else None


# =============================================================================
# ESTATÍSTICAS
# =============================================================================

# =============================================================================
# LINKEDIN
# =============================================================================

def registrar_log(tipo, mensagem, detalhes=None):
    """Alias de log_acao para uso do linkedin_bot."""
    log_acao(tipo, mensagem, detalhes)


def salvar_lead_linkedin(perfil: dict, status: str = 'encontrado'):
    """Salva ou atualiza lead vindo do LinkedIn / Sales Nav / Apollo."""
    url = perfil.get('url_perfil', '')
    if not url:
        return None
    conn = get_connection()
    c = conn.cursor()
    try:
        fonte = perfil.get('fonte', 'linkedin')
        email = perfil.get('email', '')
        telefone = perfil.get('telefone', '')
        c.execute("""
            INSERT INTO leads_linkedin
                (nome, cargo, empresa, url_perfil,
                 termo_busca, status, fonte, email, telefone)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (url_perfil) DO UPDATE SET
                status = EXCLUDED.status,
                email = COALESCE(
                    NULLIF(EXCLUDED.email, ''),
                    leads_linkedin.email
                ),
                telefone = COALESCE(
                    NULLIF(EXCLUDED.telefone, ''),
                    leads_linkedin.telefone
                ),
                fonte = CASE
                    WHEN leads_linkedin.fonte = 'linkedin'
                        AND EXCLUDED.fonte != 'linkedin'
                    THEN EXCLUDED.fonte
                    ELSE leads_linkedin.fonte
                END
            RETURNING id
        """, (
            perfil.get('nome'), perfil.get('cargo'),
            perfil.get('empresa'), url,
            perfil.get('termo_busca'), status,
            fonte, email or None, telefone or None
        ))
        row = c.fetchone()
        if status == 'conexao_enviada':
            c.execute(
                "UPDATE leads_linkedin "
                "SET conexao_em = CURRENT_TIMESTAMP "
                "WHERE url_perfil = %s", (url,)
            )
        elif status == 'dm_enviada':
            c.execute(
                "UPDATE leads_linkedin "
                "SET dm_enviada_em = CURRENT_TIMESTAMP "
                "WHERE url_perfil = %s", (url,)
            )
        incrementar_contagem(f'linkedin_{status}')
        conn.commit()
        return row['id'] if row else None
    except Exception as e:
        conn.rollback()
        try:
            log_acao('erro', f'salvar_lead_linkedin: {e}')
        except Exception:
            pass
        return None
    finally:
        conn.close()


def get_leads_linkedin(limite=20):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM leads_linkedin ORDER BY encontrado_em DESC LIMIT %s",
        (limite,)
    )
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_stats_linkedin():
    conn = get_connection()
    c = conn.cursor()
    stats = {}
    c.execute(
        "SELECT COUNT(*) AS n FROM leads_linkedin"
    )
    stats['total'] = c.fetchone()['n']
    c.execute(
        "SELECT COUNT(*) AS n FROM leads_linkedin "
        "WHERE status = 'conexao_enviada'"
    )
    stats['conexoes'] = c.fetchone()['n']
    c.execute(
        "SELECT COUNT(*) AS n FROM leads_linkedin "
        "WHERE respondeu = 1"
    )
    stats['responderam'] = c.fetchone()['n']
    c.execute(
        "SELECT COUNT(*) AS n FROM leads_linkedin "
        "WHERE demo_status = 'confirmado'"
    )
    stats['demos'] = c.fetchone()['n']
    # Stats por fonte
    c.execute("""
        SELECT
            COALESCE(fonte, 'linkedin') AS fonte,
            COUNT(*) AS total
        FROM leads_linkedin
        GROUP BY COALESCE(fonte, 'linkedin')
    """)
    stats['por_fonte'] = {
        row['fonte']: row['total']
        for row in c.fetchall()
    }
    conn.close()
    return stats


def get_estatisticas():
    conn = get_connection()
    c = conn.cursor()
    stats = {}
    for key, sql in [
        ('total_empresas',       'SELECT COUNT(*) as total FROM empresas'),
        ('empresas_novas',       "SELECT COUNT(*) as total FROM empresas WHERE status = 'novo'"),
        ('empresas_contactadas', "SELECT COUNT(*) as total FROM empresas WHERE status = 'contactada'"),
        ('whatsapp_enviados',    "SELECT COUNT(*) as total FROM interacoes WHERE canal = 'whatsapp'"),
        ('whatsapp_respostas',   "SELECT COUNT(*) as total FROM interacoes WHERE canal = 'whatsapp' AND respondeu = 1"),
        ('total_buscas',         'SELECT COUNT(*) as total FROM buscas'),
    ]:
        c.execute(sql)
        stats[key] = c.fetchone()['total']
    stats['buscas_hoje']   = get_contagem_diaria('buscas')
    stats['whatsapp_hoje'] = get_contagem_diaria('whatsapp_enviados')
    conn.close()
    return stats
