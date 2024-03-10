from starlette.datastructures import URL
from starlette.responses import RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class PathRedirectMiddleware:
    def __init__(self, app: ASGIApp, paths: set[str], port: int) -> None:
        self.app = app
        self.paths = paths
        self.port = port

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if "path" in scope and scope["path"] in self.paths:
            url = URL(scope=scope)
            url = url.replace(port=self.port)
            response = RedirectResponse(url, status_code=307)
            await response(scope, receive, send)
        else:
            await self.app(scope, receive, send)
