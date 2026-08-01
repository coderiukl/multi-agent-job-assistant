from fastapi import APIRouter
from app.api.v1.endpoints import health, cvs

router = APIRouter()

router.include_router(health.router)
router.include_router(cvs.router)