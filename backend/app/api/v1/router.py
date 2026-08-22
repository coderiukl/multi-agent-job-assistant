from fastapi import APIRouter

from app.api.v1.endpoints import conversation, cvs

router = APIRouter()

router.include_router(cvs.router, prefix="/cvs", tags=["CVs"])
router.include_router(conversation.router, prefix="/conversation", tags=["Conversations"])