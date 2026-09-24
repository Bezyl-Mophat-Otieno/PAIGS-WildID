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
