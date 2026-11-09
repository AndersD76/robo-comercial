"""Atualiza o índice local da Receita quando sai base nova.

A Receita publica os dados abertos do CNPJ uma vez por mês. Este script roda
todo dia pela tarefa TurboVenda-Receita-Mensal (instalar_worker.ps1): se o
espelho ainda tem o mesmo mês do índice, sai em segundos; se tem mês novo,
baixa os zips, monta o índice ao lado do atual e troca.

O worker continua usando o índice velho durante a montagem (~1 h); só para
por alguns segundos na troca. Leads que ficaram sem CNPJ voltam a ser
conferidos contra a base nova, porque a lista de conferidos é por versão.

Uso manual (não precisa ser Administrador):
    python scripts/atualizar_receita.py            # só se houver mês novo
    python scripts/atualizar_receita.py --forcar   # remonta mesmo assim
"""
import argparse
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import zipfile
from datetime import datetime

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import cnpj_ingest  # noqa: E402

PASTA_MES = re.compile(r'^\d{4}-\d{2}(-\d{2})?$')
SEM_JANELA = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
PRIORIDADE_BAIXA = getattr(subprocess, 'BELOW_NORMAL_PRIORITY_CLASS', 0)


def mes_do_indice(indice):
    try:
        with open(indice + '.mes', encoding='utf-8') as f:
            return f.read().strip()
    except OSError:
        return ''


def gravar_mes(indice, mes):
    tmp = indice + '.mes.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(mes)
    os.replace(tmp, indice + '.mes')


def contar(caminho):
    conn = sqlite3.connect(f'file:{caminho}?mode=ro', uri=True)
    try:
        return conn.execute('SELECT COUNT(*) FROM empresas_publicas').fetchone()[0]
    finally:
        conn.close()


def validar(novo, linhas_antigas):
    """Não troca um índice bom por um quebrado ou pela metade."""
    conn = sqlite3.connect(f'file:{novo}?mode=ro', uri=True)
    try:
        ok = conn.execute('PRAGMA quick_check').fetchone()[0]
    finally:
        conn.close()
    if ok != 'ok':
        raise RuntimeError(f'indice novo corrompido: {ok}')
    linhas = contar(novo)
    # A base cresce mês a mês; encolher 10% é download truncado ou zip ruim
    if linhas_antigas and linhas < linhas_antigas * 0.9:
        raise RuntimeError(f'indice novo com {linhas:,} empresas contra '
                           f'{linhas_antigas:,} do atual; mantido o atual')
    return linhas


def _schtasks(*args):
    subprocess.run(['schtasks', *args], capture_output=True,
                   creationflags=SEM_JANELA)


def trocar(novo, indice, tarefa):
    """Pausa o worker só durante a troca: no Windows não dá para substituir
    um arquivo que outro processo tem aberto."""
    _schtasks('/Change', '/TN', tarefa, '/DISABLE')
    try:
        # Interromper é seguro: o worker grava o progresso a cada 25 leads
        _schtasks('/End', '/TN', tarefa)
        for _ in range(60):
            try:
                os.replace(novo, indice)
                return
            except PermissionError:
                time.sleep(10)
        raise RuntimeError(f'{indice} continua em uso; troca adiada')
    finally:
        _schtasks('/Change', '/TN', tarefa, '/ENABLE')


def descartar_zips_quebrados(pasta_mes):
    """Download cortado no meio fica salvo e o cnpj_ingest pula arquivo que
    já existe: sem isto a montagem falharia todo dia no mesmo zip."""
    if not os.path.isdir(pasta_mes):
        return
    for nome in os.listdir(pasta_mes):
        if not nome.endswith('.zip'):
            continue
        caminho = os.path.join(pasta_mes, nome)
        try:
            zipfile.ZipFile(caminho).close()
        except zipfile.BadZipFile:
            print(f'[limpeza] {nome} veio truncado; sera baixado de novo')
            os.remove(caminho)


def atualizar_relatorio(indice, dsn_arquivo):
    """Recalcula /dados/empresas-ativas-no-brasil com a base nova. Falhar
    aqui não desfaz a troca do índice: só avisa no log."""
    if not dsn_arquivo or not os.path.exists(dsn_arquivo):
        print('[aviso] sem arquivo de DSN: relatório de dados não atualizado')
        return
    sys.stdout.flush()
    r = subprocess.run([sys.executable, '-u', os.path.join(AQUI, 'relatorio_dados.py'),
                        '--indice', indice, '--dsn-arquivo', dsn_arquivo],
                       stdout=sys.stdout, stderr=subprocess.STDOUT,
                       creationflags=SEM_JANELA | PRIORIDADE_BAIXA)
    if r.returncode != 0:
        print(f'[aviso] relatório de dados falhou (código {r.returncode})')


