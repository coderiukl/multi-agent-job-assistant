from fastapi import APIRouter

from app.api.v1.endpoints import auth, conversation, cvs, jobs

router = APIRouter()

router.include_router(auth.router, prefix="/auth", tags=["Auth"])
router.include_router(cvs.router, prefix="/cvs", tags=["CVs"])
router.include_router(conversation.router, prefix="/conversation", tags=["Conversations"])
router.include_router(jobs.router, prefix="/jobs", tags=["Jobs"])