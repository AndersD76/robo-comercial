"""Chama de volta quem testou o TurboVenda antes das correções de 03/11/2026.

Até ali o robô gravava contatos errados (e-mail press@google.com, telefone
tirado da nota do Google) e quem testou viu lixo. Este script estende o teste
dessas contas em 7 dias, a partir de hoje se já venceu, e manda um e-mail
explicando o que foi corrigido, com os números da conta.

Cada conta recebe uma vez só (users.reativacao_enviada_em). Sem --aplicar,
só mostra quantas contas seriam chamadas, sem enviar nem mudar nada.

    railway run python scripts/reativar_testes.py
    railway run python scripts/reativar_testes.py --aplicar
"""
import argparse
import os
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
import psycopg2  # noqa: E402
import psycopg2.extras  # noqa: E402
import emails_funil  # noqa: E402

CORRECOES_EM = '2026-11-04'   # contas criadas antes disto pegaram o robô quebrado
PRECO_STARTER = 97.00          # MP_PLANOS['starter'] no app.py
APP_URL = os.environ.get('APP_URL', 'https://www.turbovenda.com.br')


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--aplicar', action='store_true',
                    help='estende os testes e envia os e-mails')
    ap.add_argument('--criados-antes', default=CORRECOES_EM)
    args = ap.parse_args()

    dsn = os.environ.get('DATABASE_URL')
    if not dsn:
        sys.exit('DATABASE_URL não definido (rode com railway run)')
    chave = os.environ.get('RESEND_API_KEY', '')
    remetente = os.environ.get('EMAIL_FROM', 'contato@turbovenda.com.br')
    if args.aplicar and not chave:
        sys.exit('RESEND_API_KEY não definido: nenhum e-mail sairia')

    conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    cur = conn.cursor()
    emails_funil.migrar(cur)
    conn.commit()
    alvos = emails_funil.alvos_reativacao(cur, args.criados_antes)

    com_leads = cheios = vencidos = 0
    for u in alvos:
        r = emails_funil.resumo_leads(cur, u['schema_name'] or f'emp_{u["id"]}')
        com_leads += r['validos'] > 0
        cheios += r['validos'] >= emails_funil.COTA_TESTE
        cur.execute('SELECT %s < NOW() AS v', (u['plano_expira'],))
        vencidos += bool(u['plano_expira'] and cur.fetchone()['v'])
    print(f'{len(alvos)} contas de teste criadas antes de {args.criados_antes}: '
          f'{vencidos} com o teste vencido, {com_leads} com leads, '
          f'{cheios} com a cota de {emails_funil.COTA_TESTE} cheia')
    if not args.aplicar:
        print('(simulação: nada enviado; rode com --aplicar)')
        return 0

    def enviar(para, assunto, html):
        return emails_funil.enviar_resend(chave, remetente, para, assunto, html)

    ok = falhas = 0
    for u in alvos:
        if emails_funil.reativar(conn, u, enviar, APP_URL, PRECO_STARTER):
            ok += 1
        else:
            falhas += 1
        time.sleep(0.6)   # Resend aceita 2 envios por segundo
    print(f'reativadas e avisadas: {ok}; falhas (nada mudou nelas): {falhas}')
    conn.close()
    return 0 if not falhas else 1


if __name__ == '__main__':
    sys.exit(main())
