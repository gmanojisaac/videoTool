"""Video rendering engine using FFmpeg pipe streaming."""

from __future__ import annotations

import cv2
import hashlib
import numpy as np
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, Callable

from models.schemas import CameraPlan, Viewport, Shot, InspectionResult
from video.camera import interpolate_viewports
from video.transitions import sample_transition_viewport
from video.ffmpeg import get_ffmpeg_executable, inspect_video_file


def calculate_file_sha256(file_path: str | Path) -> str:
    """Calculates SHA-256 hash of a file for source safety integrity verification."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def get_viewport_at_time(
    plan: CameraPlan,
    time_seconds: float,
    full_comic_viewport: Optional[Viewport] = None,
    show_full_comic_transitions: bool = False,
) -> Viewport:
    """Samples the active camera viewport at any given point in time."""
    t = max(0.0, min(plan.total_duration, time_seconds))
    
    # Locate active shot
    active_shot: Optional[Shot] = None
    for shot in plan.shots:
        if shot.start <= t <= shot.end:
            active_shot = shot
            break
            
    if active_shot is None:
        if plan.shots:
            active_shot = plan.shots[-1] if t >= plan.shots[-1].end else plan.shots[0]
        else:
            return Viewport(x=0, y=0, width=plan.resolution.width, height=plan.resolution.height)

    # Compute progress in shot
    duration = max(0.0001, active_shot.duration)
    progress = (t - active_shot.start) / duration
    progress = max(0.0, min(1.0, progress))

    if active_shot.type == "transition":
        return sample_transition_viewport(
            from_viewport=active_shot.start_viewport,
            to_viewport=active_shot.end_viewport,
            full_comic_viewport=full_comic_viewport,
            progress=progress,
            show_full_comic=show_full_comic_transitions,
        )
    else:
        return interpolate_viewports(
            v_start=active_shot.start_viewport,
            v_end=active_shot.end_viewport,
            progress=progress,
            easing="smootherstep",
        )


def extract_frame_for_viewport(
    image: np.ndarray,
    viewport: Viewport,
    out_width: int,
    out_height: int,
) -> np.ndarray:
    """Crops the virtual camera viewport with subpixel precision and scales to output resolution
    using Lanczos-4 interpolation, eliminating border artifacts and jitter.
    """
    img_h, img_w = image.shape[:2]
    vx = float(viewport.x)
    vy = float(viewport.y)
    vw = float(viewport.width)
    vh = float(viewport.height)

    # Clamp viewport to canvas boundaries
    vw = max(1.0, min(float(img_w), vw))
    vh = max(1.0, min(float(img_h), vh))
    vx = max(0.0, min(float(img_w - vw), vx))
    vy = max(0.0, min(float(img_h - vh), vy))

    src_pts = np.array([
        [vx, vy],
        [vx + vw, vy],
        [vx, vy + vh],
    ], dtype=np.float32)

    dst_pts = np.array([
        [0.0, 0.0],
        [float(out_width), 0.0],
        [0.0, float(out_height)],
    ], dtype=np.float32)

    M = cv2.getAffineTransform(src_pts, dst_pts)
    frame = cv2.warpAffine(
        image,
        M,
        (out_width, out_height),
        flags=cv2.INTER_LANCZOS4,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return frame


def render_camera_plan_video(
    plan: CameraPlan,
    output_path: str | Path,
    resolution_scale: float = 1.0,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> InspectionResult:
    """Renders the entire camera plan into an MP4 video using FFmpeg.
    Ensures absolute source image safety by calculating SHA-256 before and after.
    """
    source_img_path = Path(plan.image_path).resolve()
    if not source_img_path.is_file():
        raise FileNotFoundError(f"Source comic image not found: {source_img_path}")
        
    out_file = Path(output_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)
    
    # 1. Source Safety Verification: SHA-256 before
    sha_before = calculate_file_sha256(source_img_path)
    
    # Read image
    source_image = cv2.imread(str(source_img_path))
    if source_image is None:
        raise ValueError(f"Failed to read source image: {source_img_path}")
        
    out_w = int(round(plan.resolution.width * resolution_scale))
    out_h = int(round(plan.resolution.height * resolution_scale))
    # Ensure dimensions are even numbers for H.264
    out_w = out_w if out_w % 2 == 0 else out_w + 1
    out_h = out_h if out_h % 2 == 0 else out_h + 1
    
    fps = plan.fps
    total_frames = int(round(plan.total_duration * fps))
    
    # Full comic viewport for transitions
    full_comic_viewport = None
    for shot in plan.shots:
        if shot.type == "full_comic":
            full_comic_viewport = shot.start_viewport
            break
            
    ffmpeg_bin = get_ffmpeg_executable()
    
    ffmpeg_cmd = [
        ffmpeg_bin,
        "-y",
        "-f", "rawvideo",
        "-pix_fmt", "bgr24",
        "-s", f"{out_w}x{out_h}",
        "-r", str(fps),
        "-i", "pipe:0",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "fast",
        "-crf", "18",
        str(out_file),
    ]
    
    proc = subprocess.Popen(
        ffmpeg_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    
    show_full_comic = getattr(plan, "show_full_comic_between_panels", False)

    try:
        for frame_idx in range(total_frames):
            t = frame_idx / float(fps)
            vp = get_viewport_at_time(
                plan=plan,
                time_seconds=t,
                full_comic_viewport=full_comic_viewport,
                show_full_comic_transitions=show_full_comic,
            )
            frame = extract_frame_for_viewport(source_image, vp, out_w, out_h)
            proc.stdin.write(frame.tobytes())
            
            if progress_callback and frame_idx % 30 == 0:
                progress_callback(frame_idx, total_frames)
                
        proc.stdin.close()
        stdout, stderr = proc.communicate()
        
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg failed with exit code {proc.returncode}: {stderr.decode('utf-8', errors='replace')}")
            
    except Exception as e:
        proc.kill()
        raise RuntimeError(f"Rendering failed: {e}")
        
    # 2. Source Safety Verification: SHA-256 after
    sha_after = calculate_file_sha256(source_img_path)
    if sha_before != sha_after:
        raise RuntimeError("SOURCE SAFETY VIOLATION: Source comic image was modified during rendering!")
        
    # Inspect output
    return inspect_video_file(out_file)


def generate_camera_plan_preview_image(
    plan: CameraPlan,
    output_path: str | Path,
) -> Path:
    """Generates a visual diagram showing camera trajectory over the comic sheet."""
    source_img_path = Path(plan.image_path).resolve()
    image = cv2.imread(str(source_img_path))
    if image is None:
        raise ValueError(f"Failed to read image: {source_img_path}")
        
    img_h, img_w = image.shape[:2]
    canvas = image.copy()
    
    # Overlay semi-transparent mask
    overlay = canvas.copy()
    
    # Colors
    box_color = (255, 120, 0)       # Blue-ish orange
    path_color = (0, 255, 255)      # Yellow
    text_color = (255, 255, 255)
    
    panel_centers = []
    
    # Draw shots
    for shot in plan.shots:
        if shot.type == "panel":
            vp = shot.start_viewport
            x1, y1 = int(vp.x), int(vp.y)
            x2, y2 = int(vp.x + vp.width), int(vp.y + vp.height)
            cv2.rectangle(overlay, (x1, y1), (x2, y2), box_color, 4)
            
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            panel_centers.append((cx, cy, shot.panel_id, shot.movement))
            
    # Draw trajectory line
    for i in range(len(panel_centers) - 1):
        p1 = (panel_centers[i][0], panel_centers[i][1])
        p2 = (panel_centers[i + 1][0], panel_centers[i + 1][1])
        cv2.arrowedLine(overlay, p1, p2, path_color, 4, tipLength=0.06)

    # Blend overlay
    cv2.addWeighted(overlay, 0.85, canvas, 0.15, 0, canvas)
    
    # Draw labels
    for cx, cy, pid, mvt in panel_centers:
        label = f"Panel {pid} ({mvt})"
        cv2.putText(canvas, label, (cx - 100, cy), cv2.FONT_HERSHEY_DUPLEX, 0.9, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(canvas, label, (cx - 100, cy), cv2.FONT_HERSHEY_DUPLEX, 0.9, text_color, 2, cv2.LINE_AA)

    out_p = Path(output_path).resolve()
    out_p.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_p), canvas)
    return out_p
