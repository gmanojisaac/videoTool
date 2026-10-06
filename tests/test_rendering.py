"""Tests for video rendering, preview generation, metadata inspection, and source safety."""

import cv2
import numpy as np
import pytest
from pathlib import Path

from video.ffmpeg import get_ffmpeg_executable, get_ffprobe_executable, inspect_video_file
from video.renderer import calculate_file_sha256
from mcp_tools.create_comic_video import create_comic_video
from mcp_tools.preview_camera_plan import preview_camera_plan
from mcp_tools.inspect_output import inspect_output


@pytest.fixture
def sample_comic_file(tmp_path) -> Path:
    """Creates a sample 6-tile comic sheet image for rendering tests."""
    w, h = 1920, 1080
    sheet = np.full((h, w, 3), 240, dtype=np.uint8)
    
    col_w = (w - 40) // 3
    row_h = (h - 30) // 2
    
    for r in range(2):
        for c in range(3):
            x = 10 + c * (col_w + 10)
            y = 10 + r * (row_h + 10)
            # Fill panel with colored gradient
            sheet[y:y + row_h, x:x + col_w] = (40 + c * 60, 80 + r * 60, 160)
            cv2.putText(
                sheet,
                f"Panel {r * 3 + c + 1}",
                (x + 50, y + 100),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.5,
                (255, 255, 255),
                3,
            )
            
    img_path = tmp_path / "test_comic_sheet.png"
    cv2.imwrite(str(img_path), sheet)
    return img_path


def test_ffmpeg_and_ffprobe_exist():
    """Verifies that FFmpeg and FFprobe binaries are found on the system."""
    ffmpeg_bin = get_ffmpeg_executable()
    ffprobe_bin = get_ffprobe_executable()
    
    assert Path(ffmpeg_bin).is_file()
    assert Path(ffprobe_bin).is_file()


def test_source_safety_and_rendering(sample_comic_file, tmp_path):
    """Verifies complete rendering pipeline and asserts source image SHA-256 is untouched."""
    sha_before = calculate_file_sha256(sample_comic_file)
    
    out_video = tmp_path / "output_comic.mp4"
    
    # Run short 1-second-per-panel render for test speed
    result = create_comic_video(
        image=str(sample_comic_file),
        output=str(out_video),
        panel_duration_seconds=1.0,
        transition_duration_seconds=0.5,
        intro_duration_seconds=0.5,
        outro_duration_seconds=0.5,
        width=1280,
        height=720,
        fps=30,
        output_dir=str(tmp_path),
    )
    
    # Check source safety: SHA-256 must NOT change!
    sha_after = calculate_file_sha256(sample_comic_file)
    assert sha_before == sha_after, "SOURCE SAFETY FAILURE: Source comic file was modified!"
    
    # Verify video was created
    assert out_video.is_file()
    assert out_video.stat().st_size > 0
    
    # Inspect video
    meta = inspect_output(str(out_video))
    assert meta["width"] == 1280
    assert meta["height"] == 720
    assert abs(meta["fps"] - 30.0) < 1.0
    assert meta["codec"] in ("h264", "libx264")
    assert meta["has_audio"] is False  # Must be silent by default!


def test_preview_generation(sample_comic_file, tmp_path):
    """Verifies low-resolution preview video and camera plan preview diagram."""
    from mcp_tools.analyze_comic import analyze_comic
    from mcp_tools.create_camera_plan import create_camera_plan
    
    analysis = analyze_comic(str(sample_comic_file), output_dir=str(tmp_path))
    plan = create_camera_plan(
        analysis=analysis,
        panel_duration_seconds=1.0,
        transition_duration_seconds=0.5,
        output_dir=str(tmp_path),
    )
    
    preview_res = preview_camera_plan(
        camera_plan=plan,
        resolution_scale=0.25,
        output_dir=str(tmp_path),
    )
    
    assert Path(preview_res["preview_video"]).is_file()
    assert Path(preview_res["preview_image"]).is_file()
    assert preview_res["file_size_bytes"] > 0
