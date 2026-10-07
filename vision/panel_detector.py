"""Panel detection for 6-tile comic sheets with OpenCV and Pillow."""

from __future__ import annotations

import cv2
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

from models.schemas import Panel, ComicAnalysis
from vision.composition import sort_reading_order, detect_comic_format_and_layout
from vision.focus_detector import detect_focus_point


def detect_panels_via_gutters(
    image: np.ndarray,
    layout: str = "3x2",
) -> Optional[List[Dict[str, int]]]:
    """Detects 3x2 (Desktop) or 2x3 (Mobile) panel grid by finding horizontal and vertical gutters."""
    h, w = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    
    # Compute horizontal and vertical projection profiles (gradient / edge density)
    edges = cv2.Canny(gray, 40, 150)
    row_density = np.mean(edges, axis=1)
    col_density = np.mean(edges, axis=0)

    if layout == "2x3":
        # 2 columns x 3 rows (Mobile)
        # Search for central vertical gutter between 0.38*w and 0.62*w
        v_start = int(0.38 * w)
        v_end = int(0.62 * w)
        v_x = v_start + int(np.argmin(col_density[v_start:v_end])) if v_end > v_start else w // 2

        # Search for horizontal gutter 1 (between 0.24*h and 0.42*h)
        h1_start = int(0.24 * h)
        h1_end = int(0.42 * h)
        h1_y = h1_start + int(np.argmin(row_density[h1_start:h1_end])) if h1_end > h1_start else int(h / 3)

        # Search for horizontal gutter 2 (between 0.58*h and 0.76*h)
        h2_start = int(0.58 * h)
        h2_end = int(0.76 * h)
        h2_y = h2_start + int(np.argmin(row_density[h2_start:h2_end])) if h2_end > h2_start else int(2 * h / 3)

        col_bounds = [(0, v_x), (v_x, w)]
        row_bounds = [(0, h1_y), (h1_y, h2_y), (h2_y, h)]
    else:
        # 3 columns x 2 rows (Desktop 3x2)
        # Central horizontal gutter between row 0.38*h and 0.62*h
        mid_y_start = int(0.38 * h)
        mid_y_end = int(0.62 * h)
        h_gutter_y = mid_y_start + int(np.argmin(row_density[mid_y_start:mid_y_end])) if mid_y_end > mid_y_start else h // 2

        # Vertical gutter 1 (between 0.24*w and 0.42*w)
        v1_start = int(0.24 * w)
        v1_end = int(0.42 * w)
        v1_x = v1_start + int(np.argmin(col_density[v1_start:v1_end])) if v1_end > v1_start else int(w / 3)

        # Vertical gutter 2 (between 0.58*w and 0.76*w)
        v2_start = int(0.58 * w)
        v2_end = int(0.76 * w)
        v2_x = v2_start + int(np.argmin(col_density[v2_start:v2_end])) if v2_end > v2_start else int(2 * w / 3)

        col_bounds = [(0, v1_x), (v1_x, v2_x), (v2_x, w)]
        row_bounds = [(0, h_gutter_y), (h_gutter_y, h)]
    
    candidate_panels = []
    for r_idx, (y_start, y_end) in enumerate(row_bounds):
        for c_idx, (x_start, x_end) in enumerate(col_bounds):
            candidate_panels.append({
                "x": int(x_start),
                "y": int(y_start),
                "width": int(x_end - x_start),
                "height": int(y_end - y_start),
            })
            
    if len(candidate_panels) == 6:
        return candidate_panels
    return None


def detect_panels_via_contours(
    image: np.ndarray,
    layout: str = "3x2",
) -> Optional[List[Dict[str, int]]]:
    """Detects panels via external rectangular contours."""
    h, w = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    
    # Adaptive threshold / edge detection
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    thresh = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 3
    )
    
    # Morphological closing to connect panel frame lines
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    total_area = w * h
    min_area = total_area * 0.05
    max_area = total_area * 0.35
    
    rectangles = []
    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        area = cw * ch
        if min_area <= area <= max_area:
            # Check aspect ratio
            aspect = cw / max(ch, 1)
            if 0.4 <= aspect <= 2.8:
                rectangles.append({"x": x, "y": y, "width": cw, "height": ch})
                
    if len(rectangles) == 6:
        return rectangles
    return None


