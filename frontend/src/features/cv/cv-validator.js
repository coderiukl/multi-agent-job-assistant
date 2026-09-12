import { MAX_FILE_SIZE } from "../../core/constants.js";

export function validateCvFile(file) {
    if (!file) {
        return "Bạn chưa chọn CV.";
    }

    const normalizedName = file.name.toLowerCase().trim();

    const isPdf = file.type === "application/pdf" || normalizedName.endsWith(".pdf");

    if (!isPdf) {
        return "CV phải là tệp PDF.";
    }

    if (file.size > MAX_FILE_SIZE) {
        return "Dung lượng CV không được vượt quá 10 MB.";
    }
    
    return null;
}