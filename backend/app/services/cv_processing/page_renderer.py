import fitz
import numpy as np

class PageRenderer:
    """Render PDF pages or regions to OpenCV-compatible images."""

    def render_page(self, page: fitz.Page, *, dpi: int) -> np.ndarray:
        matrix = fitz.Matrix(dpi / 72, dpi / 72)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        return self._pixmap_to_image(pixmap)

    def render_region(self, page: fitz.Page, *, bbox: tuple[float, float, float, float], dpi: int) -> np.ndarray:
        matrix = fitz.Matrix(dpi / 72, dpi / 72)
        clip = fitz.Rect(*bbox)
        pixmap = page.get_pixmap(matrix=matrix, clip=clip, alpha=False)
        return self._pixmap_to_image(pixmap)

    def image_bbox_to_page_bbox(self, *, image_bbox: tuple[float, float, float, float], page_bbox: tuple[float, float, float, float], image_width: int, image_height: int) -> tuple[float, float, float, float]:
        x0, y0, x1, y1 = image_bbox
        px0, py0, px1, py1 = page_bbox

        page_width = px1 - px0
        page_height = py1 - py0

        return (
            px0 + (x0 / image_width) * page_width,
            py0 + (y0 / image_height) * page_height,
            px0 + (x1 / image_width) * page_width,
            py0 + (y1 / image_height) * page_height,
        )

    def _pixmap_to_image(self, pixmap: fitz.Pixmap) -> np.ndarray:
        image = np.frombuffer(pixmap.samples, dtype=np.uint8)
        image = image.reshape(pixmap.height, pixmap.width, pixmap.n)
        return image