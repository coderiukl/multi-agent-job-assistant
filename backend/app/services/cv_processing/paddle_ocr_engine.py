import numpy as np

from app.core.exceptions import ExternalServiceException
from app.services.cv_processing.ocr_engine import OCREngine, OCRTextBox


class PaddleOCREngine(OCREngine):
    """PaddleOCR adapter."""

    def __init__(self, *, languages: tuple[str, ...]) -> None:
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise ExternalServiceException(
                service="paddleocr",
                message="PaddleOCR is not installed.",
            ) from exc

        lang = "vi" if "vi" in languages else "en"

        try:
            self.engine = PaddleOCR(
                use_angle_cls=True,
                lang=lang,
                show_log=False,
            )
        except Exception as exc:
            raise ExternalServiceException(
                service="paddleocr",
                message="PaddleOCR cannot be initialized.",
            ) from exc

    def recognize(self, image: np.ndarray) -> list[OCRTextBox]:
        try:
            result = self.engine.ocr(image, cls=True)
        except Exception as exc:
            raise ExternalServiceException(
                service="paddleocr",
                message="PaddleOCR recognition failed.",
            ) from exc

        boxes: list[OCRTextBox] = []

        if not result:
            return boxes

        for page_result in result:
            if not page_result:
                continue

            for item in page_result:
                points = item[0]
                text, confidence = item[1]
                clean_text = str(text).strip()

                if not clean_text:
                    continue

                xs = [float(point[0]) for point in points]
                ys = [float(point[1]) for point in points]
                confidence_value = max(0.0, min(float(confidence), 1.0))

                boxes.append(
                    OCRTextBox(
                        text=clean_text,
                        bbox=(min(xs), min(ys), max(xs), max(ys)),
                        confidence=confidence_value,
                    )
                )
        return boxes
