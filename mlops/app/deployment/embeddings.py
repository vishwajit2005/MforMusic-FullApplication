"""Separate CPU memory budget for the existing MiniLM encoder."""
import asyncio
from fastapi import FastAPI
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from app.deployment.auth import ServiceAuth
from app.services.embedding_service import _get_model

api = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
lock = asyncio.Lock()

class EncodeRequest(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=64)

@api.get("/health")
def health():
    return {"status": "ok", "service": "embeddings"}

@api.post("/encode")
async def encode(request: EncodeRequest):
    async with lock:
        def compute():
            model = _get_model()
            if model is None:
                from fastapi import HTTPException
                raise HTTPException(503, "Embedding model unavailable")
            return model.encode(request.texts, normalize_embeddings=True,
                                batch_size=64, show_progress_bar=False).astype("float32").tolist()
        return {"vectors": await run_in_threadpool(compute)}

app = ServiceAuth(api)
