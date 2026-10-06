"""Composition and bounding box geometry utilities."""

from __future__ import annotations

from typing import List, Tuple, Dict, Any
from models.schemas import Viewport, Panel


def fit_aspect_ratio(
    target_box: Tuple[float, float, float, float],
    target_aspect: float = 16.0 / 9.0,
    padding_fraction: float = 0.05,
    max_width: float = 1920.0,
    max_height: float = 1080.0,
) -> Viewport:
    """Expands or adjusts a bounding box (x, y, w, h) to match target_aspect.
    
    Includes safety padding around the panel so comic borders and text
    bubbles don't get cut off. Clamps within max_width and max_height.
    """
    bx, by, bw, bh = target_box
    
    # Add padding
    pad_w = bw * padding_fraction
    pad_h = bh * padding_fraction
    
    padded_x = bx - pad_w
    padded_y = by - pad_h
    padded_w = bw + (2.0 * pad_w)
    padded_h = bh + (2.0 * pad_h)
    
    current_aspect = padded_w / max(padded_h, 1.0)
    
    if current_aspect < target_aspect:
        # Too tall: expand width to achieve target aspect
        new_w = padded_h * target_aspect
        new_h = padded_h
        new_x = padded_x - (new_w - padded_w) / 2.0
        new_y = padded_y
    else:
        # Too wide: expand height to achieve target aspect
        new_h = padded_w / target_aspect
        new_w = padded_w
        new_x = padded_x
        new_y = padded_y - (new_h - padded_h) / 2.0

    # If the adjusted box exceeds bounds, scale down if possible or shift
    if new_w > max_width:
        new_w = max_width
        new_h = new_w / target_aspect
    if new_h > max_height:
        new_h = max_height
        new_w = new_h * target_aspect

    # Clamp position to stay within [0, max]
    new_x = max(0.0, min(new_x, max_width - new_w))
    new_y = max(0.0, min(new_y, max_height - new_h))
    
    return Viewport(x=new_x, y=new_y, width=new_w, height=new_h)


def detect_comic_format_and_layout(
    image_width: int,
    image_height: int,
    format_override: Optional[str] = None,
    layout_override: Optional[str] = None,
) -> Tuple[str, str, int, int]:
    """Detects format ('desktop' or 'mobile') and layout ('3x2' or '2x3').
    
    Returns:
        (format, layout, default_width, default_height)
    """
    aspect = float(image_width) / max(float(image_height), 1.0)
    
    if format_override:
        fmt = format_override.strip().lower()
    elif layout_override:
        fmt = "mobile" if layout_override.strip() == "2x3" else "desktop"
    else:
        # 9:16 is 0.5625; 4:3 is 1.333. Threshold at 0.85 separates vertical mobile vs horizontal desktop
        fmt = "mobile" if aspect < 0.85 else "desktop"
        
    if layout_override:
        lay = layout_override.strip()
    else:
        lay = "2x3" if fmt == "mobile" else "3x2"
        
    if fmt == "mobile":
        def_w, def_h = 1080, 1920
    else:
        def_w, def_h = 1920, 1080
        
    return fmt, lay, def_w, def_h


def sort_reading_order(
    panels: List[Dict[str, Any]],
    image_height: int,
    layout: str = "3x2",
) -> List[Dict[str, Any]]:
    """Sorts panels into reading order:
    For 3x2 (Desktop): Top row (panels 1, 2, 3), followed by bottom row (panels 4, 5, 6).
    For 2x3 (Mobile): Row 1 (panels 1, 2), Row 2 (panels 3, 4), Row 3 (panels 5, 6).
    """
    if not panels:
        return []

    # Sort all panels by their vertical center (cy)
    panels_with_cy = []
    for p in panels:
        cy = float(p["y"]) + float(p["height"]) / 2.0
        panels_with_cy.append((cy, p))
    panels_with_cy.sort(key=lambda item: item[0])
    sorted_p = [item[1] for item in panels_with_cy]

    if layout == "2x3":
        # 3 rows x 2 columns
        row1 = sorted_p[0:2]
        row2 = sorted_p[2:4]
        row3 = sorted_p[4:6]
        row1.sort(key=lambda p: p["x"])
        row2.sort(key=lambda p: p["x"])
        row3.sort(key=lambda p: p["x"])
        ordered = row1 + row2 + row3
    else:
        # 2 rows x 3 columns (default 3x2)
        mid = len(sorted_p) // 2
        top_row = sorted_p[:mid]
        bottom_row = sorted_p[mid:]
        top_row.sort(key=lambda p: p["x"])
        bottom_row.sort(key=lambda p: p["x"])
        ordered = top_row + bottom_row
    
    # Reassign sequential 1-based IDs
    for idx, p in enumerate(ordered, start=1):
        p["id"] = idx
        
    return ordered


def compute_full_comic_viewport(
    image_width: int,
    image_height: int,
    target_aspect: float = 16.0 / 9.0,
) -> Viewport:
    """Computes a viewport that displays the entire continuous comic canvas without black borders."""
    img_w = float(image_width)
    img_h = float(image_height)
    canvas_aspect = img_w / max(img_h, 1.0)
    
    if canvas_aspect > target_aspect:
        # Canvas is wider than camera: fit height, center width
        vh = img_h
        vw = vh * target_aspect
        if vw > img_w:
            vw = img_w
            vh = vw / target_aspect
    else:
        # Canvas is taller than camera: fit width, center height
        vw = img_w
        vh = vw / target_aspect
        if vh > img_h:
            vh = img_h
            vw = vh * target_aspect

    vw = min(vw, img_w)
    vh = min(vh, img_h)
    vx = max(0.0, (img_w - vw) / 2.0)
    vy = max(0.0, (img_h - vh) / 2.0)
    
    return Viewport(x=vx, y=vy, width=vw, height=vh)
