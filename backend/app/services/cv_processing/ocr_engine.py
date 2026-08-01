from typing import Protocol

import numpy as np
from pydantic import BaseModel, Field

class OCRTextBox(BaseModel):
    text: str
    bbox: tuple[float, float, float, float]
    confidence: float = Field(ge=0.0, le=0.0)

class OCREngine(Protocol):
    def recognize(self, image: np.ndarray) -> list[OCRTextBox]:
        ...

