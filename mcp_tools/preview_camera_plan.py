"""MCP Tool: preview_camera_plan"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, Optional, Union

from config import OUTPUT_DIR
from models.schemas import CameraPlan
from video.renderer import render_camera_plan_video, generate_camera_plan_preview_image


def preview_camera_plan(
    camera_plan: Union[str, Dict[str, Any]],
    resolution_scale: float = 0.5,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Generates a low-resolution preview video (camera_preview.mp4) and
    a visual camera trajectory diagram (camera_plan_preview.png).
    
    Args:
        camera_plan: Path to camera_plan.json or camera plan dictionary.
        resolution_scale: Scale factor for video preview (default 0.5 = 960x540).
        output_dir: Output directory for preview files.
        
    Returns:
        Dictionary with preview video and preview image paths and metrics.
    """
    if isinstance(camera_plan, (str, Path)):
        p = Path(camera_plan).resolve()
        if not p.is_file():
            raise FileNotFoundError(f"Camera plan file not found: {p}")
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    elif isinstance(camera_plan, dict):
        data = camera_plan
    else:
        raise ValueError("Invalid camera_plan parameter; must be file path or dictionary.")

    plan_obj = CameraPlan(**data)
    
    out_dir = Path(output_dir).resolve() if output_dir else OUTPUT_DIR.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    
    preview_video_path = out_dir / "camera_preview.mp4"
    preview_image_path = out_dir / "camera_plan_preview.png"
    
    # 1. Render visual camera diagram
    generate_camera_plan_preview_image(plan_obj, preview_image_path)
    
    # 2. Render low-res preview video
    inspection = render_camera_plan_video(
        plan=plan_obj,
        output_path=preview_video_path,
        resolution_scale=resolution_scale,
    )
    
    return {
        "preview_video": str(preview_video_path),
        "preview_image": str(preview_image_path),
        "resolution": f"{inspection.width}x{inspection.height}",
        "fps": inspection.fps,
        "duration_seconds": inspection.duration_seconds,
        "file_size_bytes": inspection.file_size_bytes,
        "codec": inspection.codec,
    }
