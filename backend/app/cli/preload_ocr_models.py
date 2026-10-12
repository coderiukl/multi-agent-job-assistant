from app.core.config import get_settings
from app.services.pdf import PdfOcrExtractor


async def preload_ocr_models() -> None:
    extractor = PdfOcrExtractor(get_settings())
    await extractor.warm_up()
