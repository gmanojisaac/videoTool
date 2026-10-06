"""Comic Video MCP Server

A Model Context Protocol server that transforms 6-tile comic sheets into
cinematic educational videos using a virtual 2D camera viewport rendered via FFmpeg.
"""

from __future__ import annotations

import sys
from typing import Dict, Any, Optional, List, Union

try:
    from mcp.server.mcpserver import MCPServer
    ServerClass = MCPServer
except ImportError:
    from mcp.server.fastmcp import FastMCP
    ServerClass = FastMCP

from config import (
    DEFAULT_WIDTH,
    DEFAULT_HEIGHT,
    DEFAULT_FPS,
    DEFAULT_PANEL_DURATION,
    DEFAULT_TRANSITION_DURATION,
    DEFAULT_INTRO_DURATION,
    DEFAULT_OUTRO_DURATION,
    DEFAULT_PRESET,
)
from mcp_tools import (
    analyze_comic as analyze_comic_impl,
    create_camera_plan as create_camera_plan_impl,
    preview_camera_plan as preview_camera_plan_impl,
    render_video as render_video_impl,
    create_comic_video as create_comic_video_impl,
    inspect_output as inspect_output_impl,
)

# Initialize MCP Server
app = ServerClass(name="comic-video-mcp")


@app.tool()
def analyze_comic(
    image: str,
    manual_panels: Optional[List[Dict[str, Any]]] = None,
    output_dir: Optional[str] = None,
    format: Optional[str] = None,
    layout: Optional[str] = None,
) -> Dict[str, Any]:
    """Analyzes a comic sheet, automatically detects format (Desktop/Mobile) and layout (3x2/2x3).
    
    Generates:
    - analysis.json
    - panel_detection_preview.png (diagnostic overlay image)
    
    Args:
        image: Absolute or relative path to the source comic image (PNG/JPG).
        manual_panels: Optional list of panel coordinates (x, y, width, height) to override auto-detection.
        output_dir: Output directory where analysis.json and diagnostic preview will be written.
        format: Optional format ('desktop' or 'mobile'). Auto-detected from aspect ratio if omitted.
        layout: Optional grid layout ('3x2' or '2x3'). Auto-detected if omitted.
    """
    return analyze_comic_impl(
        image=image,
        manual_panels=manual_panels,
        output_dir=output_dir,
        format=format,
        layout=layout,
    )


@app.tool()
def create_camera_plan(
    analysis: Union[str, Dict[str, Any]],
    panel_duration_seconds: float = DEFAULT_PANEL_DURATION,
    transition_duration_seconds: float = DEFAULT_TRANSITION_DURATION,
    preset: str = DEFAULT_PRESET,
    include_intro: bool = True,
    include_outro: bool = True,
    show_full_comic_between_panels: bool = False,
    sequence: Optional[List[int]] = None,
    intro_duration_seconds: float = DEFAULT_INTRO_DURATION,
    outro_duration_seconds: float = DEFAULT_OUTRO_DURATION,
    width: Optional[int] = None,
    height: Optional[int] = None,
    fps: int = DEFAULT_FPS,
    output_dir: Optional[str] = None,
    format: Optional[str] = None,
    layout: Optional[str] = None,
) -> Dict[str, Any]:
    """Generates a continuous canvas camera storyboard treating the comic as one single scene.
    
    The camera travels seamlessly across the canvas between story areas without visible panel
    borders, frames, or slideshow tile transitions.
    
    Generates:
    - camera_plan.json
    
    Args:
        analysis: Path to analysis.json or raw analysis dict from analyze_comic.
        panel_duration_seconds: Duration spent displaying each panel (default: 5.0).
        transition_duration_seconds: Camera travel time between panels (default: 2.0).
        preset: Movement preset: 'educational', 'gentle', 'emotional', 'object_focus', 'wide'.
        include_intro: Start with full comic canvas overview.
        include_outro: Smoothly pull back to full comic canvas overview at the end.
        show_full_comic_between_panels: False for seamless continuous canvas; True to zoom out to grid.
        sequence: Custom reading order sequence of panel IDs (e.g. [1, 2, 3, 4, 5, 6]).
        intro_duration_seconds: Duration of full comic intro shot (default: 2.0).
        outro_duration_seconds: Duration of full comic outro shot (default: 2.0).
        width: Video width (default: auto-detected 1920 for desktop, 1080 for mobile).
        height: Video height (default: auto-detected 1080 for desktop, 1920 for mobile).
        fps: Frames per second (default: 30).
        output_dir: Output directory where camera_plan.json will be written.
        format: Optional format override ('desktop' or 'mobile').
        layout: Optional layout override ('3x2' or '2x3').
    """
    return create_camera_plan_impl(
        analysis=analysis,
        panel_duration_seconds=panel_duration_seconds,
        transition_duration_seconds=transition_duration_seconds,
        preset=preset,
        include_intro=include_intro,
        include_outro=include_outro,
        show_full_comic_between_panels=show_full_comic_between_panels,
        sequence=sequence,
        intro_duration_seconds=intro_duration_seconds,
        outro_duration_seconds=outro_duration_seconds,
        width=width,
        height=height,
        fps=fps,
        output_dir=output_dir,
        format=format,
        layout=layout,
    )


