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
            null,
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