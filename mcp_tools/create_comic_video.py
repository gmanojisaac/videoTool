"""MCP Tool: create_comic_video (End-to-End Convenience Pipeline)"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, Optional, List, Union

from config import (
    OUTPUT_DIR,
    DEFAULT_PANEL_DURATION,
    DEFAULT_TRANSITION_DURATION,
    DEFAULT_INTRO_DURATION,
    DEFAULT_OUTRO_DURATION,
    DEFAULT_PRESET,
    DEFAULT_WIDTH,
    DEFAULT_HEIGHT,
    DEFAULT_FPS,
)
from mcp_tools.analyze_comic import analyze_comic
from mcp_tools.create_camera_plan import create_camera_plan
from mcp_tools.render_video import render_video


def create_comic_video(
    image: str,
    output: Optional[str] = None,
    panel_duration_seconds: float = DEFAULT_PANEL_DURATION,
    transition_duration_seconds: float = DEFAULT_TRANSITION_DURATION,
    intro_duration_seconds: float = DEFAULT_INTRO_DURATION,
    outro_duration_seconds: float = DEFAULT_OUTRO_DURATION,
    preset: str = DEFAULT_PRESET,
    include_intro: bool = True,
    include_outro: bool = True,
    show_full_comic_between_panels: bool = False,
    manual_panels: Optional[List[Dict[str, Any]]] = None,
    sequence: Optional[List[int]] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    fps: int = DEFAULT_FPS,
    audio: Optional[Union[str, bool]] = False,
    output_dir: Optional[str] = None,
    format: Optional[str] = None,
    layout: Optional[str] = None,
) -> Dict[str, Any]:
    """End-to-end continuous canvas pipeline: analyzes comic sheet (desktop 4:3 3x2 or mobile 9:16 2x3),
    generates seamless camera plan, and renders final MP4 using FFmpeg.
    
    Args:
        image: Path to comic PNG/JPG image file.
        output: Destination MP4 file path.
        panel_duration_seconds: Time spent per panel (default 5.0).
        transition_duration_seconds: Time traveling between panels (default 2.0).
        intro_duration_seconds: Duration of full comic intro (default 2.0).
        outro_duration_seconds: Duration of full comic outro (default 2.0).
        preset: Movement preset ('educational', 'gentle', 'emotional', 'object_focus', 'wide').
        include_intro: Whether to include full comic overview intro.
        include_outro: Whether to include full comic overview outro.
        show_full_comic_between_panels: False for continuous canvas travel; True for tile overview.
        manual_panels: Optional manual panel coordinate overrides.
        sequence: Custom reading order (default [1, 2, 3, 4, 5, 6]).
        width: Video width (default: auto-detected 1920 for desktop, 1080 for mobile).
        height: Video height (default: auto-detected 1080 for desktop, 1920 for mobile).
        fps: Video framerate (default 30).
        audio: False or path to audio voiceover file.
        output_dir: Output directory for all generated artifacts.
        format: Optional format override ('desktop' or 'mobile').
        layout: Optional layout override ('3x2' or '2x3').
        
    Returns:
        Summary dictionary with all artifact paths, metadata, format, layout, and status.
    """
    out_dir = Path(output_dir).resolve() if output_dir else OUTPUT_DIR.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    
    final_output = Path(output).resolve() if output else (out_dir / "comic_video.mp4")

    # Step 1: Analyze comic
    analysis_res = analyze_comic(
        image=image,
        manual_panels=manual_panels,
        output_dir=str(out_dir),
        format=format,
        layout=layout,
    )
    
    # Step 2: Create camera plan
    plan_res = create_camera_plan(
        analysis=analysis_res,
        panel_duration_seconds=panel_duration_seconds,
        transition_duration_seconds=transition_duration_seconds,
        intro_duration_seconds=intro_duration_seconds,
        outro_duration_seconds=outro_duration_seconds,
        preset=preset,
        include_intro=include_intro,
        include_outro=include_outro,
        show_full_comic_between_panels=show_full_comic_between_panels,
        sequence=sequence,
        width=width,
        height=height,
        fps=fps,
        output_dir=str(out_dir),
        format=format,
        layout=layout,
    )
    
    # Step 3: Render final video
    render_res = render_video(
        image=image,
        camera_plan=plan_res,
        output=str(final_output),
        width=width,
        height=height,
        fps=fps,
        audio=audio,
    )
    
    return {
        "status": "success",
        "video_path": render_res["video_path"],
        "analysis_file": analysis_res.get("analysis_file"),
        "diagnostic_preview": analysis_res.get("diagnostic_preview_path"),
        "camera_plan_file": plan_res.get("plan_file"),
        "duration_seconds": render_res["duration_seconds"],
        "resolution": f"{render_res['width']}x{render_res['height']}",
        "fps": render_res["fps"],
        "file_size_bytes": render_res["file_size_bytes"],
        "codec": render_res["codec"],
        "has_audio": render_res["has_audio"],
        "preset": preset,
        "format": plan_res.get("format", analysis_res.get("format", "desktop")),
        "layout": plan_res.get("layout", analysis_res.get("layout", "3x2")),
        "panel_count": analysis_res.get("panel_count", 6),
    }
