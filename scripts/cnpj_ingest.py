#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ingestão dos dados abertos CNPJ da Receita Federal -> tabela empresas_publicas.

STANDALONE: roda fora do web app. Usa DATABASE_URL do ambiente (Postgres).

Fonte: https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/
  - pasta do mês mais recente (ex.: 2026-06/)
  - Estabelecimentos0..9.zip  (endereço, CNAE, situação, município)
  - Empresas0..9.zip          (razão social, porte)
  - Municipios.zip            (código TOM -> nome do município)
  CSVs: separador ';', encoding latin-1, SEM header, campos por posição
  (layout oficial: "cnpj-metadados.pdf" no mesmo site).

Filtros aplicados:
  - situação cadastral ativa (02)
  - UF em RS, SC, PR
  - CNAE principal na lista CNAE_B2B (~50 CNAEs, ver pseo_data.py)
  - apenas matriz (identificador 1) — evita duplicar filiais por cnpj_basico

Uso:
  # Teste local end-to-end com ~200 empresas sintéticas (sem download):
  python scripts/cnpj_ingest.py --sample
  #   -> usa DATABASE_URL se definido; senão cria pseo_dev.sqlite (só p/ teste)

  # Ingestão real (ATENÇÃO: download de ~6-8 GB, horas de execução):
  DATABASE_URL=postgresql://... python scripts/cnpj_ingest.py
  python scripts/cnpj_ingest.py --month 2026-06 --dir /tmp/cnpj --keep

