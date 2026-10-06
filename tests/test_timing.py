"""Tests for timeline continuity, duration calculation, and frame count."""

import pytest
from mcp_tools.create_camera_plan import create_camera_plan


@pytest.fixture
def mock_analysis():
    return {
        "image_path": "comic.png",
        "image_width": 1920,
        "image_height": 1080,
        "panels": [
            {"id": i, "x": (i - 1) * 300, "y": 0, "width": 300, "height": 300, "focus_x": (i - 1) * 300 + 150, "focus_y": 150}
            for i in range(1, 7)
        ],
    }


def test_timeline_continuity(mock_analysis, tmp_path):
    """Verifies that there are no gaps or overlaps between consecutive shots."""
    plan = create_camera_plan(
        analysis=mock_analysis,
        panel_duration_seconds=5.0,
        transition_duration_seconds=2.0,
        intro_duration_seconds=3.0,
        outro_duration_seconds=2.5,
        output_dir=str(tmp_path),
    )
    
    shots = plan["shots"]
    for i in range(len(shots) - 1):
        assert abs(shots[i]["end"] - shots[i + 1]["start"]) < 0.001, (
            f"Gap detected between shot {shots[i]['id']} and {shots[i+1]['id']}"
        )


def test_duration_formula(mock_analysis, tmp_path):
    """Verifies exact calculation of total duration."""
    panel_dur = 4.0
    trans_dur = 1.5
    intro_dur = 2.0
    outro_dur = 2.0
    num_panels = 6
    
    # 6 panels have:
    # 1 intro shot
    # 6 transitions into panels
    # 6 panel shots
    # 1 transition into outro
    # 1 outro shot
    expected_duration = intro_dur + (num_panels * trans_dur) + (num_panels * panel_dur) + trans_dur + outro_dur
    
    plan = create_camera_plan(
        analysis=mock_analysis,
        panel_duration_seconds=panel_dur,
        transition_duration_seconds=trans_dur,
        intro_duration_seconds=intro_dur,
        outro_duration_seconds=outro_dur,
        include_intro=True,
        include_outro=True,
        fps=30,
        output_dir=str(tmp_path),
    )
    
    assert abs(plan["total_duration"] - expected_duration) < 0.01
    assert plan["total_frames"] == int(round(expected_duration * 30))
