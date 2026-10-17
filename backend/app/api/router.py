from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.invitations import router as invitations_router
from app.api.routes.workspace import router as workspace_router

router = APIRouter(prefix="/api")
router.include_router(auth_router)
router.include_router(invitations_router)
router.include_router(workspace_router)
