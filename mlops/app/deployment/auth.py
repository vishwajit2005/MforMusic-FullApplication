import os
import secrets
from starlette.responses import JSONResponse

class ServiceAuth:
    def __init__(self, app):
        self.app = app
        self.key = os.environ.get("MLOPS_API_KEY", "")
        if len(self.key) < 32:
            raise RuntimeError("MLOPS_API_KEY must contain at least 32 characters")

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"] != "/health":
            headers = dict(scope.get("headers", []))
            provided = headers.get(b"x-mformusic-key", b"")
            if not secrets.compare_digest(provided, self.key.encode("utf-8")):
                await JSONResponse({"detail": "Unauthorized"}, status_code=401)(scope, receive, send)
                return
        await self.app(scope, receive, send)
