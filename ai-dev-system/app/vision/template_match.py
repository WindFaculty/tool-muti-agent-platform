from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image


class TemplateMatcher:
    """Match a template image against a screenshot region."""

    def match(self, source: Image.Image, template_path: Path, confidence: float) -> dict[str, Any] | None:
        source_np = cv2.cvtColor(np.array(source), cv2.COLOR_RGB2BGR)
        template = cv2.imread(str(template_path))
        if template is None:
            raise FileNotFoundError(template_path)
        result = cv2.matchTemplate(source_np, template, cv2.TM_CCOEFF_NORMED)
        _, max_value, _, max_loc = cv2.minMaxLoc(result)
        if max_value < confidence:
            return None
        height, width = template.shape[:2]
        return {
            "score": float(max_value),
            "left": int(max_loc[0]),
            "top": int(max_loc[1]),
            "width": int(width),
            "height": int(height),
        }
