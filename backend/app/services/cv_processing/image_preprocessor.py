import cv2
import numpy as np


class ImagePreprocessor:
    """Apply conservative preprocessing before OCR."""

    def preprocess(self, image: np.ndarray) -> np.ndarray:
        processed = self.to_grayscale(image)
        processed = self.enhance_contrast(processed)
        processed = self.denoise(processed)

        angle = self.detect_skew_angle(processed)
        if abs(angle) >= 1.0:
            processed = self.deskew_image(processed, angle)

        return processed

    def to_grayscale(self, image: np.ndarray) -> np.ndarray:
        if len(image.shape) == 2:
            return image

        if image.shape[2] == 4:
            return cv2.cvtColor(image, cv2.COLOR_RGBA2GRAY)

        return cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)

    def enhance_contrast(self, image: np.ndarray) -> np.ndarray:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        return clahe.apply(image)

    def denoise(self, image: np.ndarray) -> np.ndarray:
        return cv2.fastNlMeansDenoising(image, None, 7, 7, 21)

    def detect_skew_angle(self, image: np.ndarray) -> float:
        edges = cv2.Canny(image, 50, 150, apertureSize=3)
        lines = cv2.HoughLines(edges, 1, np.pi / 180, 120)

        if lines is None:
            return 0.0

        angles: list[float] = []

        for line in lines[:50]:
            rho, theta = line[0]
            angle = (theta * 180 / np.pi) - 90
            if -15 <= angle <= 15:
                angles.append(float(angle))
        if not angles:
            return 0.0

        return float(np.median(angles))

    def deskew_image(self, image: np.ndarray, angle: float) -> np.ndarray:
        height, width = image.shape[:2]
        center = (width // 2, height // 2)

        matrix = cv2.getRotationMatrix2D(center, angle, 1.0)

        return cv2.warpAffine(
            image,
            matrix,
            (width, height),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )
