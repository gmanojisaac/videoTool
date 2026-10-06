"""MCP Tool: render_video"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, Optional, Union

from config import OUTPUT_DIR, DEFAULT_WIDTH, DEFAULT_HEIGHT, DEFAULT_FPS
from models.schemas import CameraPlan, Resolution
from video.renderer import render_camera_plan_video
from video.ffmpeg import mux_audio_into_video, inspect_video_file


def render_video(
    image: Optional[str] = None,
    camera_plan: Optional[Union[str, Dict[str, Any]]] = None,
    output: Optional[str] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    fps: Optional[int] = None,
    audio: Optional[Union[str, bool]] = False,
) -> Dict[str, Any]:
    """Renders final high-quality cinematic educational comic video using FFmpeg.
    
    Args:
        image: Path to source comic image (optional if specified inside camera_plan).
        camera_plan: Path to camera_plan.json or camera plan dictionary.
        output: Destination MP4 file path (default output/comic_video.mp4).
        width: Video width (overrides camera plan if provided).
        height: Video height (overrides camera plan if provided).
        fps: Video framerate (overrides camera plan if provided).
        audio: False or None for silent video, or path to voiceover audio file.
        
    Returns:
        Rendered video metrics and verification results.
    """
    if camera_plan is None:
        raise ValueError("Parameter 'camera_plan' must be provided.")
        
    if isinstance(camera_plan, (str, Path)):
        p = Path(camera_plan).resolve()
        if not p.is_file():
            raise FileNotFoundError(f"Camera plan file not found: {p}")
        with open(p, "r", encoding="utf-8") as f:
            plan_data = json.load(f)
    elif isinstance(camera_plan, dict):
        plan_data = dict(camera_plan)
    else:
        raise ValueError("Invalid camera_plan parameter; must be file path or dictionary.")

    # Override image if passed explicitly
    if image:
        plan_data["image_path"] = str(Path(image).resolve())
        
    # Override resolution if passed explicitly
    if width is not None and height is not None:
        plan_data["resolution"] = {"width": width, "height": height}
    if fps is not None:
        plan_data["fps"] = fps

    plan_obj = CameraPlan(**plan_data)
    
    # Destination output path
    if output:
        out_path = Path(output).resolve()
    else:
        out_path = (OUTPUT_DIR / "comic_video.mp4").resolve()
        
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    # If audio is requested, first render silent temp video, then mux
    temp_silent_path = out_path.with_name(f"{out_path.stem}_silent{out_path.suffix}") if audio else out_path
    
    # Render video via FFmpeg pipe
    inspection = render_camera_plan_video(
        plan=plan_obj,
        output_path=temp_silent_path,
        resolution_scale=1.0,
    )
    
    # Handle optional audio muxing
    audio_warning = None
    if audio and isinstance(audio, (str, Path)):
        a_path = Path(audio).resolve()
        if a_path.is_file():
            success, err = mux_audio_into_video(temp_silent_path, a_path, out_path)
            if success:
                inspection = inspect_video_file(out_path)
                # Cleanup temp silent file if different
                if temp_silent_path != out_path and temp_silent_path.is_file():
                    temp_silent_path.unlink()
            else:
                audio_warning = f"Failed to mux audio: {err}"
        else:
            audio_warning = f"Audio file not found: {a_path}"

    return {
        "status": "success",
        "video_path": str(out_path),
        "file_size_bytes": inspection.file_size_bytes,
        "duration_seconds": inspection.duration_seconds,
        "width": inspection.width,
        "height": inspection.height,
        "fps": inspection.fps,
        "codec": inspection.codec,
        "has_audio": inspection.has_audio,
        "audio_warning": audio_warning,
    }
