import { requestJson } from "./http-client.js";

const CV_UPLOAD_ENDPOINT = "/api/v1/cvs";

export async function uploadCv(file) {
    const formData = new FormData();

    formData.append("file", file);

    const responseBody = await requestJson(
        CV_UPLOAD_ENDPOINT,
        {
            method: "POST",
            body: formData,
        },
        "Không thể tải CV lên backend.",
    );

    const data = responseBody?.data ?? responseBody;

    return {
        fileId:
            data?.fileId ??
            data?.file_id ??
            data?.cvId ??
            data?.cv_id ??
            null,
        taskId:
            data?.taskId ??
            data?.task_id ??
            null,
        status: data?.status ?? null,
        fileName:
            data?.fileName ??
            data?.file_name ??
            file.name,
        fileSize:
            data?.fileSize ??
            data?.file_size ??
            file.size,
        contentType:
            data?.content_type ??
            file.type,
        inspection: data?.inspection ?? null,
        extraction: data?.extraction ?? null,
        ocr: data?.ocr ?? null,
        profile: data?.profile ?? null,
    };
}

export async function getCvProcessingTask(taskId) {
    const responseBody = await requestJson(
        CV_UPLOAD_ENDPOINT +
            "/processing-tasks/" +
            encodeURIComponent(taskId),
        {},
        "Không thể kiểm tra trạng thái xử lý CV.",
    );
    const data = responseBody?.data ?? responseBody;
    return {
        taskId: data?.taskId ?? data?.task_id ?? taskId,
        fileId: data?.cvId ?? data?.cv_id ?? null,
        fileName: data?.fileName ?? data?.file_name ?? null,
        fileSize: data?.fileSize ?? data?.file_size ?? null,
        contentType: data?.contentType ?? data?.content_type ?? null,
        status: data?.status ?? null,
        attemptCount: data?.attemptCount ?? data?.attempt_count ?? 0,
        errorCode: data?.errorCode ?? data?.error_code ?? null,
        errorMessage: data?.errorMessage ?? data?.error_message ?? null,
        profile: data?.profile ?? null,
    };
}

export async function updateCvProfile(fileId, profile) {
    const responseBody = await requestJson(
        CV_UPLOAD_ENDPOINT + "/" + encodeURIComponent(fileId),
        {
            method: "PATCH",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(profile),
        },
        "Không thể cập nhật thông tin CV.",
    );
    return responseBody?.data ?? responseBody;
}

export async function deleteCv(fileId) {
    await requestJson(
        CV_UPLOAD_ENDPOINT + "/" + encodeURIComponent(fileId),
        {method: "DELETE"},
        "Không thể xóa CV.",
    );
}
