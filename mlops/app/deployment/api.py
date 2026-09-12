"""Compose unchanged serving routes with a remote encoder for free-tier memory isolation."""
import os
import numpy as np
import requests
from app.services import embedding_service
from app.deployment.auth import ServiceAuth

class RemoteEncoder:
    def __init__(self):
        self.url = os.environ["EMBEDDING_SERVICE_URL"].rstrip("/")
        self.key = os.environ["MLOPS_API_KEY"]
        if not self.url.startswith("https://") and os.environ.get("DEPLOYMENT_LOCAL_TEST") != "1":
            raise RuntimeError("Embedding service requires HTTPS")

    def encode(self, texts, normalize_embeddings=True, batch_size=64, show_progress_bar=False):
        if not normalize_embeddings:
            raise ValueError("The serving pipeline requires normalized embeddings")
        single = isinstance(texts, str)
        rows = [texts] if single else list(texts)
        vectors = []
        for i in range(0, len(rows), 64):
            response = requests.post(self.url + "/encode", json={"texts": rows[i:i+64]},
                                     headers={"X-MforMusic-Key": self.key}, timeout=(5, 90))
            response.raise_for_status()
            vectors.extend(response.json()["vectors"])
        result = np.asarray(vectors, dtype=np.float32)
        return result[0] if single else result

# Deployment-only dependency injection. Local app.main and model code are unchanged.
embedding_service._model = RemoteEncoder()
from app.main import app as serving_app
app = ServiceAuth(serving_app)
