# PAIGS WildID

Wildlife DNA species-identification pipeline. See [`CLAUDE.md`](./CLAUDE.md) for the full
build plan, stage-by-stage pipeline spec, and API design. This file covers day-to-day
local setup for running the backend.

## Running the backend locally (no Docker)

```bash
cd backend
python3 -m venv .venv        # first time only
source .venv/bin/activate    # every new terminal session
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Check you're in the right virtualenv at any point with:

```bash
echo $VIRTUAL_ENV   # prints the venv path if active, empty if not
which python         # should resolve inside backend/.venv/bin/ when active
```

Once running, the API is at `http://127.0.0.1:8000`, with interactive Swagger UI at
`http://127.0.0.1:8000/docs` (ReDoc at `/redoc`).

> BLAST+ (needed from Stage 9 onward) is a separate compiled binary, not a pip package —
> it isn't installed by `requirements.txt`. It's baked into the Docker image (see
> `backend/Dockerfile`); for a non-Docker local setup it must be installed separately.

## Running with Docker Compose

There are two compose files at the repo root:

- **`docker-compose.yml`** — the base service definition: builds the backend image
  (with BLAST+ baked in per `backend/Dockerfile`), exposes port 8000, and persists
  uploaded files/run artifacts in a named volume (`wildid-storage`).
- **`docker-compose.override.yml`** — dev-only additions layered on top automatically:
  bind-mounts `backend/` into the container and runs `uvicorn --reload`, so local code
  edits apply immediately without rebuilding the image.

**Local development** (override applied automatically):

```bash
docker compose up --build
```

Edit code freely afterward — no rebuild needed. Rebuild (`--build`) again only when
`backend/requirements.txt` changes, since new dependencies still need installing into
the image.

**Deploying** (override explicitly excluded, clean production config):

```bash
docker compose -f docker-compose.yml up --build -d
```

Either way, the API/Swagger UI is reachable at `http://localhost:8000/docs`.

### Storage note

Uploaded AB1 files and run artifacts live in the `wildid-storage` named Docker volume,
local to whichever single machine runs the container. That's sufficient for a
prototype/single-server deployment — data survives container restarts and redeploys as
long as you don't run `docker compose down -v` (the `-v` deletes named volumes). It stops
being enough once you need multiple server instances (each would have its own,
non-shared volume) or move to a host without persistent local disk — at that point,
switch to external object storage (e.g. S3) instead.

## Authentication

Invite-only accounts with two simple roles (`admin`, `analyst`), driving what the
future frontend shows each user. There's no self-registration endpoint — every account
either is the seeded default admin, or was created by an admin via `POST /admin/invite`.

### Default admin account

A single admin account is seeded automatically the first time anyone hits
`POST /auth/login` — no separate setup step. Its credentials come from environment
variables, falling back to a clearly-labeled prototype default if unset:

```bash
export PAIGS_ADMIN_EMAIL=admin@paigs.local       # fallback if unset
export PAIGS_ADMIN_PASSWORD=paigs-admin-dev      # fallback if unset -- change this outside local prototyping
```

Also set `PAIGS_JWT_SECRET` outside of local prototyping — it defaults to an
intentionally-insecure placeholder (see `backend/app/auth/security.py`).

### Logging in

`POST /auth/login` takes standard OAuth2 form fields (`username`, `password` —
`username` doubles as the email), not JSON — this is what makes Swagger UI's
"Authorize" button work out of the box at `/docs`. It returns a bearer access token;
send it as `Authorization: Bearer <token>` on every other authenticated request.

### Inviting a user

An admin's only account-management feature for now, on purpose (kept simple):
`POST /admin/invite` with `{"email": "...", "role": "analyst"}` creates the account and
returns a one-time `temporary_password` in the response. Email delivery is stubbed —
nothing is actually sent (`backend/app/auth/email_stub.py` just logs what would have
gone out) — so the admin copies `temporary_password` from the response and shares it
with the invited user directly. `GET /admin/users` lists every account (never exposing
a password) so an admin can confirm who's been invited.

Existing pipeline endpoints (`/runs`, `/config`, `/reference-database`) are **not** yet
gated behind a login — this first pass adds the accounts/roles/tokens plumbing itself;
requiring auth on those endpoints is a deliberate next step, not done here.
