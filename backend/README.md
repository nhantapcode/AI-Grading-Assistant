# Backend structure

```text
app/
├── main.py                 # FastAPI assembly, middleware, error mapping
├── api/
│   ├── router.py           # API router registration
│   ├── dependencies.py     # Dependency wiring and request protection
│   └── routes/             # Authentication, members, invitations
├── core/
│   ├── config.py           # Environment settings
│   └── security.py         # Password hashing and token digests
├── db/connection.py        # Connections and transaction lifecycle
├── models/                 # Typed database records
│   ├── user.py
│   ├── auth_session.py
│   └── invitation.py
├── repositories/           # PostgreSQL queries and record mapping
│   ├── users.py
│   ├── sessions.py
│   ├── memberships.py
│   └── invitations.py
├── schemas/                # Validated API request/response contracts
├── services/               # Authentication and invitation rules
├── create_owner.py         # Bootstrap organization and first owner
└── set_password.py         # Interactive password-management command
tests/                     # Authentication and invitation integration tests
```

Routes call services; services use repositories; repositories map PostgreSQL rows to models. `models/` contains dataclasses for the existing SQL schema, using psycopg rather than an ORM. Database DDL and migrations remain in `../db/migrations/`.

Repositories do not commit. The database connection context commits successful operations and rolls back exceptions, so login rotation and password changes are atomic. Services raise domain exceptions; the API maps authentication failures to HTTP 401. Response schemas explicitly exclude password hashes.

Add future endpoints under `api/routes/`, business rules under `services/`, database records under `models/`, and SQL under `repositories/`. Register new routers in `api/router.py`. Avoid importing the FastAPI application into services, repositories, or command-line tools.

Run from this directory:

```sh
source .venv/bin/activate
uvicorn app.main:app --reload
python -m app.set_password trainer@demo.example
python -m pytest -q
```

See the root README for database and frontend setup.

Invitation endpoints:

| Method | Path | Access |
|---|---|---|
| GET | `/api/organizations` | Authenticated user; active memberships only |
| GET | `/api/organizations/{id}/members` | Owner/admin of that organization |
| POST, GET | `/api/organizations/{id}/invitations` | Owner/admin of that organization |
| POST | `/api/organizations/{id}/invitations/{invitation_id}/revoke` | Owner/admin of that organization |
| POST | `/api/invitations/resolve` | Valid invitation token |
| POST | `/api/invitations/accept` | Valid token; existing users must authenticate |

All POST endpoints require the request protection header used by the frontend. `accept` takes `token` and, for a new account, `display_name` and `password`. Token resolution returns only the invited email, role, organization name, expiry, and whether the account already exists. GET/list responses never return invitation tokens or token hashes.

## Workspace modules

Workspace routes are in `api/routes/workspace.py`; SQL is in `repositories/{workspace,assignments,files,jobs}.py`; business rules are in `services/{workspace,assignments,files,extraction}.py`. `storage/local.py` manages private objects. Run `python -m app.worker` separately for leased file-processing jobs. See [the workspace implementation guide](../doc/WORKSPACE_IMPLEMENTATION.md) for API contracts, migration instructions, configuration, and verification.