def limpar_meses_antigos(pasta_zips, manter=2):
    """Guarda o mês atual e o anterior (para remontar sem baixar de novo)."""
    meses = sorted(n for n in os.listdir(pasta_zips)
                   if PASTA_MES.match(n)
                   and os.path.isdir(os.path.join(pasta_zips, n)))
    for mes in meses[:-manter]:
        print(f'[limpeza] apagando zips de {mes}')
        shutil.rmtree(os.path.join(pasta_zips, mes), ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--indice', default='C:/cnpj/indice.sqlite')
    ap.add_argument('--zips', default='D:/cnpj',
                    help='onde guardar os zips, uma pasta por mês')
    ap.add_argument('--tarefa-worker', default='TurboVenda-Receita')
    ap.add_argument('--forcar', action='store_true',
                    help='remonta mesmo que o mês seja o mesmo do índice')
    ap.add_argument('--log', help='acrescenta a saída neste arquivo')
    ap.add_argument('--dsn-arquivo', default=os.path.expandvars(
        r'%LOCALAPPDATA%\TurboVenda\database_url.txt'),
        help='DSN do banco para gravar o relatório de dados da base nova')
    args = ap.parse_args()

    if args.log:
        sys.stdout = sys.stderr = open(args.log, 'a', encoding='utf-8',
                                       buffering=1)
    print(f'--- {datetime.now():%Y-%m-%d %H:%M:%S}')

    atual = mes_do_indice(args.indice)
    try:
        ultimo = cnpj_ingest.latest_month_folder(cnpj_ingest._http())
    except Exception as e:
        print(f'[erro] espelho da Receita fora do ar: {e}')
        return 1
    if ultimo == atual and not args.forcar:
        print(f'[ok] indice ja e de {atual}')
        return 0
    print(f'[mes] indice de {atual or "?"}, espelho tem {ultimo}')

    pasta = os.path.dirname(os.path.abspath(args.indice))
    tamanho = os.path.getsize(args.indice) if os.path.exists(args.indice) else 0
    livre = shutil.disk_usage(pasta).free
    precisa = max(2 * tamanho, 20 * 1024**3) + 5 * 1024**3
    if livre < precisa:
        print(f'[erro] {pasta} com {livre / 1024**3:.0f} GB livres; a montagem '
              f'precisa de ~{precisa / 1024**3:.0f} GB')
        return 1

    novo = os.path.join(pasta, 'indice_novo.sqlite')
    pasta_mes = os.path.join(args.zips, ultimo)
    env = dict(os.environ)
    # Sem isto o cnpj_ingest gravaria no Postgres de produção, não no SQLite
    env.pop('DATABASE_URL', None)
    cmd = [sys.executable, '-u', os.path.join(AQUI, 'cnpj_ingest.py'),
           '--month', ultimo, '--dir', pasta_mes, '--keep',
           '--sqlite', novo, '--ufs', '*', '--todos-cnaes', '--so-com-contato']
    sys.stdout.flush()
    r = subprocess.run(cmd, env=env, stdout=sys.stdout, stderr=subprocess.STDOUT,
                       creationflags=SEM_JANELA | PRIORIDADE_BAIXA)
    if r.returncode != 0 or not os.path.exists(novo):
        print(f'[erro] montagem falhou (codigo {r.returncode}); indice atual mantido')
        descartar_zips_quebrados(pasta_mes)
        return 1

    try:
        antigas = contar(args.indice) if tamanho else 0
        linhas = validar(novo, antigas)
        trocar(novo, args.indice, args.tarefa_worker)
    except Exception as e:
        print(f'[erro] {e}')
        return 1
    gravar_mes(args.indice, ultimo)
    print(f'[ok] indice atualizado para {ultimo}: {linhas:,} empresas')
    limpar_meses_antigos(args.zips)
    atualizar_relatorio(args.indice, args.dsn_arquivo)
    return 0


if __name__ == '__main__':
    sys.exit(main())
