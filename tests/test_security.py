# -*- coding: utf-8 -*-
"""
Testes de seguranca baseados em analise estatica de arquivos.

Estes testes NAO precisam de DATABASE_URL — inspecionam o codigo-fonte
e templates diretamente no disco.
"""
import os
import re
import glob

# Diretorio raiz do projeto
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
_TEMPLATES_DIR = os.path.join(_ROOT, 'templates')
_APP_PY = os.path.join(_ROOT, 'app.py')


def _read_file(path):
    """Le conteudo de um arquivo com encoding utf-8."""
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def _all_templates():
    """Retorna lista de caminhos de todos os .html em templates/."""
    return glob.glob(os.path.join(_TEMPLATES_DIR, '*.html'))


# =========================================================================
# 1. SECRET_KEY — logica de enforcement existe
# =========================================================================

def test_secret_key_fatal_in_production():
    """app.py deve chamar sys.exit() se SECRET_KEY nao definida em producao."""
    source = _read_file(_APP_PY)
    # Verifica que existe checagem RAILWAY_ENVIRONMENT/RENDER/FLY_APP_NAME
    assert 'RAILWAY_ENVIRONMENT' in source, (
        "Sem checagem de RAILWAY_ENVIRONMENT para SECRET_KEY"
    )
    # Verifica que sys.exit e chamado no bloco de SECRET_KEY
    # O padrao: se SECRET_KEY vazio E ambiente de producao -> sys.exit(1)
    assert 'sys.exit(1)' in source, (
        "Sem sys.exit(1) para SECRET_KEY ausente em producao"
    )


def test_secret_key_rejects_default_value():
    """app.py deve rejeitar o valor default 'mv-saas-2025-change-in-prod'."""
    source = _read_file(_APP_PY)
    assert 'mv-saas-2025-change-in-prod' in source, (
        "Valor default de SECRET_KEY nao esta sendo verificado"
    )
    # Confirma que o valor default e tratado como vazio (gera temporario ou fatal)
    # Procura o padrao: if not _secret or _secret == 'mv-saas-2025-change-in-prod'
    assert re.search(
        r"if\s+not\s+_secret\s+or\s+_secret\s*==\s*'mv-saas-2025-change-in-prod'",
        source
    ), "SECRET_KEY default nao e tratada como invalida"


def test_secret_key_generates_temp_for_dev():
    """Em dev (sem variavel de producao), deve gerar SECRET_KEY temporaria."""
    source = _read_file(_APP_PY)
    assert 'secrets.token_hex' in source, (
        "Sem geracao de SECRET_KEY temporaria via secrets.token_hex"
    )


# =========================================================================
# 2. GA Measurement ID — sem hardcode em templates
# =========================================================================

def test_no_hardcoded_ga_id_in_templates():
    """Templates nao devem conter GA ID hardcoded (G-NGSNSF3SPM).

    O ID deve ser passado via variavel ga_id do contexto Jinja,
    nunca diretamente no HTML.
    """
    ga_id = 'G-NGSNSF3SPM'
    violations = []
    for tpl_path in _all_templates():
        content = _read_file(tpl_path)
        if ga_id in content:
            fname = os.path.basename(tpl_path)
            violations.append(fname)
    assert not violations, (
        f"GA ID hardcoded encontrado em templates: {', '.join(violations)}. "
        "Use a variavel ga_id do contexto Jinja."
    )


def test_ga_id_comes_from_env_in_app():
    """app.py deve ler GA_MEASUREMENT_ID de variavel de ambiente."""
    source = _read_file(_APP_PY)
    assert "os.environ.get('GA_MEASUREMENT_ID'" in source, (
        "GA_MEASUREMENT_ID nao e lido de variavel de ambiente"
    )


# =========================================================================
# 3. target="_blank" deve ter rel="noopener"
# =========================================================================

