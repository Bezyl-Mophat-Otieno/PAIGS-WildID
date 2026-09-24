from fastapi import FastAPI

from app.api.config import router as config_router
from app.api.reference import router as reference_router
from app.api.runs import router as runs_router
from app.db import Base, engine

Base.metadata.create_all(bind=engine)

app = FastAPI(title="PAIGS WildID", version="0.1.0")

app.include_router(runs_router)
app.include_router(reference_router)
app.include_router(config_router)


@app.get("/health")
def health():
    return {"status": "ok"}
