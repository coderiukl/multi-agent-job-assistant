from fastapi import APIRouter

from app.api.v1.endpoints.cvs import router as cvs_router

router = APIRouter()

router.include_router(cvs_router, prefix="/cvs", tags=["CVs"])