"""Configuration module for Comic Video MCP Server."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Dict, Any, Tuple, Optional


def find_ffmpeg_binaries() -> Tuple[Optional[str], Optional[str]]:
    """Locates ffmpeg and ffprobe executables using multiple discovery strategies.
    
    Order of preference:
    1. Environment variables FFMPEG_PATH and FFPROBE_PATH
    2. System PATH (via shutil.which)
    3. static_ffmpeg package (fetches platform binaries if needed)
    4. imageio_ffmpeg package
    5. Standard Windows installation paths
    """
    ffmpeg_path: Optional[str] = os.environ.get("FFMPEG_PATH")
    ffprobe_path: Optional[str] = os.environ.get("FFPROBE_PATH")

    # 1. Direct environment variable check
    if ffmpeg_path and Path(ffmpeg_path).is_file():
        ffmpeg_valid = ffmpeg_path
    else:
        ffmpeg_valid = None

    if ffprobe_path and Path(ffprobe_path).is_file():
        ffprobe_valid = ffprobe_path
    else:
        ffprobe_valid = None

    # 2. System PATH
    if not ffmpeg_valid:
        which_ffmpeg = shutil.which("ffmpeg")
        if which_ffmpeg:
            ffmpeg_valid = which_ffmpeg

    if not ffprobe_valid:
        which_ffprobe = shutil.which("ffprobe")
        if which_ffprobe:
            ffprobe_valid = which_ffprobe

    # 3. static_ffmpeg
    if not ffmpeg_valid or not ffprobe_valid:
        try:
            import static_ffmpeg
            s_ffmpeg, s_ffprobe = static_ffmpeg.run.get_or_fetch_platform_executables_else_raise()
            if not ffmpeg_valid and s_ffmpeg and Path(s_ffmpeg).is_file():
                ffmpeg_valid = s_ffmpeg
            if not ffprobe_valid and s_ffprobe and Path(s_ffprobe).is_file():
                ffprobe_valid = s_ffprobe
        except Exception:
            pass

    # 4. imageio_ffmpeg (provides ffmpeg)
    if not ffmpeg_valid:
        try:
            import imageio_ffmpeg
            i_ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
            if i_ffmpeg and Path(i_ffmpeg).is_file():
                ffmpeg_valid = i_ffmpeg
        except Exception:
            pass

    # 5. Common Windows fallbacks
    win_ffmpeg_paths = [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\tools\ffmpeg\bin\ffmpeg.exe",
    ]
    win_ffprobe_paths = [
        r"C:\ffmpeg\bin\ffprobe.exe",
        r"C:\Program Files\ffmpeg\bin\ffprobe.exe",
        r"C:\tools\ffmpeg\bin\ffprobe.exe",
    ]

    if not ffmpeg_valid:
        for p in win_ffmpeg_paths:
            if Path(p).is_file():
                ffmpeg_valid = p
                break

    if not ffprobe_valid:
        for p in win_ffprobe_paths:
            if Path(p).is_file():
                ffprobe_valid = p
                break

    return ffmpeg_valid, ffprobe_valid


# Resolution & Video Defaults
DEFAULT_DESKTOP_WIDTH: int = int(os.environ.get("DEFAULT_DESKTOP_WIDTH", 1920))
DEFAULT_DESKTOP_HEIGHT: int = int(os.environ.get("DEFAULT_DESKTOP_HEIGHT", 1080))
DEFAULT_MOBILE_WIDTH: int = int(os.environ.get("DEFAULT_MOBILE_WIDTH", 1080))
DEFAULT_MOBILE_HEIGHT: int = int(os.environ.get("DEFAULT_MOBILE_HEIGHT", 1920))

DEFAULT_WIDTH: int = int(os.environ.get("DEFAULT_WIDTH", DEFAULT_DESKTOP_WIDTH))
DEFAULT_HEIGHT: int = int(os.environ.get("DEFAULT_HEIGHT", DEFAULT_DESKTOP_HEIGHT))
DEFAULT_FPS: int = int(os.environ.get("DEFAULT_FPS", 30))

# Timing Defaults (seconds)
DEFAULT_PANEL_DURATION: float = float(os.environ.get("DEFAULT_PANEL_DURATION", 5.0))
DEFAULT_TRANSITION_DURATION: float = float(os.environ.get("DEFAULT_TRANSITION_DURATION", 2.0))
DEFAULT_INTRO_DURATION: float = float(os.environ.get("DEFAULT_INTRO_DURATION", 2.0))
DEFAULT_OUTRO_DURATION: float = float(os.environ.get("DEFAULT_OUTRO_DURATION", 2.0))

# Continuous Canvas Mode (False means camera travels continuously across the single canvas without zooming back out to the grid)
DEFAULT_SHOW_FULL_COMIC_BETWEEN_PANELS: bool = os.environ.get("SHOW_FULL_COMIC_BETWEEN_PANELS", "false").lower() in ("1", "true", "yes")

# Preset Defaults
DEFAULT_PRESET: str = os.environ.get("DEFAULT_PRESET", "educational")

# Output Directory
OUTPUT_DIR: Path = Path(os.environ.get("OUTPUT_DIR", "output"))

# Resolved FFmpeg and FFprobe binaries
FFMPEG_BIN, FFPROBE_BIN = find_ffmpeg_binaries()

# Camera Presets configuration (safe_margin insets inside panels to ensure borders and gutters are never visible)
PRESETS: Dict[str, Dict[str, Any]] = {
    "educational": {
        "description": "Mostly calm framing with very subtle push-in, prioritizing readability and calm pacing",
        "default_movement": "slow_push",
        "zoom_factor": 1.05,
        "easing": "smootherstep",
        "safe_margin": 0.08,
    },
    "gentle": {
        "description": "Ultra slow, barely perceptible camera motion",
        "default_movement": "slow_push",
        "zoom_factor": 1.03,
        "easing": "smootherstep",
        "safe_margin": 0.08,
    },
    "emotional": {
        "description": "Slow push-in focused on characters/faces",
        "default_movement": "slow_push",
        "zoom_factor": 1.10,
        "easing": "smootherstep",
        "safe_margin": 0.08,
    },
    "object_focus": {
        "description": "Slow push-in centered on important object or high saliency region",
        "default_movement": "slow_push",
        "zoom_factor": 1.08,
        "easing": "smootherstep",
        "safe_margin": 0.08,
    },
    "wide": {
        "description": "Minimal zoom and pan, framing the entire panel interior with clean border clearance",
        "default_movement": "hold",
        "zoom_factor": 1.01,
        "easing": "smootherstep",
        "safe_margin": 0.08,
    },
}