def detect_panels_uniform_fallback(
    image_width: int,
    image_height: int,
    layout: str = "3x2",
) -> List[Dict[str, int]]:
    """Generates standard grid as fallback (3x2 Desktop or 2x3 Mobile)."""
    w = image_width
    h = image_height
    
    if layout == "2x3":
        # 2 columns x 3 rows (Mobile)
        cols, rows = 2, 3
    else:
        # 3 columns x 2 rows (Desktop)
        cols, rows = 3, 2

    col_w = w / float(cols)
    row_h = h / float(rows)
    
    panels = []
    for r in range(rows):
        for c in range(cols):
            panels.append({
                "x": int(round(c * col_w)),
                "y": int(round(r * row_h)),
                "width": int(round(col_w)),
                "height": int(round(row_h)),
            })
    return panels


def evaluate_confidence(
    panels: List[Dict[str, int]],
    image_width: int,
    image_height: int,
    detection_method: str,
) -> float:
    """Evaluates detection confidence score based on geometry and coverage."""
    if len(panels) != 6:
        return 0.3
        
    total_image_area = image_width * image_height
    panel_areas = [p["width"] * p["height"] for p in panels]
    total_panel_area = sum(panel_areas)
    
    coverage = total_panel_area / float(total_image_area)
    # Expected coverage is 85% to 100% of image area
    if coverage < 0.75 or coverage > 1.05:
        area_score = 0.5
    else:
        area_score = 0.95
        
    # Check consistency of panel sizes (standard deviation / mean)
    mean_area = np.mean(panel_areas)
    std_area = np.std(panel_areas)
    consistency_score = max(0.4, 1.0 - (std_area / max(mean_area, 1.0)))
    
    if detection_method == "gutters":
        base_confidence = 0.92
    elif detection_method == "contours":
        base_confidence = 0.95
    else:
        base_confidence = 0.82
        
    return float(np.clip(base_confidence * area_score * consistency_score, 0.2, 1.0))


def analyze_comic_image(
    image_path: str | Path,
    manual_panels: Optional[List[Dict[str, Any]]] = None,
    preview_output_path: Optional[str | Path] = None,
    format: Optional[str] = None,
    layout: Optional[str] = None,
) -> ComicAnalysis:
    """Performs full comic analysis: detects format (Desktop/Mobile) and layout (3x2/2x3),
    detects panels, reading order, focal points, and optionally renders a diagnostic preview image.
    """
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"Source comic image not found: {path}")
        
    # Read image using OpenCV
    image = cv2.imread(str(path))
    if image is None:
        raise ValueError(f"Unable to decode image file: {path}")
        
    img_h, img_w = image.shape[:2]
    
    # Detect format (desktop / mobile) and layout (3x2 / 2x3)
    detected_format, detected_layout, _, _ = detect_comic_format_and_layout(
        image_width=img_w,
        image_height=img_h,
        format_override=format,
        layout_override=layout,
    )
    
    detection_method = "auto"
    raw_panels: List[Dict[str, Any]] = []
    
    # 1. Check if manual coordinates were supplied
    if manual_panels and len(manual_panels) > 0:
        raw_panels = [dict(p) for p in manual_panels]
        detection_method = "manual"
        confidence = 1.0
        warning = None
    else:
        # Try Strategy 1: Gutters
        gutter_panels = detect_panels_via_gutters(image, layout=detected_layout)
        if gutter_panels and len(gutter_panels) == 6:
            raw_panels = gutter_panels
            detection_method = "gutters"
        else:
            # Try Strategy 2: Contours
            contour_panels = detect_panels_via_contours(image, layout=detected_layout)
            if contour_panels and len(contour_panels) == 6:
                raw_panels = contour_panels
                detection_method = "contours"
            else:
                # Strategy 3: Uniform grid fallback
                raw_panels = detect_panels_uniform_fallback(img_w, img_h, layout=detected_layout)
                detection_method = "uniform_grid"
                
        confidence = evaluate_confidence(raw_panels, img_w, img_h, detection_method)
        if confidence < 0.6:
            warning = "Automatic panel detection confidence is low. Please provide manual panel coordinates."
        else:
            warning = None

    # Sort into reading order (1..6) using detected layout
    sorted_panels = sort_reading_order(raw_panels, img_h, layout=detected_layout)
    
    # Detect focus points for each panel
    final_panels: List[Panel] = []
    for p in sorted_panels:
        # Check if manual focus provided
        if "focus_x" in p and "focus_y" in p:
            fx = int(p["focus_x"])
            fy = int(p["focus_y"])
            ftype = p.get("focus_type", "manual")
        else:
            fx, fy, ftype = detect_focus_point(
                image, p["x"], p["y"], p["width"], p["height"]
            )
            
        panel_obj = Panel(
            id=p["id"],
            x=p["x"],
            y=p["y"],
            width=p["width"],
            height=p["height"],
            focus_x=fx,
            focus_y=fy,
            focus_type=ftype,
            protected_content_bounds=p.get("protected_content_bounds"),
            confidence=p.get("confidence", confidence),
        )
        final_panels.append(panel_obj)

    # Generate diagnostic preview image if requested
    diag_preview_path_str: Optional[str] = None
    if preview_output_path:
        preview_path = Path(preview_output_path)
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        generate_panel_preview(image, final_panels, preview_path)
        diag_preview_path_str = str(preview_path.resolve())

    return ComicAnalysis(
        image_path=str(path.resolve()),
        image_width=img_w,
        image_height=img_h,
        panel_count=len(final_panels),
        layout=detected_layout,
        format=detected_format,
        panels=final_panels,
        confidence=round(confidence, 3),
        warning=warning,
        diagnostic_preview_path=diag_preview_path_str,
    )


