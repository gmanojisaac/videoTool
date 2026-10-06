"""Tests for comic panel detection, sorting, and manual overrides."""

import cv2
import numpy as np
import pytest
from pathlib import Path

from vision.panel_detector import analyze_comic_image, detect_panels_uniform_fallback
from vision.composition import sort_reading_order


@pytest.fixture
def sample_comic_image(tmp_path) -> Path:
    """Creates a synthetic 6-panel comic sheet (3 columns x 2 rows) with distinct panel colors."""
    w, h = 1920, 1080
    sheet = np.full((h, w, 3), 255, dtype=np.uint8)  # White background gutters
    
    col_w = (w - 40) // 3
    row_h = (h - 30) // 2
    
    colors = [
        (40, 40, 180),   # Panel 1: Red
        (40, 180, 40),   # Panel 2: Green
        (180, 40, 40),   # Panel 3: Blue
        (40, 180, 180),  # Panel 4: Yellow
        (180, 40, 180),  # Panel 5: Magenta
        (180, 180, 40),  # Panel 6: Cyan
    ]
    
    idx = 0
    for r in range(2):
        for c in range(3):
            x = 10 + c * (col_w + 10)
            y = 10 + r * (row_h + 10)
            sheet[y:y + row_h, x:x + col_w] = colors[idx]
            # Add some inner texture / circle
            cv2.circle(sheet, (x + col_w // 2, y + row_h // 2), 50, (255, 255, 255), -1)
            idx += 1
            
    img_path = tmp_path / "synthetic_comic.png"
    cv2.imwrite(str(img_path), sheet)
    return img_path


def test_six_panels_detected(sample_comic_image, tmp_path):
    """Verifies that exactly six panels are detected with positive confidence."""
    diag_path = tmp_path / "preview.png"
    analysis = analyze_comic_image(sample_comic_image, preview_output_path=diag_path)
    
    assert analysis.panel_count == 6
    assert len(analysis.panels) == 6
    assert analysis.confidence >= 0.5
    assert diag_path.is_file()


def test_panel_reading_order(sample_comic_image):
    """Verifies reading order: top row 1, 2, 3 left-to-right, then bottom row 4, 5, 6."""
    analysis = analyze_comic_image(sample_comic_image)
    panels = analysis.panels
    
    # Check sequential IDs
    assert [p.id for p in panels] == [1, 2, 3, 4, 5, 6]
    
    # Top row y should be above bottom row y
    top_row = panels[:3]
    bottom_row = panels[3:]
    
    for tp in top_row:
        for bp in bottom_row:
            assert tp.y < bp.y
            
    # Within top row, x must be strictly increasing
    assert top_row[0].x < top_row[1].x < top_row[2].x
    # Within bottom row, x must be strictly increasing
    assert bottom_row[0].x < bottom_row[1].x < bottom_row[2].x


def test_panel_valid_coordinates_and_no_overlap(sample_comic_image):
    """Verifies that coordinates are non-negative and panels do not severely overlap."""
    analysis = analyze_comic_image(sample_comic_image)
    
    for p in analysis.panels:
        assert p.x >= 0
        assert p.y >= 0
        assert p.width > 100
        assert p.height > 100
        assert p.x + p.width <= analysis.image_width
        assert p.y + p.height <= analysis.image_height
        
    # Check pairwise overlap is minimal (< 5% area overlap)
    for i in range(len(analysis.panels)):
        for j in range(i + 1, len(analysis.panels)):
            p1 = analysis.panels[i]
            p2 = analysis.panels[j]
            
            x_left = max(p1.x, p2.x)
            y_top = max(p1.y, p2.y)
            x_right = min(p1.x + p1.width, p2.x + p2.width)
            y_bottom = min(p1.y + p1.height, p2.y + p2.height)
            
            if x_right > x_left and y_bottom > y_top:
                overlap_area = (x_right - x_left) * (y_bottom - y_top)
                smaller_area = min(p1.width * p1.height, p2.width * p2.height)
                overlap_ratio = overlap_area / smaller_area
                assert overlap_ratio < 0.05, f"Excessive overlap between panel {p1.id} and {p2.id}"


def test_manual_panel_coordinates_override(sample_comic_image):
    """Verifies manual coordinates take absolute precedence over automatic detection."""
    manual = [
        {"id": 1, "x": 50, "y": 60, "width": 500, "height": 400, "focus_x": 300, "focus_y": 250},
        {"id": 2, "x": 600, "y": 60, "width": 500, "height": 400, "focus_x": 850, "focus_y": 250},
        {"id": 3, "x": 1150, "y": 60, "width": 500, "height": 400, "focus_x": 1400, "focus_y": 250},
        {"id": 4, "x": 50, "y": 500, "width": 500, "height": 400, "focus_x": 300, "focus_y": 700},
        {"id": 5, "x": 600, "y": 500, "width": 500, "height": 400, "focus_x": 850, "focus_y": 700},
        {"id": 6, "x": 1150, "y": 500, "width": 500, "height": 400, "focus_x": 1400, "focus_y": 700},
    ]
    analysis = analyze_comic_image(sample_comic_image, manual_panels=manual)
    
    assert analysis.confidence == 1.0
    assert analysis.panels[0].x == 50
    assert analysis.panels[0].y == 60
    assert analysis.panels[0].focus_x == 300
    assert analysis.panels[0].focus_y == 250
