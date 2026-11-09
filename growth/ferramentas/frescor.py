"""Fila de atualização: páginas que estão perdendo busca orgânica.

Enquanto o Search Console não tem acesso por API, usa a telemetria do próprio
site (tabela `pageviews`): entradas vindas do Google ou do Bing por página,
nos últimos 28 dias contra os 28 anteriores. Quando houver dados do GSC
(Fase 6), a mesma fila passa a usar cliques e posição.

    python growth/ferramentas/frescor.py --dsn-arquivo %LOCALAPPDATA%/TurboVenda/database_url.txt

Grava growth/fila-atualizacao.md. Só lê o banco.
"""
import argparse
import os
from datetime import date

import psycopg2

ORGANICO = r"referrer ~* '(^|\.)(google|bing)\.'"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--dsn-arquivo', help='arquivo com a DATABASE_URL (senão usa a variável)')
    ap.add_argument('--saida', default='growth/fila-atualizacao.md')
    ap.add_argument('--queda-min', type=float, default=0.3, help='queda mínima (0,3 = 30%%)')
    ap.add_argument('--base-min', type=int, default=5, help='entradas mínimas no período anterior')
    args = ap.parse_args()
    dsn = os.environ.get('DATABASE_URL', '')
    if args.dsn_arquivo:
        with open(os.path.expandvars(args.dsn_arquivo), encoding='utf-8-sig') as f:
            dsn = f.read().strip()
    conn = psycopg2.connect(dsn)
    c = conn.cursor()
    c.execute(f"""
        SELECT path,
               COUNT(*) FILTER (WHERE created_at >= now() - interval '28 days') AS atual,
               COUNT(*) FILTER (WHERE created_at <  now() - interval '28 days'
                                  AND created_at >= now() - interval '56 days') AS anterior
        FROM pageviews
        WHERE NOT is_bot AND entrada AND {ORGANICO}
          AND created_at >= now() - interval '56 days'
        GROUP BY path""")
    linhas = c.fetchall()
    c.execute("SELECT MIN(created_at)::date FROM pageviews")
    inicio = c.fetchone()[0]
    conn.close()

    caindo = sorted(((p, a, b) for p, a, b in linhas
                     if b >= args.base_min and a <= b * (1 - args.queda_min)),
                    key=lambda x: x[1] - x[2])
    subindo = sorted(((p, a, b) for p, a, b in linhas if a > b), key=lambda x: x[2] - x[1])[:15]
    dias = (date.today() - inicio).days if inicio else 0
    with open(args.saida, 'w', encoding='utf-8', newline='\n') as f:
        f.write(f'# Fila de atualização — {date.today():%d/%m/%Y}\n\n')
        f.write('Fonte: telemetria própria (`pageviews`), entradas vindas de Google ou Bing; '
                'últimos 28 dias contra os 28 anteriores.\n')
        if dias < 56:
            f.write(f'\n**Atenção:** a telemetria começou há {dias} dias, então o período '
                    'anterior ainda está incompleto e quedas podem não aparecer.\n')
        f.write(f'\n## Perdendo tráfego (queda ≥ {args.queda_min:.0%} com ≥ {args.base_min} '
                'entradas antes) — atualizar primeiro\n\n')
        if caindo:
            f.write('| Página | 28 dias anteriores | Últimos 28 dias | Variação |\n|---|---|---|---|\n')
            for p, a, b in caindo:
                f.write(f'| `{p}` | {b} | {a} | {(a - b) / b:+.0%} |\n')
        else:
            f.write('Nenhuma página nesse critério.\n')
        f.write('\n## Ganhando tráfego (referência do que funciona)\n\n')
        f.write('| Página | 28 dias anteriores | Últimos 28 dias |\n|---|---|---|\n')
        for p, a, b in subindo:
            f.write(f'| `{p}` | {b} | {a} |\n')
    print(f'{len(caindo)} página(s) perdendo tráfego; fila em {args.saida}')


if __name__ == '__main__':
    main()
