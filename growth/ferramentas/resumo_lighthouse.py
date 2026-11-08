"""Resume os JSON do Lighthouse (growth/dados/lighthouse/lh-NN.json) numa tabela."""
import glob
import json
import sys

pasta = sys.argv[1] if len(sys.argv) > 1 else 'growth/dados/lighthouse'
print('| Página | Perf | SEO | Acess. | LCP | CLS | TBT | INP* | JS (KB) | Peso total (KB) |')
print('|---|---|---|---|---|---|---|---|---|---|')
for f in sorted(glob.glob(f'{pasta}/lh-*.json')):
    d = json.load(open(f, encoding='utf-8'))
    a, c = d['audits'], d['categories']
    def num(k, div=1, casas=1):
        v = a.get(k, {}).get('numericValue')
        return '-' if v is None else f'{v / div:.{casas}f}'
    itens = a.get('resource-summary', {}).get('details', {}).get('items', [])
    js = next((i['transferSize'] for i in itens if i.get('resourceType') == 'script'), 0)
    total = next((i['transferSize'] for i in itens if i.get('resourceType') == 'total'), 0)
    caminho = d['finalDisplayedUrl'].replace('https://www.turbovenda.com.br', '') or '/'
    pct = lambda k: str(round((c.get(k, {}).get('score') or 0) * 100))
    print(f"| `{caminho}` | {pct('performance')} | {pct('seo')} | {pct('accessibility')} | "
          f"{num('largest-contentful-paint', 1000)} s | {num('cumulative-layout-shift', 1, 3)} | "
          f"{num('total-blocking-time', 1, 0)} ms | {num('interaction-to-next-paint', 1, 0)} | "
          f"{js / 1024:.0f} | {total / 1024:.0f} |")
print('\n*INP só existe em dado de campo; no laboratório o TBT é o indicador equivalente.')
