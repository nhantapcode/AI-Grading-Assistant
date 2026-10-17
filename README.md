# AI Grading Assistant

AI Grading Assistant is a system designed to help trainers evaluate student assignments and exercises. It aims to combine Large Language Models (LLMs), semantic embeddings, reference solutions, and high-quality past submissions to provide consistent scoring and useful feedback, with trainers retaining control over final grades.

## Objectives

- Reduce the manual effort required to grade assignments.
- Give students consistent feedback that supports learning.
- Build a collection of high-quality submissions for future reference and evaluation.

## Intended workflow

1. **Create assignments and answer keys.** Trainers define assignments, scoring criteria, and reference solutions.
2. **Collect student submissions.** Students submit files, including ZIP archives, for processing.
3. **Evaluate with AI.** LLMs and embeddings compare submissions with answer keys and relevant examples to suggest scores and feedback.
4. **Review grades.** Trainers review AI feedback and adjust scores before publishing results.
5. **Reuse quality examples.** Approved high-scoring submissions become reference examples, with embeddings supporting retrieval and recommendations.

## Implementation status

The current application provides the foundation for this workflow:

- Authentication with server-side sessions and HttpOnly cookies.
- Organization membership, role-based access, and account invitations.
- Assignment editing, versioning, scoring criteria, reference uploads, and publication rules.
- Student submissions, private file storage, and background document/ZIP extraction.
- PostgreSQL schema with pgvector support for future semantic retrieval.

**AI scoring, model integration, embedding generation, exemplar recommendations, and trainer grade-review screens are planned features.** Sample AI evaluations and vectors in the development seed data are synthetic; they do not represent a working AI integration.

## Technology

| Component | Current implementation / planned integration |
|---|---|
| Backend | Python, FastAPI, Psycopg, Pydantic |
| Frontend | React, Vite, Tailwind CSS |
| Database | PostgreSQL 17 with pgvector |
| Authentication | Server-side sessions with HttpOnly cookies |
| File handling | Private local storage and a background extraction worker |
| Local infrastructure | Docker Compose for PostgreSQL |
| AI evaluation (planned) | OpenAI GPT, Gemini, or an equivalent LLM |
| Embeddings (planned) | An embedding provider for semantic comparison and retrieval |
| Cloud storage (optional, planned) | AWS S3, Google Cloud Storage, or Azure Blob Storage |

## Repository structure

```text
backend/
  app/             FastAPI routes, services, repositories, schemas, and worker
  tests/           Backend integration tests
  .env.example     Example environment configuration
frontend/
  src/             React pages, components, layouts, and API helpers
db/
  migrations/      Ordered database migrations
  sample_data.sql  Synthetic development data
  smoke.sql        Rollback-only schema checks
compose.yaml       Local PostgreSQL service
```

See [backend/README.md](backend/README.md) for backend module responsibilities.

## Run locally

### Prerequisites

- Python 3.10 or later.
- Node.js 22.12+ or 24 and npm.
- Docker with Docker Compose.

### 1. Start PostgreSQL

From the repository root:

```sh
docker compose up -d --wait
```

A fresh database volume applies all SQL files in `db/migrations/` automatically. For an existing volume, apply only unapplied migrations once, in filename order. Preserve existing volumes and data.

### 2. Set up the backend

```sh
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Review `.env` for your local settings. Create the first organization owner:

```sh
python -m app.create_owner --organization "Training Center" --email owner@example.com --name "Organization Owner"
```

The command prompts for a password. With the default local configuration, start the API:

```sh
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --env-file .env
```

The owner command and worker read environment variables directly. If you customize `.env`, export the same settings into their shells before running them. The API and worker must share database and storage settings.

### 3. Start the upload worker

In a separate terminal:

```sh
cd backend
source .venv/bin/activate
python -m app.worker
```

Uploads remain pending until the worker processes them. Uploaded files are stored in `backend/.storage/` by default and are excluded from Git.

### 4. Start the frontend

In another terminal:

```sh
cd frontend
npm ci
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) and sign in with the owner account. Vite proxies `/api` requests to port 8000. Interactive API documentation is available at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

Owners can invite admins and trainers; admins can invite trainers. Invitation links must currently be shared manually.

## Optional sample data

From the repository root, load synthetic development records:

```sh
docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U grading -d grading < db/sample_data.sql
```

The sample includes assignments, references, submissions, and illustrative grading records. To sign in with the sample trainer, set a password from `backend/` with the virtual environment activated:

```sh
python -m app.set_password trainer@demo.example
```

## Checks

Run backend integration tests against PostgreSQL with all migrations applied:

```sh
cd backend
source .venv/bin/activate
python -m pytest -q
```

Run frontend tests and create a production bundle:

```sh
cd frontend
npm test
npm run build
```

Run the rollback-only database smoke checks from the repository root:

```sh
docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U grading -d grading < db/smoke.sql
```

## Deployment configuration

Use `backend/.env.example` as the configuration reference. Serve the frontend and API from one HTTPS origin, set `COOKIE_SECURE=true`, and set `FRONTEND_ORIGIN` to that origin. Configure a dedicated database role with appropriate restrictions; the Compose bootstrap credentials are for local development.

Keep credentials, session tokens, and uploaded student files out of Git. Private file access and organization requests must remain authorized, and uploaded code must never be executed.
