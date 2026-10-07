"""Comprehensive tests for continuous canvas comic video generation.

Validates:
1. Desktop 4:3 3x2 continuous canvas video generation and borderless framing.
2. Mobile 9:16 2x3 continuous canvas video generation and vertical video output.
3. Automatic format and layout detection.
4. Seamless continuous camera flight without panel borders or slideshow tile jumps.
"""

import cv2
import numpy as np
import pytest
from pathlib import Path

from vision.composition import detect_comic_format_and_layout, compute_full_comic_viewport, sort_reading_order
from vision.panel_detector import analyze_comic_image
from video.camera import compute_panel_viewports, interpolate_viewports
from video.transitions import sample_transition_viewport
from video.renderer import get_viewport_at_time
from models.schemas import CameraPlan, Viewport
from mcp_tools.analyze_comic import analyze_comic
from mcp_tools.create_camera_plan import create_camera_plan
from mcp_tools.create_comic_video import create_comic_video
from mcp_tools.inspect_output import inspect_output


@pytest.fixture
def desktop_4_3_comic(tmp_path) -> Path:
    """Creates a synthetic 4:3 desktop comic strip (2400x1800, 3 columns x 2 rows)
    with distinct panel borders and artwork inside.
    """
    w, h = 2400, 1800  # 4:3 ratio = 1.333
    canvas = np.full((h, w, 3), 250, dtype=np.uint8)  # Off-white gutters
    
    col_w = (w - 80) // 3
    row_h = (h - 60) // 2
    
    colors = [
        (50, 50, 200),   # 1: Red
        (50, 180, 50),   # 2: Green
        (200, 50, 50),   # 3: Blue
        (50, 180, 180),  # 4: Yellow
        (180, 50, 180),  # 5: Magenta
        (180, 180, 50),  # 6: Cyan
    ]
    
    idx = 0
    for r in range(2):
        for c in range(3):
            x = 20 + c * (col_w + 20)
            y = 20 + r * (row_h + 20)
            # Black panel border stroke
            cv2.rectangle(canvas, (x, y), (x + col_w, y + row_h), (0, 0, 0), 6)
            # Inner artwork
            canvas[y + 6:y + row_h - 6, x + 6:x + col_w - 6] = colors[idx]
            # Center illustration feature
            cv2.circle(canvas, (x + col_w // 2, y + row_h // 2), 70, (255, 255, 255), -1)
            idx += 1
            
    img_path = tmp_path / "desktop_4_3_comic.png"
    cv2.imwrite(str(img_path), canvas)
    return img_path


@pytest.fixture
def mobile_9_16_comic(tmp_path) -> Path:
    """Creates a synthetic 9:16 mobile comic strip (1080x1920, 2 columns x 3 rows)
    with distinct panel borders and artwork inside.
    """
    w, h = 1080, 1920  # 9:16 ratio = 0.5625
    canvas = np.full((h, w, 3), 245, dtype=np.uint8)  # Off-white gutters
    
    col_w = (w - 60) // 2
    row_h = (h - 80) // 3
    
    colors = [
        (60, 60, 220),   # 1
        (60, 200, 60),   # 2
        (220, 60, 60),   # 3
        (60, 200, 200),  # 4
        (200, 60, 200),  # 5
        (200, 200, 60),  # 6
    ]
    
    idx = 0
    for r in range(3):
        for c in range(2):
            x = 20 + c * (col_w + 20)
            y = 20 + r * (row_h + 20)
            # Black panel border stroke
            cv2.rectangle(canvas, (x, y), (x + col_w, y + row_h), (0, 0, 0), 5)
            # Inner artwork
            canvas[y + 5:y + row_h - 5, x + 5:x + col_w - 5] = colors[idx]
            cv2.circle(canvas, (x + col_w // 2, y + row_h // 2), 50, (255, 255, 255), -1)
            idx += 1
            
    img_path = tmp_path / "mobile_9_16_comic.png"
    cv2.imwrite(str(img_path), canvas)
    return img_path


def test_format_and_layout_detection():
    """Verifies automatic detection of 4:3 Desktop vs 9:16 Mobile."""
    # Desktop 4:3 (2400x1800)
    fmt_d, lay_d, def_w_d, def_h_d = detect_comic_format_and_layout(2400, 1800)
    assert fmt_d == "desktop"
    assert lay_d == "3x2"
    assert def_w_d == 1920
    assert def_h_d == 1080

    # Mobile 9:16 (1080x1920)
    fmt_m, lay_m, def_w_m, def_h_m = detect_comic_format_and_layout(1080, 1920)
    assert fmt_m == "mobile"
    assert lay_m == "2x3"
    assert def_w_m == 1080
    assert def_h_m == 1920


def test_desktop_4_3_analysis(desktop_4_3_comic, tmp_path):
    """Verifies analysis detects desktop format and 3x2 layout with 6 panels in correct reading order."""
    analysis = analyze_comic(str(desktop_4_3_comic), output_dir=str(tmp_path))
    assert analysis["format"] == "desktop"
    assert analysis["layout"] == "3x2"
    assert analysis["panel_count"] == 6
    assert len(analysis["panels"]) == 6
    # Reading order: top row (1, 2, 3), bottom row (4, 5, 6)
    p_ids = [p["id"] for p in analysis["panels"]]
    assert p_ids == [1, 2, 3, 4, 5, 6]
    # Check top row is above bottom row
    assert analysis["panels"][0]["y"] < analysis["panels"][3]["y"]
    assert analysis["panels"][1]["y"] < analysis["panels"][4]["y"]


def test_mobile_9_16_analysis(mobile_9_16_comic, tmp_path):
    """Verifies analysis detects mobile format and 2x3 layout with 6 panels in correct reading order."""
    analysis = analyze_comic(str(mobile_9_16_comic), output_dir=str(tmp_path))
    assert analysis["format"] == "mobile"
    assert analysis["layout"] == "2x3"
    assert analysis["panel_count"] == 6
    assert len(analysis["panels"]) == 6
    # Reading order: row 1 (1, 2), row 2 (3, 4), row 3 (5, 6)
    p_ids = [p["id"] for p in analysis["panels"]]
    assert p_ids == [1, 2, 3, 4, 5, 6]
    assert analysis["panels"][0]["y"] < analysis["panels"][2]["y"] < analysis["panels"][4]["y"]
    assert analysis["panels"][1]["y"] < analysis["panels"][3]["y"] < analysis["panels"][5]["y"]


def test_borderless_framing_guarantee(desktop_4_3_comic, tmp_path):
    """Verifies that camera viewports for story areas stay strictly inside the panel interior,
    completely excluding panel borders, frames, and gutters.
    """
    analysis = analyze_comic(str(desktop_4_3_comic), output_dir=str(tmp_path))
    for panel_dict in analysis["panels"]:
        from models.schemas import Panel
        p = Panel(**panel_dict)
        start_vp, end_vp = compute_panel_viewports(
            panel=p,
            image_width=analysis["image_width"],
            image_height=analysis["image_height"],
            safe_margin=0.08,
            target_aspect=16.0 / 9.0,
        )
        # Check start viewport is strictly inside panel bounds (excluding borders)
        assert start_vp.x >= p.x, f"Viewport left edge outside panel {p.id}"
        assert start_vp.y >= p.y, f"Viewport top edge outside panel {p.id}"
        assert start_vp.x + start_vp.width <= p.x + p.width, f"Viewport right edge outside panel {p.id}"
        assert start_vp.y + start_vp.height <= p.y + p.height, f"Viewport bottom edge outside panel {p.id}"
        # Check aspect ratio
        aspect = start_vp.width / start_vp.height
        assert abs(aspect - (16.0 / 9.0)) < 0.01

        # Check end viewport (slow_push) is also strictly inside
        assert end_vp.x >= p.x
        assert end_vp.y >= p.y
        assert end_vp.x + end_vp.width <= p.x + p.width
        assert end_vp.y + end_vp.height <= p.y + p.height


def test_continuous_canvas_transitions(desktop_4_3_comic, tmp_path):
    """Verifies that between-panel transitions glide directly across the canvas without zooming out to the full grid."""
    analysis = analyze_comic(str(desktop_4_3_comic), output_dir=str(tmp_path))
    plan = create_camera_plan(
        analysis=analysis,
        backtrack_to_start=False,
        panel_duration_seconds=3.0,
        transition_duration_seconds=1.5,
        framing="crop", output_dir=str(tmp_path),
    )

    assert plan["format"] == "desktop"
    assert plan["layout"] == "3x2"
    assert plan["show_full_comic_between_panels"] is False

    plan_obj = CameraPlan(**plan)
    # Check shot 4 (transition from Panel 1 to Panel 2)
    t_trans = 2.0 + 1.5 + 3.0 + 0.75  # halfway through panel 1 -> 2 transition
    mid_vp = get_viewport_at_time(
        plan=plan_obj,
        time_seconds=t_trans,
        show_full_comic_transitions=False,
    )
    # The mid transition viewport width must NOT equal the full comic width (it does not zoom out to grid)
    full_vp = compute_full_comic_viewport(analysis["image_width"], analysis["image_height"], 16/9)
    assert mid_vp.width < full_vp.width * 0.9, "Transition zoomed out to full comic grid instead of continuous travel!"


def test_desktop_4_3_render(desktop_4_3_comic, tmp_path):
    """End-to-end render test: 4:3 desktop comic produces horizontal desktop video."""
    out_video = tmp_path / "desktop_output.mp4"
    result = create_comic_video(
        image=str(desktop_4_3_comic),
        output=str(out_video),
        panel_duration_seconds=0.6,
        transition_duration_seconds=0.4,
        intro_duration_seconds=0.4,
        outro_duration_seconds=0.4,
        fps=30,
        framing="crop", output_dir=str(tmp_path),
    )

    assert result["status"] == "success"
    assert result["format"] == "desktop"
    assert result["layout"] == "3x2"
    assert out_video.is_file()

    meta = inspect_output(str(out_video))
    assert meta["width"] == 1920
    assert meta["height"] == 1080
    assert meta["has_audio"] is False


def test_mobile_9_16_render(mobile_9_16_comic, tmp_path):
    """End-to-end render test: 9:16 mobile comic produces vertical mobile video."""
    out_video = tmp_path / "mobile_output.mp4"
    result = create_comic_video(
        image=str(mobile_9_16_comic),
        output=str(out_video),
        panel_duration_seconds=0.6,
        transition_duration_seconds=0.4,
        intro_duration_seconds=0.4,
        outro_duration_seconds=0.4,
        fps=30,
        framing="crop", output_dir=str(tmp_path),
    )

    assert result["status"] == "success"
    assert result["format"] == "mobile"
    assert result["layout"] == "2x3"
    assert out_video.is_file()

    meta = inspect_output(str(out_video))
    assert meta["width"] == 1080
    assert meta["height"] == 1920
    assert meta["has_audio"] is False


@pytest.mark.parametrize("fixture_name,layout", [("desktop_4_3_comic", "3x2"), ("mobile_9_16_comic", "2x3")])
@pytest.mark.parametrize("mode,resolution", [("desktop", {"width":1920,"height":1080}), ("mobile", {"width":1080,"height":1920})])
def test_independent_modes_and_exact_backtrack(request, fixture_name, layout, mode, resolution, tmp_path):
    image = request.getfixturevalue(fixture_name)
    analysis = analyze_comic(str(image), format=mode, output_dir=str(tmp_path))
    assert analysis["layout"] == layout
    plan = create_camera_plan(analysis, format=mode, framing="crop", output_dir=str(tmp_path))
    assert plan["resolution"] == resolution
    assert plan["layout"] == layout
    shots = plan["shots"]
    obj = CameraPlan(**plan)
    for i, shot in enumerate(shots):
        if shot["type"] != "panel":
            continue
        approach, push = shots[i-1], shot
        reverse_push, reverse_approach = shots[i+1:i+3]
        for forward, reverse in [(push, reverse_push), (approach, reverse_approach)]:
            assert reverse["movement"] == "backtrack"
            assert forward["start_viewport"] == reverse["end_viewport"]
            assert forward["end_viewport"] == reverse["start_viewport"]
            for progress in [0.1, 0.3, 0.6, 0.9]:
                a = get_viewport_at_time(obj, forward["start"] + progress * forward["duration"])
                b = get_viewport_at_time(obj, reverse["start"] + (1-progress) * reverse["duration"])
                assert list(a.model_dump().values()) == pytest.approx(list(b.model_dump().values()))
    for a,b in zip(shots, shots[1:]):
        assert a["end_viewport"] == b["start_viewport"]
        assert a["end"] == b["start"]
    result = create_comic_video(str(image), format=mode, width=320 if mode=="desktop" else 180,
        height=180 if mode=="desktop" else 320, fps=10, panel_duration_seconds=0.2,
        transition_duration_seconds=0.2, intro_duration_seconds=0.2, outro_duration_seconds=0.2,
        output=str(tmp_path / "cross_mode.mp4"), framing="crop", output_dir=str(tmp_path))
    assert result["layout"] == layout
    assert result["format"] == mode
