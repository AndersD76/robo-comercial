# -*- coding: utf-8 -*-
"""Validação por IP dos robôs de IA que publicam as próprias faixas (OpenAI e
Perplexity). User-agent se falsifica; IP dentro da faixa oficial, não.

As faixas são baixadas em segundo plano uma vez por dia; enquanto não
chegam, o acesso conta como não verificado (nunca atrasa a resposta).
"""
import ipaddress
import threading
import time

FAIXAS = {
    'GPTBot': 'https://openai.com/gptbot.json',
    'OAI-SearchBot': 'https://openai.com/searchbot.json',
    'ChatGPT-User': 'https://openai.com/chatgpt-user.json',
    'PerplexityBot': 'https://www.perplexity.ai/perplexitybot.json',
    'Perplexity-User': 'https://www.perplexity.ai/perplexity-user.json',
}
VALIDADE = 86400
_cache = {}            # robo -> (expira_em, [redes])
_baixando = set()
_trava = threading.Lock()


def redes_de(dados):
    redes = []
    for p in (dados or {}).get('prefixes', []):
        bloco = p.get('ipv4Prefix') or p.get('ipv6Prefix')
        if bloco:
            try:
                redes.append(ipaddress.ip_network(bloco, strict=False))
            except ValueError:
                pass
    return redes


def _baixar(robo):
    try:
        import requests
        r = requests.get(FAIXAS[robo], timeout=15, headers={'User-Agent': 'TurboVenda/1.0 (+https://www.turbovenda.com.br/sobre)'})
        redes = redes_de(r.json()) if r.status_code == 200 else []
        _cache[robo] = (time.time() + (VALIDADE if redes else 3600), redes)
    except Exception:
        _cache[robo] = (time.time() + 3600, [])
    finally:
        with _trava:
            _baixando.discard(robo)


def verificado(robo, ip, agora=None):
    """True se o IP está numa faixa oficial do robô. None se o robô não
    publica faixas (cabe a outro método, como o DNS reverso)."""
    if robo not in FAIXAS:
        return None
    agora = agora or time.time()
    item = _cache.get(robo)
    if not item or item[0] < agora:
        with _trava:
            if robo not in _baixando:
                _baixando.add(robo)
                threading.Thread(target=_baixar, args=(robo,), daemon=True).start()
    redes = (item or (0, []))[1]
    try:
        endereco = ipaddress.ip_address((ip or '').strip())
    except ValueError:
        return False
    return any(endereco in rede for rede in redes)
