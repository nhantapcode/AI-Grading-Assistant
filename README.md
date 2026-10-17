# AI Grading Assistant database

This repository contains the PostgreSQL schema described in [the database design](doc/DB_SCHEMA_DESGIN.md), a React + Tailwind frontend in `frontend/`, and a FastAPI backend in `backend/`. The app supports login/logout, invitations, Owner account management, versioned assignments, private uploads, document/ZIP extraction, and student submissions. AI grading, embeddings, and grade-review screens are the next stage.

## Owner and Trainer workspace

See [doc/WORKSPACE_IMPLEMENTATION.md](doc/WORKSPACE_IMPLEMENTATION.md) for the new screens, migration `005`, upload worker startup, supported file types, limits, and verification commands. Start `python -m app.worker` in a separate backend terminal so uploaded files can become ready.

## Login and logout app

Backend modules are organized into API routes, services, database models, repositories, schemas, configuration, and connection management. See [backend/README.md](backend/README.md) for the structure and responsibilities.

Use Node.js 20.19+ (or 22.12+) and Python 3.10+. Start PostgreSQL and import the sample data using the commands below, then run:

```sh
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.set_password trainer@demo.example
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The password command prompts for a password and replaces the sample account's non-login placeholder. It also revokes existing sessions. No fixed demo password is supplied.

In a second terminal:

```sh
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** and sign in as `trainer@demo.example` with the password you set. The account screen includes a **Sign out** button. Reloading restores a valid session. Failed login and connection errors appear on screen.

Vite proxies `/api` to FastAPI at port 8000. Endpoints are `POST /api/auth/login`, `GET /api/auth/me`, and `POST /api/auth/logout`. API docs are at http://127.0.0.1:8000/docs. POST and PATCH requests require `X-Requested-With: grading-web`; the frontend supplies it automatically.

The backend reads environment variables listed in `backend/.env.example`. To load a copied `backend/.env` file, start Uvicorn with `--env-file .env`. Sessions last eight hours by default; only a SHA-256 token digest is stored in `auth_sessions`. The browser cookie is HttpOnly and SameSite=Lax. Logout revokes the database session and clears the cookie.

For deployment, serve the frontend and `/api` from one HTTPS origin, set `COOKIE_SECURE=true`, set `FRONTEND_ORIGIN` to that origin, and configure `DATABASE_URL` with a dedicated database role. The development bootstrap role is not suitable for production. Add shared login and invitation rate limiting before exposing this service publicly. Member and invitation APIs enforce organization permissions; future grading endpoints must implement their own tenant authorization.

Run the backend integration tests against a database with the migrations applied:

```sh
cd backend
.venv/bin/python -m pytest -q
```

Most tests use rollback transactions. The concurrency test creates isolated temporary accounts and an organization, then removes only those records. Existing data is preserved. Run `npm test` for component tests and `npm run build` for the production bundle from `frontend/`. Node.js 22.12+ or 24 is recommended for test tooling.

## Account creation through invitations

For an existing database volume, apply the invitation migration once (it has already been applied to the local database during implementation):

```sh
docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U grading -d grading < db/migrations/004_account_invitations.sql
```

Fresh database volumes apply all migrations automatically. Create the first owner and a new organization from `backend/`:

```sh
source .venv/bin/activate
python -m app.create_owner --organization "Training Center" --email owner@example.com --name "Organization Owner"
```

The command prompts for a password (12–1024 characters) and confirmation. It creates the organization, user, and owner membership in one transaction. It rejects existing emails without changing their account. The sample trainer remains a trainer and cannot invite members.

1. Sign in with the owner account at http://localhost:5173.
2. In **Organization members**, choose an organization, enter an email, choose a role, and click **Create invitation**.
3. Copy the generated link and share it manually. It is shown only when created and expires after 48 hours. Automatic email delivery is not included.
4. Open the link. A new user enters their name, password, and password confirmation. An existing user signs in with the invited email and confirms acceptance.
5. After acceptance, a new user signs in normally. Owners/admins can see the member and invitation lists or cancel pending invitations.

Owners can invite admins or trainers; admins can invite trainers. Trainers cannot manage members. Invites become unusable after acceptance, expiry, cancellation, organization suspension, or loss of the inviter's required permissions. Existing memberships are preserved; invitation acceptance does not change or reactivate their roles.

Invitation tokens are generated randomly, stored as SHA-256 digests, and included in the link fragment. The browser submits the token in a POST body. Acceptance locks the invitation row and creates the user, membership, and acceptance timestamp in a single transaction, preventing replay and concurrent double use. Cookies now use the `/api` path; sign in again if you have a session created before this change.

## Run locally

```sh
docker compose up -d --wait
docker compose exec postgres psql -U grading -d grading
```

Run the rollback-only schema smoke test with:

```sh
docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U grading -d grading < db/smoke.sql
```

The `pgvector/pgvector:pg17` image runs the SQL migrations in `db/migrations` **only when the database volume is first created**. For an existing volume, apply a new migration explicitly with `psql`; do not delete a volume containing data. The Compose password and exposed port are for local development only.

The initial embedding table uses 1,536 dimensions and cosine distance. Insert an `embedding_profiles` row matching that dimension before writing vectors. Another embedding dimension requires a new migration and a separate embedding table or partition.

## Sample data

The development database contains synthetic sample data in `db/sample_data.sql`. It includes a trainer, two students, a published assignment with two rubric criteria, an answer key, two submissions, a simulated AI evaluation, a trainer-approved grade, and an anonymized exemplar with demo vectors. The AI result and vectors are illustrative; no model or storage provider was called. The script can be run again without duplicating records:

```sh
docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U grading -d grading < db/sample_data.sql
```

Connect from DBeaver using the **PostgreSQL** driver:

| Setting | Value |
|---|---|
| Host | `localhost` |
| Port | `5432` |
| Database | `grading` |
| Username | `grading` |
| Password | `grading_dev_only` |

Open `grading` → `Schemas` → `public` → `Tables`. Right-click a table and select **View Data**. A useful starting query is:

```sql
SELECT s.display_name, a.title, sub.status, g.total_score, g.feedback
FROM submissions sub
JOIN students s ON (s.organization_id, s.id) = (sub.organization_id, sub.student_id)
JOIN assignment_versions v ON (v.organization_id, v.id) = (sub.organization_id, sub.assignment_version_id)
JOIN assignments a ON (a.organization_id, a.id) = (v.organization_id, v.assignment_id)
LEFT JOIN grade_revisions g ON (g.organization_id, g.id) = (sub.organization_id, sub.current_published_grade_id)
WHERE sub.organization_id = '10000000-0000-0000-0000-000000000001';
```

For tenant-scoped application queries, use a database role without `BYPASSRLS` or table ownership privileges and set the tenant in each transaction:

```sql
BEGIN;
SET LOCAL app.organization_id = '00000000-0000-0000-0000-000000000001';
-- tenant queries here
COMMIT;
```

The bootstrap `grading` role owns the schema and therefore bypasses row-level security. Do not use it for application traffic. Applications must also authorize the authenticated user against an active membership, use a dedicated role with restricted column access for sensitive prompts and student data, and write audit/outbox records for relevant changes.

Publication guards enforce rubric totals, usable references, grade coverage, current-grade consistency, and published-content immutability. Future grading APIs and workers must implement grading-specific idempotency, authorization, anonymization review, and event delivery described in the design; the upload/submission workflows implement their own transaction and lease handling.