@app.tool()
def preview_camera_plan(
    camera_plan: Union[str, Dict[str, Any]],
    resolution_scale: float = 0.5,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Generates a low-resolution preview MP4 and visual trajectory diagram.
    
    Generates:
    - camera_preview.mp4 (e.g. 960x540)
    - camera_plan_preview.png (diagram of camera path over comic)
    
    Args:
        camera_plan: Path to camera_plan.json or camera plan dictionary.
        resolution_scale: Preview resolution multiplier (default: 0.5).
        output_dir: Output directory for preview files.
    """
    return preview_camera_plan_impl(
        camera_plan=camera_plan,
        resolution_scale=resolution_scale,
        output_dir=output_dir,
    )


@app.tool()
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
    
    Generates:
    - comic_video.mp4 (H.264, yuv420p, silent or with optional voiceover audio)
    
    Args:
        image: Path to comic image (optional if defined in camera_plan).
        camera_plan: Path to camera_plan.json or camera plan dictionary.
        output: Destination video file path (default: output/comic_video.mp4).
        width: Video width (optional override).
        height: Video height (optional override).
        fps: Frames per second (optional override).
        audio: False for silent, or path to voiceover audio file to mux into video.
    """
    return render_video_impl(
        image=image,
        camera_plan=camera_plan,
        output=output,
        width=width,
        height=height,
        fps=fps,
        audio=audio,
    )


@app.tool()
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
    """End-to-end continuous canvas pipeline: treats the comic strip as ONE continuous canvas.
    
    Automatically detects format (Desktop 4:3 3x2 or Mobile 9:16 2x3), builds seamless camera
    path without showing borders, frames, or slideshow cuts, and renders final MP4 via FFmpeg.
        
    Args:
        image: Path to comic PNG/JPG image file.
        output: Destination MP4 file path (default: output/comic_video.mp4).
        panel_duration_seconds: Time spent displaying each story area (default: 5.0).
        transition_duration_seconds: Time traveling between story areas (default: 2.0).
        intro_duration_seconds: Duration of full comic intro (default: 2.0).
        outro_duration_seconds: Duration of full comic outro (default: 2.0).
        preset: Movement preset: 'educational', 'gentle', 'emotional', 'object_focus', 'wide'.
        include_intro: Start with full comic overview.
        include_outro: Pull back to full comic overview at the end.
        show_full_comic_between_panels: False for seamless continuous canvas; True to zoom out to grid.
        manual_panels: Optional manual panel coordinate overrides.
        sequence: Custom reading order sequence of panel IDs.
        width: Video width (default: auto-detected 1920 for desktop, 1080 for mobile).
        height: Video height (default: auto-detected 1080 for desktop, 1920 for mobile).
        fps: Frames per second (default: 30).
        audio: False or path to audio voiceover file.
        output_dir: Output directory for all generated artifacts.
        format: Optional format override ('desktop' or 'mobile').
        layout: Optional layout override ('3x2' or '2x3').
    """
    return create_comic_video_impl(
        image=image,
        output=output,
        panel_duration_seconds=panel_duration_seconds,
        transition_duration_seconds=transition_duration_seconds,
        intro_duration_seconds=intro_duration_seconds,
        outro_duration_seconds=outro_duration_seconds,
        preset=preset,
        include_intro=include_intro,
        include_outro=include_outro,
        show_full_comic_between_panels=show_full_comic_between_panels,
        manual_panels=manual_panels,
        sequence=sequence,
        width=width,
        height=height,
        fps=fps,
        audio=audio,
        output_dir=output_dir,
        format=format,
        layout=layout,
    )


@app.tool()
def inspect_output(video_path: str) -> Dict[str, Any]:
    """Inspects an MP4 video file and returns its technical parameters.
    
    Returns:
    - file path
    - file size in bytes
    - duration in seconds
    - width and height
    - FPS
    - codec
    - audio stream presence
    
    Args:
        video_path: Path to the video file to inspect.
    """
    return inspect_output_impl(video_path=video_path)


def main():
    """Runs the MCP server over standard I/O."""
    app.run(transport="stdio")


if __name__ == "__main__":
    main()
