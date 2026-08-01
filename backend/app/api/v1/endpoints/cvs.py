from fastapi import APIRouter, File, UploadFile

from app.api.deps import StorageDep
from app.schemas.cv import CvUploadResponse
from app.schemas.response import ApiResponse
from app.utils.responses import success_response

router = APIRouter(prefix="/cvs", tags=["CVs"])

@router.post("/upload", status_code=201)
async def upload_cv(storage: StorageDep, file: UploadFile = File(...)) -> ApiResponse[CvUploadResponse]:
    saved_path = await storage.save_upload_file(file)

    return success_response(
        message="CV uploaded successfully.",
        data=CvUploadResponse(
            file_id=saved_path.stem,
            filename=saved_path.name,
            original_filename=file.filename,
            content_type=file.content_type,
            size_bytes=saved_path.stat().st_size,
        )
    )

