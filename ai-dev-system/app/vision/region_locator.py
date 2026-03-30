from __future__ import annotations


class RegionLocator:
    """Build smaller image-search regions from a known window rectangle."""

    def from_window(
        self,
        bounds: tuple[int, int, int, int],
        *,
        padding: int = 0,
        relative: tuple[float, float, float, float] | None = None,
    ) -> tuple[int, int, int, int]:
        left, top, right, bottom = bounds
        if relative is not None:
            rel_left, rel_top, rel_right, rel_bottom = relative
            width = right - left
            height = bottom - top
            left = left + int(width * rel_left)
            top = top + int(height * rel_top)
            right = left + int(width * (rel_right - rel_left))
            bottom = top + int(height * (rel_bottom - rel_top))
            return (left, top, right - left, bottom - top)
        return (left + padding, top + padding, (right - left) - (padding * 2), (bottom - top) - (padding * 2))
