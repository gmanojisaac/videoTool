"""Video rendering engine using FFmpeg pipe streaming."""

from __future__ import annotations

import cv2
import json
from zipfile import ZipFile, ZIP_DEFLATED
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
        if shot.start <= t < shot.end:
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

    if active_shot.type == "panel":
        moving_duration = active_shot.duration - active_shot.hold_duration_seconds
        progress = 0.0 if moving_duration <= 0 else max(0.0, min(1.0,
            (t-active_shot.start-active_shot.hold_duration_seconds)/moving_duration))

    if active_shot.type == "transition":
        return sample_transition_viewport(
            from_viewport=active_shot.start_viewport,
            to_viewport=active_shot.end_viewport,
            full_comic_viewport=full_comic_viewport,
            progress=progress,
            show_full_comic=show_full_comic_transitions and not plan.backtrack_to_start,
        )
    else:
        return interpolate_viewports(
            v_start=active_shot.start_viewport,
            v_end=active_shot.end_viewport,
            progress=progress,
            easing="smootherstep",
        )


def isolate_panel_content(image: np.ndarray, bounds: Viewport) -> np.ndarray:
    """Mask before resampling so adjacent panels cannot bleed through Lanczos edges."""
    height, width = image.shape[:2]
    left, right = max(0, int(np.floor(bounds.x))), min(width, int(np.ceil(bounds.x+bounds.width)))
    top, bottom = max(0, int(np.floor(bounds.y))), min(height, int(np.ceil(bounds.y+bounds.height)))
    isolated = np.full_like(image, 24)
    isolated[top:bottom, left:right] = image[top:bottom, left:right]
    return isolated


def extract_frame_for_viewport(
    image: np.ndarray,
    viewport: Viewport,
    out_width: int,
    out_height: int,
    content_bounds: Optional[Viewport] = None,
    contain: bool = False,
    source_isolated: bool = False,
) -> np.ndarray:
    """Crops the virtual camera viewport with subpixel precision and scales to output resolution
    using Lanczos-4 interpolation, eliminating border artifacts and jitter.
    """
    img_h, img_w = image.shape[:2]
    vx = float(viewport.x)
    vy = float(viewport.y)
    vw = float(viewport.width)
    vh = float(viewport.height)

    # Whole-tile framing permits padded viewports beyond canvas edges.
    if not contain:
        vw = max(1.0, min(float(img_w), vw))
        vh = max(1.0, min(float(img_h), vh))
        vx = max(0.0, min(float(img_w - vw), vx))
        vy = max(0.0, min(float(img_h - vh), vy))

    if contain and content_bounds is not None and not source_isolated:
        image = isolate_panel_content(image, content_bounds)
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
        borderMode=(cv2.BORDER_CONSTANT if contain and
            (vx < 0 or vy < 0 or vx + vw > img_w or vy + vh > img_h)
            else cv2.BORDER_REPLICATE),
        borderValue=(24, 24, 24),
    )
    if contain and content_bounds is not None:
        # Hide adjacent tiles in the padding without cropping the focused tile.
        left = max(0, min(out_width, int(np.floor((content_bounds.x-vx)*out_width/vw))))
        right = max(0, min(out_width, int(np.ceil((content_bounds.x+content_bounds.width-vx)*out_width/vw))))
        top = max(0, min(out_height, int(np.floor((content_bounds.y-vy)*out_height/vh))))
        bottom = max(0, min(out_height, int(np.ceil((content_bounds.y+content_bounds.height-vy)*out_height/vh))))
        frame[:, :left] = 24
        frame[:, right:] = 24
        frame[:top, :] = 24
        frame[bottom:, :] = 24
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
        "-loglevel", "error",
        "-nostats",
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

    cached_bounds = None
    cached_image = source_image
    try:
        for frame_idx in range(total_frames):
            t = frame_idx / float(fps)
            vp = get_viewport_at_time(
                plan=plan,
                time_seconds=t,
                full_comic_viewport=full_comic_viewport,
                show_full_comic_transitions=show_full_comic,
            )
            content_bounds = None
            if plan.framing == "contain":
                for shot in plan.shots:
                    if shot.start <= t < shot.end:
                        if shot.start_content_bounds is not None and shot.end_content_bounds is not None:
                            content_bounds = interpolate_viewports(shot.start_content_bounds,
                                shot.end_content_bounds, (t-shot.start)/max(shot.duration, 0.0001))
                        break
            if content_bounds is not None and content_bounds != cached_bounds:
                cached_image = isolate_panel_content(source_image, content_bounds)
                cached_bounds = content_bounds
            frame_source = cached_image if content_bounds is not None else source_image
            frame = extract_frame_for_viewport(frame_source, vp, out_w, out_h,
                content_bounds=content_bounds, contain=plan.framing == "contain",
                source_isolated=content_bounds is not None)
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


def export_panel_start_frames(plan: CameraPlan, output_dir: str | Path,
    width: Optional[int] = None, height: Optional[int] = None) -> Dict[str, Any]:
    """Export exact complete-panel arrival images and edit markers for animation inserts."""
    source = cv2.imread(str(plan.image_path))
    if source is None:
        raise ValueError(f"Failed to read image: {plan.image_path}")
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    out_width = width or plan.resolution.width
    out_height = height or plan.resolution.height
    out_width += out_width % 2
    out_height += out_height % 2
    frames = []
    seen = set()
    for shot in plan.shots:
        if shot.type != "panel" or shot.panel_id in seen:
            continue
        seen.add(shot.panel_id)
        # Use the same viewport, masking, and resampling as the focused video shot.
        frame = extract_frame_for_viewport(source, shot.start_viewport, out_width, out_height,
            content_bounds=shot.start_content_bounds, contain=plan.framing == "contain")
        path = directory / f"panel_{shot.panel_id}_start.png"
        if not cv2.imwrite(str(path), frame):
            raise RuntimeError(f"Could not save {path}")
        bounds = plan.panel_bounds.get(str(shot.panel_id)) or shot.start_content_bounds
        if bounds is None:
            raise ValueError("Original tile crops require contain framing with panel boundaries")
        left, top = max(0,int(round(bounds.x))), max(0,int(round(bounds.y)))
        right = min(source.shape[1],int(round(bounds.x+bounds.width)))
        bottom = min(source.shape[0],int(round(bounds.y+bounds.height)))
        raw_path = directory / f"panel_{shot.panel_id}_original.png"
        if not cv2.imwrite(str(raw_path),source[top:bottom,left:right]):
            raise RuntimeError(f"Could not save {raw_path}")
        frames.append({"panel_id":shot.panel_id,"image_path":str(path.resolve()),
            "original_image_path":str(raw_path.resolve()),
            "original_width":right-left,"original_height":bottom-top,
            "width":out_width,"height":out_height,"focus_start_seconds":shot.start,
            "hold_end_seconds":round(shot.start+shot.hold_duration_seconds,3),
            "panel_end_seconds":shot.end})
    manifest = directory / "edit_markers.json"
    manifest.write_text(json.dumps({"mode":plan.format,"fps":plan.fps,"frames":frames},indent=2),encoding="utf-8")
    archive = directory / "panel_start_frames.zip"
    with ZipFile(archive,"w",ZIP_DEFLATED) as bundle:
        for item in frames:
            path = Path(item["image_path"])
            bundle.write(path,path.name)
            original = Path(item["original_image_path"])
            bundle.write(original,original.name)
        bundle.write(manifest,manifest.name)
    return {"frames":frames,"manifest_path":str(manifest.resolve()),"archive_path":str(archive.resolve())}
