"""Authentication HTTP validation, cookies, and responses."""
from fastapi import APIRouter, Depends, Request, Response

from app.api.dependencies import get_auth_service, protect_mutation, limit_login
from app.core.config import settings
from app.schemas.auth import LoginRequest, UserResponse
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=UserResponse, dependencies=[Depends(protect_mutation),Depends(limit_login)])
def login(body: LoginRequest, request: Request, response: Response,
          service: AuthService = Depends(get_auth_service)) -> UserResponse:
    user, token = service.login(body.email, body.password, request.cookies.get(settings.cookie_name))
    response.delete_cookie(settings.cookie_name, path="/api/auth")
    response.set_cookie(settings.cookie_name, token, max_age=settings.session_seconds, httponly=True,
                        secure=settings.cookie_secure, samesite="lax", path=settings.cookie_path)
    return UserResponse.from_user(user)


@router.get("/me", response_model=UserResponse)
def me(request: Request, service: AuthService = Depends(get_auth_service)) -> UserResponse:
    return UserResponse.from_user(service.current_user(request.cookies.get(settings.cookie_name)))


@router.post("/logout", status_code=204, dependencies=[Depends(protect_mutation)])
def logout(request: Request, response: Response, service: AuthService = Depends(get_auth_service)) -> None:
    service.logout(request.cookies.get(settings.cookie_name))
    response.delete_cookie(settings.cookie_name, path="/api/auth")
    response.delete_cookie(settings.cookie_name, path=settings.cookie_path, secure=settings.cookie_secure,
                           httponly=True, samesite="lax")
