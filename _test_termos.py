#!/usr/bin/env python3
import random, re, sys
random.seed(42)

sys.path.insert(0, '.')

# Extract just the function
with open('app.py', 'r', encoding='utf-8') as f:
    src = f.read()

# Find the function
idx = src.index('def _gerar_termos(')
# Find the next def at same indentation
end = src.index('\n\n\n# --- API Tokens', idx)
func_code = src[idx:end]

exec(func_code)

desc_pili = """Vendemos tombadores de grãos (fixos e móveis), coletores de amostra, rachadores de lenha, prensas hidráulicas e centrais hidráulicas para o setor agrícola e indústria cerealista. Nosso cliente ideal é o gerente de operações, compras ou infraestrutura de cooperativas agrícolas, cerealistas, silos, tradings e agroindústrias que recebem e armazenam soja, milho e trigo no Sul e Centro-Oeste do Brasil."""

result = _gerar_termos('Pili Industrial', desc_pili, 'https://www.pili.ind.br/')

print(f"=== {len(result['termos'])} termos ===")
for t in result['termos'][:20]:
    print(f"  {t}")
print(f"\n=== {len(result['cargos'])} cargos ===")
for c in result['cargos']:
    print(f"  {c}")

# Check: should NOT have restaurante, clínica, pet shop, etc.
bad = [t for t in result['termos'] if any(x in t.lower() for x in ['restaurante', 'clínica', 'pet shop', 'publicidade', 'advocacia', 'beleza'])]
if bad:
    print(f"\n!!! PROBLEMA: {len(bad)} termos genéricos encontrados:")
    for b in bad:
        print(f"  BAD: {b}")
else:
    print("\n✓ Nenhum termo genérico irrelevante encontrado!")

# Check regions
sul_co = [t for t in result['termos'] if any(c in t for c in ['Curitiba', 'Porto Alegre', 'Cascavel', 'Goiânia', 'Campo Grande', 'Cuiabá', 'Sinop', 'PR', 'RS', 'SC', 'GO', 'MT', 'MS'])]
print(f"\n✓ {len(sul_co)} termos com cidades/estados do Sul e Centro-Oeste")
