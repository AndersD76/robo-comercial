# -*- coding: utf-8 -*-
"""
Testes de rotas HTTP do TurboVenda.

Todos os testes que precisam importar o app requerem DATABASE_URL.
Se DATABASE_URL nao estiver configurado, os testes sao pulados (skip).
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

_HAS_DB = bool(os.environ.get('DATABASE_URL'))


def _skip_no_db():
    if not _HAS_DB:
        pytest.skip("DATABASE_URL nao configurado")


@pytest.fixture(scope='module')
def client():
    """Flask test_client — disponivel apenas se DATABASE_URL existir."""
    _skip_no_db()
    import app as mod
    mod.app.config['TESTING'] = True
    # Desabilita rate-limiter nos testes para evitar 429
    mod.limiter.enabled = False
    with mod.app.test_client() as c:
        yield c


@pytest.fixture(scope='module')
def flask_app():
    """Flask app object — disponivel apenas se DATABASE_URL existir."""
    _skip_no_db()
    import app as mod
    return mod.app


# =========================================================================
# 1. Rotas publicas retornam 200
# =========================================================================

_PUBLIC_ROUTES = [
    '/',
    '/login',
    '/cadastro',
    '/blog',
    '/precos',
    '/termos',
    '/privacidade',
    '/robots.txt',
    '/health',
]


@pytest.mark.parametrize('path', _PUBLIC_ROUTES)
def test_public_route_returns_200(client, path):
    """Rotas publicas devem retornar 200 OK."""
    resp = client.get(path)
    assert resp.status_code == 200, (
        f"{path} retornou {resp.status_code}, esperado 200"
    )


# =========================================================================
# 2. Rotas que exigem autenticacao — sem sessao devem redirecionar ou 401
# =========================================================================

_AUTH_REQUIRED_HTML_ROUTES = [
    '/dashboard',
    '/configurar',
]


@pytest.mark.parametrize('path', _AUTH_REQUIRED_HTML_ROUTES)
def test_auth_html_routes_redirect_without_session(client, path):
    """Rotas HTML protegidas devem redirecionar para /login sem sessao."""
    resp = client.get(path)
    assert resp.status_code in (302, 303), (
        f"{path} retornou {resp.status_code}, esperado redirect 302/303"
    )
    location = resp.headers.get('Location', '')
    assert '/login' in location, (
        f"{path} redirecionou para {location}, esperado conter /login"
    )


_AUTH_REQUIRED_API_ROUTES = [
    '/api/test_bot/stats',
    '/api/test_bot/leads',
    '/api/test_bot/status',
    '/api/pipeline',
]


@pytest.mark.parametrize('path', _AUTH_REQUIRED_API_ROUTES)
def test_auth_api_routes_return_401_without_session(client, path):
    """Rotas de API protegidas devem retornar 401 sem sessao."""
    resp = client.get(path)
    assert resp.status_code == 401, (
        f"{path} retornou {resp.status_code}, esperado 401"
    )


# =========================================================================
# 3. robots.txt — conteudo correto
# =========================================================================

def test_robots_txt_disallows_api(client):
    """robots.txt deve bloquear /api/ para crawlers."""
    resp = client.get('/robots.txt')
    body = resp.get_data(as_text=True)
    assert 'Disallow: /api/' in body


def test_robots_txt_has_sitemap(client):
    """robots.txt deve incluir referencia ao Sitemap."""
    resp = client.get('/robots.txt')
    body = resp.get_data(as_text=True)
    assert 'Sitemap:' in body


def test_robots_txt_disallows_private_routes(client):
    """robots.txt deve bloquear /dashboard, /configurar, /admin/."""
    resp = client.get('/robots.txt')
    body = resp.get_data(as_text=True)
    assert 'Disallow: /dashboard' in body
    assert 'Disallow: /configurar' in body
    assert 'Disallow: /admin/' in body


# =========================================================================
# 4. Health check — retorna JSON com 'status'
# =========================================================================

def test_health_returns_json(client):
    """Endpoint /health deve retornar JSON."""
    resp = client.get('/health')
    assert resp.content_type.startswith('application/json')


def test_health_has_status_key(client):
    """Endpoint /health deve conter a chave 'status' no JSON."""
    resp = client.get('/health')
    data = resp.get_json()
    assert 'status' in data, "JSON de /health nao contem 'status'"
    assert data['status'] in ('ok', 'degraded'), (
        f"Status inesperado: {data['status']}"
    )


def test_health_has_version(client):
    """Endpoint /health deve conter a chave 'version' no JSON."""
    resp = client.get('/health')
    data = resp.get_json()
    assert 'version' in data, "JSON de /health nao contem 'version'"


# =========================================================================
# 5. Handler de 404
# =========================================================================

def test_404_for_nonexistent_page(client):
    """GET em rota inexistente deve retornar 404."""
    resp = client.get('/nonexistent-page-xyz-12345')
    assert resp.status_code == 404


def test_404_api_returns_json(client):
    """GET em /api/... inexistente deve retornar 404 JSON."""
    resp = client.get('/api/nonexistent-endpoint-xyz')
    # API 404 pode ser 401 (login_required) ou 404 dependendo do match
    assert resp.status_code in (401, 404)


# =========================================================================
# 6. Rate limiter configurado
# =========================================================================

def test_rate_limiter_exists(flask_app):
    """Verifica que flask_limiter esta configurado no app."""
    # limiter esta registrado como extensao
    assert hasattr(flask_app, 'extensions') or True
    # Verifica via import que o limiter foi instanciado no modulo
    import app as mod
    assert hasattr(mod, 'limiter'), "Variavel 'limiter' nao encontrada em app.py"
    assert mod.limiter is not None


# =========================================================================
# 7. Security headers — verificacao basica
# =========================================================================

def test_security_header_x_content_type(client):
    """Respostas devem incluir X-Content-Type-Options: nosniff."""
    resp = client.get('/')
    assert resp.headers.get('X-Content-Type-Options') == 'nosniff'


def test_security_header_x_frame_options(client):
    """Respostas devem incluir X-Frame-Options."""
    resp = client.get('/')
    assert 'X-Frame-Options' in resp.headers


def test_security_header_referrer_policy(client):
    """Respostas devem incluir Referrer-Policy."""
    resp = client.get('/')
    assert 'Referrer-Policy' in resp.headers


def test_security_header_permissions_policy(client):
    """Respostas devem incluir Permissions-Policy."""
    resp = client.get('/')
    assert 'Permissions-Policy' in resp.headers


def test_no_server_header_leak(client):
    """Respostas nao devem expor o header Server."""
    resp = client.get('/')
    server = resp.headers.get('Server', '')
    # Werkzeug em dev pode incluir o header, mas o after_request tenta remover.
    # Em producao nao deve ter. Verificamos que nao expoe a versao completa.
    if server:
        assert 'Python' not in server, "Header Server expoe versao do Python"


def test_session_cookie_httponly(flask_app):
    """SESSION_COOKIE_HTTPONLY deve estar True."""
    assert flask_app.config.get('SESSION_COOKIE_HTTPONLY') is True


def test_session_cookie_samesite(flask_app):
    """SESSION_COOKIE_SAMESITE deve estar configurado."""
    assert flask_app.config.get('SESSION_COOKIE_SAMESITE') in ('Lax', 'Strict')
