import {
    MAX_CV_FILES,
    MAX_FILE_SIZE,
    MAX_TOTAL_CV_SIZE,
} from "../../core/constants.js";

export function getClipboardImageFiles(clipboardData) {
    const directFiles = Array.from(clipboardData?.files ?? []).filter(
        (file) => file.type?.startsWith("image/"),
    );

    if (directFiles.length) {
        return directFiles;
    }

    return Array.from(clipboardData?.items ?? [])
        .filter(
            (item) => item.kind === "file" && item.type?.startsWith("image/"),
        )
        .map((item) => item.getAsFile())
        .filter(Boolean);
}

export function validateCvFile(file) {
    if (!file) {
        return "Bạn chưa chọn CV.";
    }

    const normalizedName = file.name.toLowerCase().trim();

    const supportedTypes = new Set([
        "application/pdf",
        "image/jpeg",
        "image/png",
    ]);
    const supportedExtensions = [".pdf", ".jpg", ".jpeg", ".png"];
    const hasSupportedType = supportedTypes.has((file.type || "").toLowerCase());
    const hasSupportedExtension = supportedExtensions.some(
        (extension) => normalizedName.endsWith(extension),
    );

    if (
        !hasSupportedExtension ||
        (file.type && !hasSupportedType)
    ) {
        return "CV phải là tệp PDF hoặc ảnh PNG/JPG.";
    }

    if (file.size > MAX_FILE_SIZE) {
        return "Dung lượng CV không được vượt quá 10 MB.";
    }
    
    return null;
}

export function validateCvFiles(files) {
    const selectedFiles = Array.from(files ?? []);

    if (!selectedFiles.length) {
        return "Bạn chưa chọn CV.";
    }

    if (selectedFiles.length > MAX_CV_FILES) {
        return `Mỗi CV chỉ được gồm tối đa ${MAX_CV_FILES} ảnh.`;
    }

    for (const file of selectedFiles) {
        const validationError = validateCvFile(file);
        if (validationError) {
            return validationError;
        }
    }

    if (
        selectedFiles.length > 1 &&
        selectedFiles.some(
            (file) => file.type === "application/pdf" ||
                file.name.toLowerCase().trim().endsWith(".pdf"),
        )
    ) {
        return "Hãy chọn một file PDF hoặc từ 1 đến 5 ảnh, không trộn lẫn.";
    }

    const totalSize = selectedFiles.reduce(
        (total, file) => total + file.size,
        0,
    );
    if (totalSize > MAX_TOTAL_CV_SIZE) {
        return "Tổng dung lượng CV không được vượt quá 50 MB.";
    }

    return null;
}
