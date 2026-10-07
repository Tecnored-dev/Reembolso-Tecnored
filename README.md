# Reembolso · Tecnored

Aplicação web para solicitação, aprovação e pagamento de reembolsos:

- **Alimentação**, que substitui o portal ARGOS.
- **Viagem** (reembolso e adiantamento), que substitui o fluxo do Power Automate.

O colaborador abre a solicitação e escolhe o gestor. O gestor aprova, e o registro guarda quem aprovou e quando. O financeiro faz o pagamento. O status fica visível para todos durante todo o processo.

Segue o padrão TI da Tecnored (repositório `tecnored-dev/Hello-World`).

## Stack

| Camada   | Tecnologia |
|----------|------------|
| Backend  | FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL 17 |
| Frontend | React 18 · Vite 5 · TypeScript · CSS Modules · Nginx |
| Login    | Azure AD (MSAL) + Cloudflare Access SSO |
| Deploy   | Docker · GitHub Actions · Dokploy |

## Rodando localmente

Pré-requisito: Docker Desktop.

```bash
copy .env.example .env
copy docker-compose.override.yml.example docker-compose.override.yml
docker compose up --build
```

- Frontend: http://localhost:8080
- API: http://localhost:8081 (docs em `/docs`)
- Sem Azure configurado, use **"Entrar como dev (local)"**. Esse login só existe com `APP_ENV=local`.

Para simular outros papéis, acesse `http://localhost:8081/dev/login?email=voce@tecnored.com.br&nome=Voce&papeis=gestor,financeiro`.

## Testes

```bash
# backend
cd backend
pip install -r requirements.txt -r requirements-dev.txt
pytest
ruff check . && ruff format --check .

# frontend
cd frontend
npm ci
npm run lint && npm test && npm run build
```

## Papéis

Os papéis vêm dos grupos do Azure AD, configurados em `AZURE_GROUP_GESTOR`, `AZURE_GROUP_FINANCEIRO` e `AZURE_GROUP_ADMIN`. Todo usuário logado tem o papel **colaborador**.

## Arquivos (notas fiscais)

O armazenamento fica isolado em `backend/app/storage/`. Hoje só existe o backend `local`, que grava no volume `/data`. S3 ou SharePoint entram depois, quando a TI definir qual usar. Arquivos **não** ficam no banco.

## Fluxo de branches

`feature/*` → PR para `hml` (Squash merge pelo Admin) → PR `hml` → `main`.
O título do PR define a versão (semantic-release): `feat:`, `fix:`, etc.
