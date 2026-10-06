"""MCP Tool: inspect_output"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any

from video.ffmpeg import inspect_video_file


def inspect_output(video_path: str) -> Dict[str, Any]:
    """Inspects an MP4 video file and reports its technical metadata.
    
    Args:
        video_path: Path to the video file to inspect.
        
    Returns:
        Metadata including duration, dimensions, FPS, codec, file size, and audio status.
    """
    path = Path(video_path).resolve()
    result = inspect_video_file(path)
    return result.model_dump()
