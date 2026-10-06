"""Tests for camera plan generation, sequence, presets, and overrides."""

import pytest
from mcp_tools.create_camera_plan import create_camera_plan


@pytest.fixture
def mock_analysis_dict():
    """Mock analysis output with 6 panels."""
    return {
        "image_path": "comic.png",
        "image_width": 1920,
        "image_height": 1080,
        "panel_count": 6,
        "layout": "3x2",
        "confidence": 0.95,
        "panels": [
            {"id": 1, "x": 0, "y": 0, "width": 640, "height": 540, "focus_x": 320, "focus_y": 270, "focus_type": "face", "confidence": 1.0},
            {"id": 2, "x": 640, "y": 0, "width": 640, "height": 540, "focus_x": 960, "focus_y": 270, "focus_type": "object", "confidence": 1.0},
            {"id": 3, "x": 1280, "y": 0, "width": 640, "height": 540, "focus_x": 1600, "focus_y": 270, "focus_type": "center", "confidence": 1.0},
            {"id": 4, "x": 0, "y": 540, "width": 640, "height": 540, "focus_x": 320, "focus_y": 810, "focus_type": "center", "confidence": 1.0},
            {"id": 5, "x": 640, "y": 540, "width": 640, "height": 540, "focus_x": 960, "focus_y": 810, "focus_type": "face", "confidence": 1.0},
            {"id": 6, "x": 1280, "y": 540, "width": 640, "height": 540, "focus_x": 1600, "focus_y": 810, "focus_type": "object", "confidence": 1.0},
        ],
    }


def test_default_sequence_and_shots(mock_analysis_dict, tmp_path):
    """Verifies default sequence [1, 2, 3, 4, 5, 6] creates proper shots."""
    plan = create_camera_plan(
        analysis=mock_analysis_dict,
        panel_duration_seconds=4.0,
        transition_duration_seconds=1.5,
        include_intro=True,
        include_outro=True,
        output_dir=str(tmp_path),
    )
    
    assert plan["sequence"] == [1, 2, 3, 4, 5, 6]
    
    shots = plan["shots"]
    # First shot must be intro full_comic
    assert shots[0]["type"] == "full_comic"
    assert shots[0]["duration"] == 2.0
    
    # Last shot must be outro full_comic
    assert shots[-1]["type"] == "full_comic"
    
    # Check panel shots
    panel_shots = [s for s in shots if s["type"] == "panel"]
    assert len(panel_shots) == 6
    assert [s["panel_id"] for s in panel_shots] == [1, 2, 3, 4, 5, 6]


def test_custom_sequence(mock_analysis_dict, tmp_path):
    """Verifies custom panel reading order."""
    custom_seq = [6, 5, 4, 3, 2, 1]
    plan = create_camera_plan(
        analysis=mock_analysis_dict,
        sequence=custom_seq,
        output_dir=str(tmp_path),
    )
    
    panel_shots = [s for s in plan["shots"] if s["type"] == "panel"]
    assert [s["panel_id"] for s in panel_shots] == custom_seq


def test_presets_affect_movement(mock_analysis_dict, tmp_path):
    """Verifies that preset affects movement style and zoom factors."""
    plan_edu = create_camera_plan(mock_analysis_dict, preset="educational", output_dir=str(tmp_path))
    plan_wide = create_camera_plan(mock_analysis_dict, preset="wide", output_dir=str(tmp_path))
    
    edu_panel_shots = [s for s in plan_edu["shots"] if s["type"] == "panel"]
    wide_panel_shots = [s for s in plan_wide["shots"] if s["type"] == "panel"]
    
    assert edu_panel_shots[0]["movement"] == "slow_push"
    assert wide_panel_shots[0]["movement"] == "hold"


def test_intro_and_outro_toggles(mock_analysis_dict, tmp_path):
    """Verifies that intro and outro can be independently omitted."""
    plan_no_intro = create_camera_plan(
        mock_analysis_dict,
        include_intro=False,
        include_outro=True,
        output_dir=str(tmp_path),
    )
    # First shot should be transition, not full_comic
    assert plan_no_intro["shots"][0]["type"] == "transition"

    plan_no_outro = create_camera_plan(
        mock_analysis_dict,
        include_intro=True,
        include_outro=False,
        output_dir=str(tmp_path),
    )
    # Last shot should be a panel, not full_comic
    assert plan_no_outro["shots"][-1]["type"] == "panel"