def test_target_blank_has_rel_noopener():
    """Todo link com target="_blank" deve ter rel contendo "noopener".

    Excecao: templates de e-mail (email_*.html) onde o contexto e
    diferente (clients de e-mail nao tem window.opener).
    """
    # Regex para encontrar tags <a> com target="_blank"
    # Captura a tag inteira para inspecionar rel=
    pattern = re.compile(
        r'<a\s[^>]*target=["\']_blank["\'][^>]*>',
        re.IGNORECASE | re.DOTALL
    )
    rel_pattern = re.compile(r'rel=["\'][^"\']*noopener[^"\']*["\']', re.IGNORECASE)

    violations = []
    for tpl_path in _all_templates():
        fname = os.path.basename(tpl_path)
        # Pular templates de e-mail e backups locais
        if fname.startswith('email_') or 'Notebook' in fname:
            continue
        content = _read_file(tpl_path)
        for match in pattern.finditer(content):
            tag = match.group(0)
            if not rel_pattern.search(tag):
                # Extrair numero da linha para facilitar debug
                line_num = content[:match.start()].count('\n') + 1
                violations.append(f"{fname}:{line_num}")

    assert not violations, (
        f"Links com target=\"_blank\" sem rel=\"noopener\" encontrados em:\n"
        + '\n'.join(f"  - {v}" for v in violations)
    )


# =========================================================================
# 4. Cookie consent — padrao existe em templates
# =========================================================================

def test_cookie_consent_pattern_in_landing():
    """Template principal (landing.html) deve verificar cookie_consent."""
    landing = os.path.join(_TEMPLATES_DIR, 'landing.html')
    assert os.path.exists(landing), "landing.html nao encontrado"
    content = _read_file(landing)
    assert 'cookie_consent' in content, (
        "Padrao cookie_consent nao encontrado em landing.html"
    )


def test_cookie_consent_banner_exists():
    """Deve existir um template de cookie banner."""
    banner = os.path.join(_TEMPLATES_DIR, 'cookie_banner.html')
    assert os.path.exists(banner), (
        "Template cookie_banner.html nao encontrado"
    )
    content = _read_file(banner)
    assert 'cookie_consent' in content
    # Deve ter opcao de aceitar e rejeitar
    assert 'accepted' in content, "Banner nao tem opcao de aceitar"
    assert 'rejected' in content, "Banner nao tem opcao de rejeitar"


def test_cookie_consent_in_key_templates():
    """Templates que carregam GA devem checar cookie_consent antes."""
    # Templates que passam ga_id e portanto devem checar consentimento
    key_templates = ['dashboard.html', 'precos.html', 'blog.html']
    missing = []
    for tpl_name in key_templates:
        tpl_path = os.path.join(_TEMPLATES_DIR, tpl_name)
        if not os.path.exists(tpl_path):
            continue
        content = _read_file(tpl_path)
        if 'cookie_consent' not in content:
            missing.append(tpl_name)
    assert not missing, (
        f"Templates sem checagem de cookie_consent: {', '.join(missing)}"
    )


# =========================================================================
# 5. Security headers — padrao no after_request
# =========================================================================

def test_security_headers_after_request_exists():
    """app.py deve ter after_request que seta headers de seguranca."""
    source = _read_file(_APP_PY)
    assert '@app.after_request' in source, (
        "Sem decorator @app.after_request para headers de seguranca"
    )
    assert 'X-Content-Type-Options' in source
    assert 'X-Frame-Options' in source
    assert 'Referrer-Policy' in source


def test_server_header_removed():
    """app.py deve remover o header Server na resposta."""
    source = _read_file(_APP_PY)
    # Procura pop('Server', None) ou similar
    assert re.search(r"headers\.pop\(['\"]Server['\"]", source), (
        "Header Server nao esta sendo removido das respostas"
    )


def test_csrf_protection_exists():
    """app.py deve ter protecao CSRF no before_request."""
    source = _read_file(_APP_PY)
    assert '@app.before_request' in source, "Sem before_request"
    assert '_csrf' in source, "Sem logica de CSRF token"
    assert 'compare_digest' in source, (
        "Sem hmac.compare_digest para validacao CSRF"
    )


# =========================================================================
# 6. Criptografia de campos sensiveis
# =========================================================================

def test_encryption_pattern_exists():
    """app.py deve ter funcoes de criptografia para campos sensiveis."""
    source = _read_file(_APP_PY)
    assert 'def _encrypt_field' in source, "Sem funcao _encrypt_field"
    assert 'def _decrypt_field' in source, "Sem funcao _decrypt_field"
    assert 'Fernet' in source, "Sem uso de Fernet para criptografia"


def test_sensitive_fields_defined():
    """Lista de campos sensiveis deve existir."""
    source = _read_file(_APP_PY)
    assert '_SENSITIVE_FIELDS' in source, "Sem definicao de _SENSITIVE_FIELDS"
    # Verifica que campos criticos estao na lista
    for field in ('smtp_password', 'linkedin_password'):
        assert field in source, f"Campo sensivel {field} nao definido"
