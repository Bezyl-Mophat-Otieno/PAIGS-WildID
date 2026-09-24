# PAIGS WildID -- backend image.
#
# Bakes in BLAST+ (per CLAUDE.md: "The server/Docker image needs the
# BLAST+ binary baked in, not just listed in requirements.txt" -- BLAST+
# is a separate compiled program, not a pip-installable package). With
# root available in a normal Docker build, that's a plain `apt-get
# install` -- this image does NOT need the no-root extraction workaround
# used to prototype and test Stage 9 in a sandboxed dev environment
# without root access (see claude/stage-8-9-status.md for that story;
# app/pipeline/blast.py's `_find_blast_binary` still supports that
# workaround's install layout as a fallback, purely for that dev case).
#
# The curated species reference database used by Stage 9's BLAST search
# is intentionally NOT baked into this image. Per CLAUDE.md, it's a
# domain-expert deliverable, built and versioned independently of the
# application, and expected to change on its own schedule. Mount it as a
# volume at runtime instead -- see docker-compose.yml alongside this file.

FROM python:3.10-slim

# ncbi-blast+ pulls in its own runtime library dependencies (libmbedtls
# and friends) via normal apt dependency resolution here -- no manual
# extraction needed, unlike the no-root dev workaround.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ncbi-blast+ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Runtime configuration (see app/db.py and app/storage.py for defaults):
#   PAIGS_DATABASE_URL -- defaults to a local SQLite file; point at
#     Postgres in real deployments (CLAUDE.md: SQLite is "acceptable for
#     early prototype" only, not for production).
#   PAIGS_STORAGE_ROOT -- where uploaded AB1 files and per-run artifacts
#     live; a volume is mounted here so runs survive container restarts.
#   BLAST_BIN_DIR -- not needed in this image (apt-get install already
#     puts blastn/makeblastdb on PATH); it exists purely for the no-root
#     sandboxed dev fallback described above.
ENV PAIGS_STORAGE_ROOT=/app/storage
VOLUME ["/app/storage"]

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
