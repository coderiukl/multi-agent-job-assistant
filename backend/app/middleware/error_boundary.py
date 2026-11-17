from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.exception_handlers import unhandled_exception_handler


class UnhandledErrorMiddleware:
    """Turns unexpected exceptions into the JSON 500 envelope *inside* CORS.

    Starlette routes ``Exception`` handlers to ``ServerErrorMiddleware``, the
    outermost layer, so those responses never pass through ``CORSMiddleware``
    and the browser reports a CORS failure instead of the API error. This
    middleware must be registered before (i.e. inside) ``CORSMiddleware``.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception as exc:
            if response_started:
                raise
            response = await unhandled_exception_handler(Request(scope), exc)
            await response(scope, receive, send)
