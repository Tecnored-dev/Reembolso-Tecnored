"""SSO via Cloudflare Access (acesso externo) — portado do Hello-World (seção 17.1).

Só roda com CF_ACCESS_TEAM_DOMAIN configurado. O Cloudflare valida a sessão
no endpoint get-identity; aqui só repassamos o JWT que a requisição trouxe.
"""

from __future__ import annotations

import httpx
from fastapi import Request

from app.config import Settings


async def identidade_cloudflare(request: Request, settings: Settings) -> dict | None:
    if not settings.cf_access_team_domain:
        return None
    jwt = request.headers.get("Cf-Access-Jwt-Assertion") or request.cookies.get("CF_Authorization")
    if not jwt:
        return None
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://{settings.cf_access_team_domain}/cdn-cgi/access/get-identity",
                headers={"Cf-Access-Jwt-Assertion": jwt},
                cookies={"CF_Authorization": jwt},
                timeout=5.0,
            )
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None
    return resp.json()
