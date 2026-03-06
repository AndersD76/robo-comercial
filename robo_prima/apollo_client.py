# -*- coding: utf-8 -*-
"""
Apollo.io API Client — PrismaBiz
Busca e enriquecimento de leads via Apollo.io API.
Complementa a prospecção do LinkedIn com dados de contato
(email, telefone, empresa) sem precisar de browser.
"""

import asyncio
import json
from datetime import datetime, timezone, timedelta

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

from config import (
    APOLLO_API_KEY, APOLLO_HABILITADO,
    APOLLO_MAX_BUSCAS_DIA, APOLLO_FILTROS,
    LINKEDIN_CARGOS_ALVO,
)

try:
    from database import (
        salvar_lead_linkedin, salvar_empresa,
        get_connection, registrar_log,
    )
    HAS_DB = True
except ImportError:
    HAS_DB = False

_BRT = timezone(timedelta(hours=-3))
_API_BASE = 'https://api.apollo.io/api/v1'


class ApolloClient:
    """
    Cliente assíncrono para a API do Apollo.io.
    Busca leads por título, indústria, localização e porte.
    """

    def __init__(self):
        self.api_key = APOLLO_API_KEY
        self.buscas_hoje = 0
        self._ultimo_dia = -1

    def _log(self, msg: str, tipo: str = 'info'):
        ts = datetime.now(_BRT).strftime('%H:%M:%S')
        icone = {
            'info': 'ℹ', 'sucesso': '✓',
            'aviso': '⚠', 'erro': '✗'
        }.get(tipo, 'ℹ')
        print(
            f"[Apollo {ts}] {icone} {msg}",
            flush=True
        )
        if HAS_DB:
            try:
                registrar_log(tipo, f"[Apollo] {msg}")
            except Exception:
                pass

    def disponivel(self) -> bool:
        """Verifica se Apollo está configurado e disponível."""
        if not APOLLO_HABILITADO:
            return False
        if not self.api_key:
            return False
        if not HAS_HTTPX:
            self._log(
                "httpx não instalado — pip install httpx",
                'aviso'
            )
            return False
        return True

    def _reset_diario(self):
        dia = datetime.now(_BRT).day
        if dia != self._ultimo_dia:
            self._ultimo_dia = dia
            self.buscas_hoje = 0

    async def buscar_leads(
        self,
        keyword: str = '',
        pagina: int = 1,
        por_pagina: int = 25,
    ) -> list[dict]:
        """
        Busca leads no Apollo.io por título/keyword.
        Retorna lista no mesmo formato do LinkedIn bot:
        [{nome, cargo, empresa, url_perfil, email, telefone}]
        """
        if not self.disponivel():
            return []

        self._reset_diario()
        if self.buscas_hoje >= APOLLO_MAX_BUSCAS_DIA:
            self._log("Limite diário Apollo atingido", 'aviso')
            return []

        filtros = APOLLO_FILTROS
        payload = {
            'page': pagina,
            'per_page': por_pagina,
            'person_titles': filtros.get('titulos', []),
            'person_locations': filtros.get('localizacao', ['Brazil']),
        }

        if keyword:
            payload['q_keywords'] = keyword

        porte_min = filtros.get('porte_min')
        porte_max = filtros.get('porte_max')
        if porte_min or porte_max:
            org_ranges = []
            if porte_min:
                org_ranges.append(str(porte_min))
            if porte_max:
                org_ranges.append(str(porte_max))
            payload['organization_num_employees_ranges'] = [
                f"{porte_min or 1},{porte_max or 10000}"
            ]

        industrias = filtros.get('industrias', [])
        if industrias:
            payload['q_organization_keyword_tags'] = industrias

        self._log(
            f"Buscando leads: \"{keyword}\" "
            f"(pág {pagina})..."
        )

        resultados = []
        try:
            async with httpx.AsyncClient(
                timeout=30,
                headers={'X-Api-Key': self.api_key, 'Content-Type': 'application/json'},
            ) as client:
                resp = await client.post(
                    f'{_API_BASE}/mixed_people/search',
                    json=payload,
                )
                self.buscas_hoje += 1

                if resp.status_code == 401:
                    self._log(
                        "API key inválida — verifique APOLLO_API_KEY",
                        'erro'
                    )
                    return []
                if resp.status_code == 429:
                    self._log(
                        "Rate limit Apollo — aguardando...",
                        'aviso'
                    )
                    await asyncio.sleep(60)
                    return []
                if resp.status_code != 200:
                    self._log(
                        f"Erro API: {resp.status_code} — "
                        f"{resp.text[:200]}",
                        'erro'
                    )
                    return []

                data = resp.json()
                people = data.get('people', [])
                total = data.get(
                    'pagination', {}
                ).get('total_entries', 0)
                self._log(
                    f"Apollo retornou {len(people)} de "
                    f"{total} total"
                )

                for person in people:
                    nome = person.get('name', '')
                    cargo = person.get('title', '')
                    empresa = (
                        person.get('organization', {})
                        .get('name', '')
                    )
                    linkedin_url = (
                        person.get('linkedin_url', '')
                    )
                    email = person.get('email', '')
                    telefone = ''
                    phones = person.get(
                        'phone_numbers', []
                    )
                    if phones:
                        telefone = phones[0].get(
                            'sanitized_number', ''
                        )

                    if not nome:
                        continue

                    # Filtra por cargo-alvo
                    if not self._cargo_alvo(cargo):
                        continue

                    # Dados da empresa
                    org = person.get('organization', {})
                    site = org.get('website_url', '')
                    setor = org.get('industry', '')
                    porte = org.get(
                        'estimated_num_employees', 0
                    )
                    cidade = person.get('city', '')
                    estado = person.get('state', '')

                    lead = {
                        'nome': nome,
                        'cargo': cargo,
                        'empresa': empresa,
                        'url_perfil': linkedin_url or '',
                        'email': email,
                        'telefone': telefone,
                        'site': site,
                        'setor': setor,
                        'porte': porte,
                        'cidade': cidade,
                        'estado': estado,
                        'termo_busca': f'[Apollo] {keyword}',
                        'fonte': 'apollo',
                    }
                    resultados.append(lead)

                    self._log(
                        f"  → {nome} | {cargo} "
                        f"@ {empresa}"
                        f"{' | ' + email if email else ''}"
                    )

        except httpx.TimeoutException:
            self._log("Timeout na API Apollo", 'erro')
        except Exception as e:
            self._log(f"Erro Apollo: {e}", 'erro')

        self._log(
            f"Apollo: {len(resultados)} leads qualificados"
        )
        return resultados

    def _cargo_alvo(self, cargo: str) -> bool:
        """Verifica se o cargo é relevante."""
        if not cargo:
            return False
        cargo_lower = cargo.lower()
        return any(
            c.lower() in cargo_lower
            for c in LINKEDIN_CARGOS_ALVO
        )

    async def enriquecer_lead(
        self, email: str = '', linkedin_url: str = ''
    ) -> dict | None:
        """
        Enriquece um lead existente buscando dados no Apollo.
        Pode buscar por email ou URL do LinkedIn.
        Retorna dict com dados enriquecidos ou None.
        """
        if not self.disponivel():
            return None

        self._reset_diario()
        if self.buscas_hoje >= APOLLO_MAX_BUSCAS_DIA:
            return None

        payload = {}
        if email:
            payload['email'] = email
        elif linkedin_url:
            payload['linkedin_url'] = linkedin_url
        else:
            return None

        try:
            async with httpx.AsyncClient(
                timeout=30,
                headers={'X-Api-Key': self.api_key, 'Content-Type': 'application/json'},
            ) as client:
                resp = await client.post(
                    f'{_API_BASE}/people/match',
                    json=payload,
                )
                self.buscas_hoje += 1

                if resp.status_code != 200:
                    return None

                data = resp.json()
                person = data.get('person')
                if not person:
                    return None

                org = person.get('organization', {})
                return {
                    'nome': person.get('name', ''),
                    'cargo': person.get('title', ''),
                    'empresa': org.get('name', ''),
                    'email': person.get('email', ''),
                    'telefone': (
                        person.get('phone_numbers', [{}])[0]
                        .get('sanitized_number', '')
                        if person.get('phone_numbers')
                        else ''
                    ),
                    'linkedin_url': (
                        person.get('linkedin_url', '')
                    ),
                    'site': org.get('website_url', ''),
                    'setor': org.get('industry', ''),
                    'porte': org.get(
                        'estimated_num_employees', 0
                    ),
                    'cidade': person.get('city', ''),
                    'estado': person.get('state', ''),
                }
        except Exception as e:
            self._log(
                f"Erro enriquecimento: {e}", 'erro'
            )
            return None

    async def salvar_leads_no_pipeline(
        self, leads: list[dict]
    ) -> int:
        """
        Salva leads do Apollo no banco para o pipeline
        LinkedIn (conexão) ou WhatsApp (se tem telefone).
        Retorna quantidade salva.
        """
        if not HAS_DB:
            return 0

        salvos = 0
        for lead in leads:
            try:
                # Salva como lead LinkedIn se tem URL
                if lead.get('url_perfil'):
                    salvar_lead_linkedin(lead, 'encontrado')
                    salvos += 1

                # Se tem telefone, salva também como empresa
                # para o pipeline WhatsApp
                telefone = lead.get('telefone', '')
                if telefone and lead.get('empresa'):
                    empresa_data = {
                        'nome': lead['empresa'],
                        'telefone': telefone,
                        'email': lead.get('email', ''),
                        'site': lead.get('site', ''),
                        'segmento': lead.get('setor', ''),
                        'contato_nome': lead.get('nome', ''),
                        'contato_cargo': lead.get('cargo', ''),
                        'fonte': 'apollo',
                        'cidade': lead.get('cidade', ''),
                        'estado': lead.get('estado', ''),
                    }
                    salvar_empresa(empresa_data)
                    salvos += 1
            except Exception as e:
                self._log(
                    f"Erro salvando lead: {e}", 'aviso'
                )

        if salvos:
            self._log(
                f"{salvos} leads Apollo salvos no pipeline",
                'sucesso'
            )
        return salvos


# Palavras-chave para busca rotativa no Apollo
APOLLO_KEYWORDS = [
    'ISO 9001 qualidade',
    'gestão qualidade industrial',
    'metalurgia qualidade',
    'manufacturing quality Brazil',
    'indústria alimentos qualidade',
    'autopeças qualidade',
    'plásticos borracha qualidade',
    'química farmacêutica qualidade',
    'melhoria contínua produção',
    'SGQ auditoria interna',
]
