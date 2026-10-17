"""FastAPI application assembly. Run with uvicorn app.main:app."""
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import Response

from app.api.router import router
from app.core.config import settings
from app.services.auth import AuthenticationError
from app.services.invitations import InvitationError
from app.services.errors import WorkspaceError
from psycopg import IntegrityError


def create_app() -> FastAPI:
    application = FastAPI(title="AI Grading Assistant")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type", "X-Requested-With"],
    )

    @application.exception_handler(AuthenticationError)
    async def authentication_error(request: Request, error: AuthenticationError) -> JSONResponse:
        return JSONResponse(status_code=401, content={"detail": str(error)})

    @application.exception_handler(InvitationError)
    async def invitation_error(request: Request, error: InvitationError) -> JSONResponse:
        return JSONResponse(status_code=error.status_code, content={"detail": str(error)})

    @application.exception_handler(WorkspaceError)
    async def workspace_error(request: Request, error: WorkspaceError) -> JSONResponse:
        return JSONResponse(status_code=error.status_code,content={'detail':str(error)})

    @application.exception_handler(IntegrityError)
    async def integrity_error(request: Request, error: IntegrityError) -> JSONResponse:
        return JSONResponse(status_code=409,content={'detail':'The change conflicts with existing data or a publication rule. Refresh and check your input.'})

    @application.middleware("http")
    async def prevent_auth_caching(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Referrer-Policy"] = "no-referrer"
        return response

    application.include_router(router)
    return application


app = create_app()
