import numpy as np

from app.services.cv_processing.ocr_engine import OCREngine, OCRTextBox

class PaddleOCREngine(OCREngine):
    """PaddleOCR adapter"""

    def __init__(self, *, languages: tuple[str, ...]) -> None:
        from paddleocr import PaddleOCR

        lang="en"
        if "vi" in languages:
            lang = "en"

        self.enging = PaddleOCR(
            use_angle_cls=True,
            lang=lang,
            show_log=False,
        )

    def recognize(self, image: np.ndarray) -> list[OCRTextBox]:
        result = self.engine.ocr(image, cls=True)
        boxes: list[OCRTextBox] = []

        if not result:
            return boxes

        for page_result in result:
            if not page_result:
                continue

            for item in page_result:
                points = item[0]
                text, confidence = item[1]

                xs = [float(point[0]) for point in points]
                ys = [float(point[1]) for point in points]

                boxes.append(
                    OCRTextBox(
                        text=text,
                        bbox=(min(xs), min(ys), max(xs), max(ys)),
                        confidence=float(confidence)
                    )
                )
        return boxes
    