Idempotente: INSERT ... ON CONFLICT (cnpj_basico) DO NOTHING.
"""

import argparse
import csv
import io
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pseo_data import CNAE_CODIGOS, UFS_INGEST  # noqa: E402

BASE_URL = 'https://dados-abertos-rf-cnpj.casadosdados.com.br/arquivos/'
BATCH = 5000

# Posições no CSV Estabelecimentos (layout oficial dados abertos CNPJ)
E_CNPJ_BASICO = 0
E_MATRIZ_FILIAL = 3       # 1=matriz 2=filial
E_NOME_FANTASIA = 4
E_SITUACAO = 5            # 02=ativa
E_DATA_INICIO = 10        # AAAAMMDD
E_CNAE_PRINCIPAL = 11
E_BAIRRO = 17
E_UF = 19
E_MUNICIPIO_COD = 20      # código TOM -> Municipios.zip
E_DDD_1 = 21              # conferido em Estabelecimentos1.zip
E_TELEFONE_1 = 22
E_DDD_2 = 23
E_TELEFONE_2 = 24
E_EMAIL = 27

# Posições no CSV Empresas
EMP_CNPJ_BASICO = 0
EMP_RAZAO_SOCIAL = 1
EMP_PORTE = 5             # 00/01/03/05


def limpar_telefone(ddd, numero):
    """Junta DDD + numero. Descarta o que nao tem cara de telefone."""
    ddd = re.sub(r'\D', '', ddd or '')
    numero = re.sub(r'\D', '', numero or '')
    if not numero or len(numero) < 8 or len(numero) > 9:
        return None
    if len(ddd) != 2:
        return None
    if numero == numero[0] * len(numero):      # 00000000, 99999999
        return None
    return f'({ddd}) {numero}'


def limpar_email(valor):
    """A Receita traz lixo e endereco de contador; filtra o obvio."""
    e = (valor or '').strip().lower()
    if not e or '@' not in e or ' ' in e:
        return None
    if not re.fullmatch(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", e):
        return None
    return e[:120]


# ---------------------------------------------------------------------------
# Adaptadores de banco (Postgres via DATABASE_URL; SQLite só p/ --sample local)
# ---------------------------------------------------------------------------

DDL_PG = """
CREATE TABLE IF NOT EXISTS empresas_publicas (
    cnpj_basico    TEXT PRIMARY KEY,
    razao_social   TEXT,
    nome_fantasia  TEXT,
    municipio      TEXT,
    uf             TEXT,
    bairro         TEXT,
    cnae_principal TEXT,
    porte          TEXT,
    data_abertura  DATE,
    situacao       TEXT,
    telefone       TEXT,
    telefone2      TEXT,
    email          TEXT
)"""

# quem ja rodou a ingestao antes nao tem essas colunas
MIGRACOES = [
    'ALTER TABLE empresas_publicas ADD COLUMN IF NOT EXISTS telefone TEXT',
    'ALTER TABLE empresas_publicas ADD COLUMN IF NOT EXISTS telefone2 TEXT',
    'ALTER TABLE empresas_publicas ADD COLUMN IF NOT EXISTS email TEXT',
]

DDL_SQLITE = DDL_PG.replace('DATE', 'TEXT')

INDEXES = [
    'CREATE INDEX IF NOT EXISTS idx_emp_pub_cnae_uf_mun ON empresas_publicas (cnae_principal, uf, municipio)',
    'CREATE INDEX IF NOT EXISTS idx_emp_pub_uf_mun ON empresas_publicas (uf, municipio)',
    # o robo busca por CNAE+UF entre quem tem contato
    'CREATE INDEX IF NOT EXISTS idx_emp_pub_contato ON empresas_publicas (uf, cnae_principal) '
    'WHERE telefone IS NOT NULL OR email IS NOT NULL',
    # o cruzamento do robo casa o lead da web pelo telefone
    'CREATE INDEX IF NOT EXISTS idx_emp_pub_tel ON empresas_publicas (telefone) '
    'WHERE telefone IS NOT NULL',
    'CREATE INDEX IF NOT EXISTS idx_emp_pub_tel2 ON empresas_publicas (telefone2) '
    'WHERE telefone2 IS NOT NULL',
]


class PgDB:
    def __init__(self, dsn):
        import psycopg2
        import psycopg2.extras
        self._psycopg2 = psycopg2
        self._extras = psycopg2.extras
        self._dsn = dsn
        self.conn = psycopg2.connect(dsn)

    def _reconnect(self):
        try:
            self.conn.close()
        except Exception:
            pass
        import time
        for attempt in range(5):
            try:
                self.conn = self._psycopg2.connect(self._dsn)
                return
            except Exception:
                time.sleep(2 ** attempt)
        raise RuntimeError('Falha ao reconectar ao Postgres após 5 tentativas')

    def _exec_with_retry(self, fn, max_retries=3):
        for attempt in range(max_retries):
            try:
                return fn()
            except (self._psycopg2.OperationalError,
                    self._psycopg2.InterfaceError):
                print(f'[db] conexão perdida, reconectando (tentativa {attempt + 1})...')
                self._reconnect()
        return fn()

    def ensure_schema(self):
        def _do():
            with self.conn.cursor() as c:
                c.execute(DDL_PG)
                for mig in MIGRACOES:
                    try:
                        c.execute(mig)
                    except Exception:
                        self.conn.rollback()
                for idx in INDEXES:
                    c.execute(idx)
            self.conn.commit()
        self._exec_with_retry(_do)

    def insert_batch(self, rows):
        if not rows:
            return
        def _do():
            with self.conn.cursor() as c:
                self._extras.execute_values(
                    c,
                    'INSERT INTO empresas_publicas (cnpj_basico, razao_social, nome_fantasia, municipio, uf, bairro, cnae_principal, porte, data_abertura, situacao, telefone, telefone2, email) '
                    'VALUES %s ON CONFLICT (cnpj_basico) DO NOTHING',
                    rows)
            self.conn.commit()
        self._exec_with_retry(_do)

    def update_razao_batch(self, rows):
        if not rows:
            return
        def _do():
            with self.conn.cursor() as c:
                self._extras.execute_values(
                    c,
                    'UPDATE empresas_publicas AS e SET razao_social = v.rs, porte = v.pt '
                    'FROM (VALUES %s) AS v(cb, rs, pt) WHERE e.cnpj_basico = v.cb',
                    rows)
            self.conn.commit()
        self._exec_with_retry(_do)

    def count(self):
        def _do():
            with self.conn.cursor() as c:
                c.execute('SELECT COUNT(*) FROM empresas_publicas')
                return c.fetchone()[0]
        return self._exec_with_retry(_do)

    def close(self):
        self.conn.close()


class SqliteDB:
    def __init__(self, path):
        import sqlite3
        self.conn = sqlite3.connect(path)

    def ensure_schema(self):
        self.conn.execute(DDL_SQLITE)
        for col in ('telefone', 'telefone2', 'email'):
            try:
                self.conn.execute(
                    f'ALTER TABLE empresas_publicas ADD COLUMN {col} TEXT')
            except Exception:
                pass
        for idx in INDEXES:
            self.conn.execute(idx)
        self.conn.commit()

    def insert_batch(self, rows):
        self.conn.executemany(
            'INSERT OR IGNORE INTO empresas_publicas (cnpj_basico, razao_social, '
            'nome_fantasia, municipio, uf, bairro, cnae_principal, porte, '
            'data_abertura, situacao, telefone, telefone2, email) '
            'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)', rows)
        self.conn.commit()

    def update_razao_batch(self, rows):
        self.conn.executemany(
            'UPDATE empresas_publicas SET razao_social=?, porte=? WHERE cnpj_basico=?',
            [(rs, pt, cb) for cb, rs, pt in rows])
        self.conn.commit()

    def count(self):
        return self.conn.execute('SELECT COUNT(*) FROM empresas_publicas').fetchone()[0]

    def close(self):
        self.conn.close()


def _open_db(args):
    dsn = os.environ.get('DATABASE_URL', '')
    if dsn.startswith('psql://'):
        dsn = 'postgresql://' + dsn[7:]
    elif dsn.startswith('postgres://'):
        dsn = 'postgresql://' + dsn[11:]
    if dsn:
        print('[db] Postgres via DATABASE_URL')
        return PgDB(dsn)
    if args.sample:
        path = args.sqlite or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'pseo_dev.sqlite')
        print(f'[db] DATABASE_URL ausente — fallback SQLite (SÓ TESTE): {path}')
        return SqliteDB(path)
    print('[FATAL] DATABASE_URL não definido (obrigatório para ingestão real)')
    sys.exit(1)


# ---------------------------------------------------------------------------
# Download / parsing dos dados abertos
# ---------------------------------------------------------------------------

def _http():
    import requests
    s = requests.Session()
    s.headers['User-Agent'] = 'TurboVenda-cnpj-ingest/1.0 (contato@turbovenda.com.br)'
    return s

def latest_month_folder(session):
    """Descobre a pasta mais recente no índice (AAAA-MM ou AAAA-MM-DD)."""
    r = session.get(BASE_URL, timeout=60)
    r.raise_for_status()
    months = sorted(set(re.findall(r'href="(\d{4}-\d{2}(?:-\d{2})?)/"', r.text)))
    if not months:
        raise RuntimeError('Nenhuma pasta AAAA-MM encontrada em ' + BASE_URL)
    return months[-1]


def list_zip_names(session, month):
    r = session.get(f'{BASE_URL}{month}/', timeout=60)
    r.raise_for_status()
    return sorted(set(re.findall(r'href="([^"]+\.zip)"', r.text)))


def download(session, month, name, dest_dir, max_retries=5):
    import time
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, name)
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        print(f'[down] {name} já existe, pulando')
        return dest
    url = f'{BASE_URL}{month}/{name}'
    for attempt in range(max_retries):
        try:
            print(f'[down] {url}' + (f' (tentativa {attempt + 1})' if attempt else ''))
            with session.get(url, stream=True, timeout=300) as r:
                r.raise_for_status()
                tmp = dest + '.part'
                with open(tmp, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=1 << 20):
                        f.write(chunk)
                os.replace(tmp, dest)
            return dest
        except Exception as e:
            print(f'[down] ERRO: {e}')
            if attempt < max_retries - 1:
                wait = 10 * (attempt + 1)
                print(f'[down] aguardando {wait}s antes de tentar novamente...')
                time.sleep(wait)
            else:
                raise
    return dest


def iter_csv_rows(zip_path):
    """Itera linhas do(s) CSV(s) dentro de um zip da Receita (latin-1, ';', sem header)."""
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            with z.open(info) as raw:
                txt = io.TextIOWrapper(raw, encoding='latin-1', newline='')
                for row in csv.reader(txt, delimiter=';', quotechar='"'):
                    yield row


def parse_data_abertura(s):
    """AAAAMMDD -> AAAA-MM-DD (ou None)."""
    s = (s or '').strip()
    if len(s) == 8 and s.isdigit() and s != '00000000':
        return f'{s[:4]}-{s[4:6]}-{s[6:]}'
    return None


def load_municipios(session, month, dest_dir, keep):
    """Municipios.zip: codigo;nome -> dict."""
    path = download(session, month, 'Municipios.zip', dest_dir)
    mapa = {}
    for row in iter_csv_rows(path):
        if len(row) >= 2:
            mapa[row[0].strip()] = row[1].strip().title()
    if not keep:
        os.remove(path)
    print(f'[mun] {len(mapa)} municípios carregados')
    return mapa


def run_real(db, args):
    session = _http()
    month = args.month or latest_month_folder(session)
    print(f'[ingest] pasta do mês: {month}')
    zips = list_zip_names(session, month)
    est_zips = [z for z in zips if z.startswith('Estabelecimentos')]
    emp_zips = [z for z in zips if z.startswith('Empresas')]
    if not est_zips or not emp_zips:
        raise RuntimeError(f'Zips não encontrados em {month}: {zips[:10]}')

    municipios = load_municipios(session, month, args.dir, args.keep)
    ufs = set(u.strip().upper() for u in args.ufs.split(','))

    # Pass 1 — Estabelecimentos: filtra e insere (razão social vem depois)
    inseridos = 0
    cnpjs = set()
    for name in est_zips:
        path = download(session, month, name, args.dir)
        batch = []
        lidos = 0
        for row in iter_csv_rows(path):
            lidos += 1
            if len(row) <= E_MUNICIPIO_COD:
                continue
            if row[E_SITUACAO].strip() != '02':
                continue
            if row[E_UF].strip().upper() not in ufs:
                continue
            cnae = row[E_CNAE_PRINCIPAL].strip()
            if cnae not in CNAE_CODIGOS:
                continue
            if row[E_MATRIZ_FILIAL].strip() != '1':   # só matriz
                continue
            cb = row[E_CNPJ_BASICO].strip()
            batch.append((
                cb,
                None,                                   # razão social no pass 2
                row[E_NOME_FANTASIA].strip() or None,
                municipios.get(row[E_MUNICIPIO_COD].strip(),
                               row[E_MUNICIPIO_COD].strip()),
                row[E_UF].strip().upper(),
                row[E_BAIRRO].strip().title() or None,
                cnae,
                None,                                   # porte no pass 2
                parse_data_abertura(row[E_DATA_INICIO]),
                row[E_SITUACAO].strip(),
                limpar_telefone(row[E_DDD_1] if len(row) > E_DDD_1 else '',
                                row[E_TELEFONE_1]
                                if len(row) > E_TELEFONE_1 else ''),
                limpar_telefone(row[E_DDD_2] if len(row) > E_DDD_2 else '',
                                row[E_TELEFONE_2]
                                if len(row) > E_TELEFONE_2 else ''),
                limpar_email(row[E_EMAIL] if len(row) > E_EMAIL else ''),
            ))
            cnpjs.add(cb)
            if len(batch) >= BATCH:
                db.insert_batch(batch)
                inseridos += len(batch)
                batch = []
        db.insert_batch(batch)
        inseridos += len(batch)
        print(f'[est] {name}: {lidos} linhas lidas, {inseridos} inseridos acumulados')
        if not args.keep:
            os.remove(path)

    # Pass 2 — Empresas: razão social + porte por cnpj_basico
    atualizados = 0
    for name in emp_zips:
        path = download(session, month, name, args.dir)
        batch = []
        for row in iter_csv_rows(path):
            if len(row) <= EMP_PORTE:
                continue
            cb = row[EMP_CNPJ_BASICO].strip()
            if cb not in cnpjs:
                continue
            batch.append((cb, row[EMP_RAZAO_SOCIAL].strip() or None,
                          row[EMP_PORTE].strip() or None))
            if len(batch) >= BATCH:
                db.update_razao_batch(batch)
                atualizados += len(batch)
                batch = []
        db.update_razao_batch(batch)
        atualizados += len(batch)
        print(f'[emp] {name}: {atualizados} razões sociais atualizadas acumuladas')
        if not args.keep:
            os.remove(path)

    print(f'[done] inseridos={inseridos} razoes_atualizadas={atualizados} '
          f'total_tabela={db.count()}')


# ---------------------------------------------------------------------------
# --sample: ~200 empresas sintéticas p/ provar o fluxo end-to-end sem download
# ---------------------------------------------------------------------------

def run_sample(db):
    import random
    random.seed(42)
    municipios = [('Passo Fundo', 'RS'), ('Porto Alegre', 'RS'),
                  ('Caxias do Sul', 'RS'), ('Chapecó', 'SC'), ('Curitiba', 'PR')]
    cnaes = ['6201501', '4930202', '2511000', '6920601', '4639701', '2833000']
    # Contagens desenhadas p/ exercitar os 3 tiers do quality gate:
    #   >=15 indexável | 8-14 noindex | <8 -> 404
    contagens = [
        # PF  POA  CXS  CHA  CWB
        [15,  16,   9,   5,   0],   # 6201501  (9 -> noindex, 5 -> 404)
        [15,  15,   8,   4,   0],   # 4930202  (8 -> noindex, 4 -> 404)
        [15,  10,   7,   3,   0],   # 2511000  (10 -> noindex, 7 -> 404)
        [16,  15,   6,   2,   0],   # 6920601
        [15,   9,   5,   1,   0],   # 4639701
        [10,   8,   4,   0,   0],   # 2833000  (sem página indexável)
    ]
    bairros = ['Centro', 'São Cristóvão', 'Boqueirão', 'Vera Cruz', 'Petrópolis',
               'Industrial', 'Lucas Araújo', 'Vila Rodrigues']
    sufixos = ['LTDA', 'S.A.', 'EIRELI', 'LTDA ME']
    palavras = ['SUL', 'PRIME', 'FORTE', 'NOVA', 'ALFA', 'BETA', 'UNIAO', 'CENTRAL',
                'MASTER', 'GLOBAL', 'REAL', 'IDEAL', 'RAPIDO', 'SUPER', 'TOP']
    tipos = {'6201501': 'SISTEMAS', '4930202': 'TRANSPORTES', '2511000': 'METALURGICA',
             '6920601': 'CONTABILIDADE', '4639701': 'DISTRIBUIDORA', '2833000': 'IMPLEMENTOS'}
    rows = []
    seq = 10000000
    for i, cnae in enumerate(cnaes):
        for j, (mun, uf) in enumerate(municipios):
            for k in range(contagens[i][j]):
                seq += 1
                nome = f'{tipos[cnae]} {random.choice(palavras)} ' \
                       f'{random.choice(palavras)} {random.choice(sufixos)}'
                ano = random.randint(1995, 2025)
                rows.append((
                    str(seq),
                    nome,
                    nome.split(' LTDA')[0].title() if k % 3 else None,
                    mun, uf,
                    random.choice(bairros),
                    cnae,
                    random.choice(['01', '01', '03', '05', '00']),
                    f'{ano}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}',
                    '02',
                    # cobertura parcial de propósito: na base real ~65% tem
                    # telefone e ~49% email, e o robô precisa lidar com isso
                    limpar_telefone('54', f'3{random.randint(1000000, 9999999)}')
                    if k % 3 else None,
                    None,
                    (f'contato{seq}@exemplo{k}.com.br'
                     if k % 2 else None),
                ))
    db.insert_batch(rows)
    print(f'[sample] {len(rows)} empresas sintéticas inseridas '
          f'({len(cnaes)} CNAEs x {len(municipios)} municípios) — total_tabela={db.count()}')


def main():
    ap = argparse.ArgumentParser(description='Ingestão dados abertos CNPJ -> empresas_publicas')
    ap.add_argument('--sample', action='store_true',
                    help='gera ~200 empresas sintéticas (teste local, sem download)')
    ap.add_argument('--month', help='pasta AAAA-MM (default: mais recente no site)')
    ap.add_argument('--dir', default=os.path.join(os.path.expanduser('~'), 'cnpj_dados'),
                    help='diretório de download dos zips')
    ap.add_argument('--keep', action='store_true', help='não apagar os zips após processar')
    ap.add_argument('--ufs', default=','.join(UFS_INGEST), help='UFs (default RS,SC,PR)')
    ap.add_argument('--sqlite', help='caminho do SQLite (só com --sample, sem DATABASE_URL)')
    args = ap.parse_args()

    db = _open_db(args)
    db.ensure_schema()
    if args.sample:
        run_sample(db)
    else:
        run_real(db, args)
    db.close()


if __name__ == '__main__':
    main()