def generate_panel_preview(
    image: np.ndarray,
    panels: List[Panel],
    output_path: Path,
) -> None:
    """Draws clear panel boundaries, sequence numbers, reading order path,
    and focus crosshairs onto a diagnostic image.
    """
    diag = image.copy()
    h, w = diag.shape[:2]
    
    # Colors
    box_color = (0, 220, 50)       # Green
    focus_color = (0, 165, 255)    # Orange
    arrow_color = (255, 200, 0)    # Cyan-yellow
    badge_bg = (30, 30, 30)        # Dark grey
    badge_text = (255, 255, 255)   # White
    
    centers = []
    
    for panel in panels:
        x, y, pw, ph = panel.x, panel.y, panel.width, panel.height
        centers.append((x + pw // 2, y + ph // 2))
        
        # Draw panel outline
        cv2.rectangle(diag, (x, y), (x + pw, y + ph), box_color, 3)
        
        # Draw panel badge (ID number)
        badge_size = 56
        badge_x = x + 12
        badge_y = y + 12
        cv2.rectangle(
            diag,
            (badge_x, badge_y),
            (badge_x + badge_size, badge_y + badge_size),
            badge_bg,
            -1,
        )
        cv2.rectangle(
            diag,
            (badge_x, badge_y),
            (badge_x + badge_size, badge_y + badge_size),
            box_color,
            2,
        )
        cv2.putText(
            diag,
            str(panel.id),
            (badge_x + 16, badge_y + 40),
            cv2.FONT_HERSHEY_DUPLEX,
            1.1,
            badge_text,
            2,
            cv2.LINE_AA,
        )
        
        # Draw focal point indicator
        fx, fy = panel.focus_x, panel.focus_y
        cv2.circle(diag, (fx, fy), 14, focus_color, 2, cv2.LINE_AA)
        cv2.circle(diag, (fx, fy), 3, focus_color, -1, cv2.LINE_AA)
        cv2.line(diag, (fx - 22, fy), (fx + 22, fy), focus_color, 1, cv2.LINE_AA)
        cv2.line(diag, (fx, fy - 22), (fx, fy + 22), focus_color, 1, cv2.LINE_AA)
        
        # Label focus type
        cv2.putText(
            diag,
            panel.focus_type,
            (fx + 16, fy - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            focus_color,
            1,
            cv2.LINE_AA,
        )

    # Draw reading order arrows connecting panel centers
    for i in range(len(centers) - 1):
        pt1 = centers[i]
        pt2 = centers[i + 1]
        cv2.arrowedLine(diag, pt1, pt2, arrow_color, 2, tipLength=0.08)

    cv2.imwrite(str(output_path), diag)
