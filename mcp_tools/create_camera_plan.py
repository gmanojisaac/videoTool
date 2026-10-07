"""MCP Tool: create_camera_plan"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Dict, Any, Optional, List, Union

from config import (
    OUTPUT_DIR,
    PRESETS,
    DEFAULT_PANEL_DURATION,
    DEFAULT_TRANSITION_DURATION,
    DEFAULT_INTRO_DURATION,
    DEFAULT_OUTRO_DURATION,
    DEFAULT_WIDTH,
    DEFAULT_HEIGHT,
    DEFAULT_FPS,
    DEFAULT_PRESET,
)
from models.schemas import CameraPlan, Shot, Viewport, Resolution, Panel, ComicAnalysis
from vision.composition import compute_full_comic_viewport, detect_comic_format_and_layout
from video.camera import compute_panel_viewports


def create_camera_plan(
    analysis: Union[str, Dict[str, Any]],
    panel_duration_seconds: float = DEFAULT_PANEL_DURATION,
    transition_duration_seconds: float = DEFAULT_TRANSITION_DURATION,
    preset: str = DEFAULT_PRESET,
    include_intro: bool = True,
    include_outro: bool = True,
    show_full_comic_between_panels: bool = False,
    backtrack_to_start: bool = True,
    sequence: Optional[List[int]] = None,
    intro_duration_seconds: float = DEFAULT_INTRO_DURATION,
    outro_duration_seconds: float = DEFAULT_OUTRO_DURATION,
    width: Optional[int] = None,
    height: Optional[int] = None,
    fps: int = DEFAULT_FPS,
    output_dir: Optional[str] = None,
    format: Optional[str] = None,
    layout: Optional[str] = None,
    framing: str = "contain",
    panel_hold_seconds: float = 1.0,
    push_in_zoom: Optional[float] = None,
    protected_content_bounds: Optional[Dict[str, Dict[str, float]]] = None,
) -> Dict[str, Any]:
    """Generates a complete, human-readable camera plan storyboard for continuous canvas video rendering.
    
    Args:
        analysis: Path to analysis.json file or analysis dictionary.
        panel_duration_seconds: Time spent displaying each panel (default 5s).
        transition_duration_seconds: Time spent traveling between panels (default 2s).
        preset: Movement preset: 'educational', 'gentle', 'emotional', 'object_focus', 'wide'.
        include_intro: Whether to show the full comic overview at the beginning.
        include_outro: Whether to zoom out to the full comic at the end.
        show_full_comic_between_panels: False for continuous canvas travel; True for tile overview.
        backtrack_to_start: Reverse each panel approach before visiting the next panel.
        sequence: Custom reading order sequence of panel IDs (default [1, 2, 3, 4, 5, 6]).
        intro_duration_seconds: Duration of full comic intro (default 2s).
        outro_duration_seconds: Duration of full comic outro (default 2s).
        width: Output video width (auto-detected: 1920 for desktop, 1080 for mobile).
        height: Output video height (auto-detected: 1080 for desktop, 1920 for mobile).
        fps: Frames per second (default 30).
        output_dir: Output directory where camera_plan.json will be saved.
        format: Output mode ('desktop' or 'mobile'); source layout is detected independently.
        layout: Optional layout override ('3x2' or '2x3').
        framing: 'contain' preserves panel aspect and edges; 'crop' is the legacy mode.
        panel_hold_seconds: Initial complete-panel hold within panel_duration_seconds.
        push_in_zoom: Maximum zoom factor (1–1.2); reduced to protect content.
        protected_content_bounds: Panel-ID mapping of source-pixel x/y/width/height rectangles.
            Unspecified panels protect their entire area and remain still.
        
    Returns:
        Camera plan dictionary.
    """
    if framing not in ("contain", "crop"):
        raise ValueError("framing must be contain or crop")
    if not math.isfinite(panel_hold_seconds) or panel_hold_seconds < 0:
        raise ValueError("Panel hold must be finite and nonnegative")
    if push_in_zoom is not None and (not math.isfinite(push_in_zoom) or push_in_zoom < 1 or push_in_zoom > 1.2):
        raise ValueError("Push-in zoom must be between 1 and 1.2")
    if framing != "contain" and protected_content_bounds:
        raise ValueError("Protected content bounds require contain framing")
    # Load analysis data
    if isinstance(analysis, (str, Path)):
        p = Path(analysis).resolve()
        if not p.is_file():
            raise FileNotFoundError(f"Analysis file not found: {p}")
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    elif isinstance(analysis, dict):
        data = analysis
    else:
        raise ValueError("Invalid analysis parameter; must be file path or dictionary.")

    image_path = data.get("image_path")
    if not image_path:
        raise ValueError("Analysis data missing 'image_path'.")
        
    img_w = int(data.get("image_width", 1920))
    img_h = int(data.get("image_height", 1080))
    
    # Detect or extract format and layout
    detected_format, detected_layout, def_w, def_h = detect_comic_format_and_layout(
        image_width=img_w,
        image_height=img_h,
        format_override=format or data.get("format"),
        layout_override=layout or data.get("layout"),
    )

    target_width = width if width is not None else def_w
    target_height = height if height is not None else def_h

    # Map panels by ID
    raw_panels = data.get("panels", [])
    panel_map: Dict[int, Panel] = {}
    for item in raw_panels:
        p_obj = Panel(**item) if isinstance(item, dict) else item
        panel_map[p_obj.id] = p_obj
        
    # Sequence of panels
    seq = sequence if sequence and len(sequence) > 0 else [1, 2, 3, 4, 5, 6]
    
    # Filter sequence to available panels
    valid_seq = [pid for pid in seq if pid in panel_map]
    if not valid_seq:
        # Fallback to sorted panel keys
        valid_seq = sorted(panel_map.keys())
        
    preset_config = PRESETS.get(preset, PRESETS["educational"])
    mvt_style = preset_config["default_movement"]
    zoom_factor = push_in_zoom if push_in_zoom is not None else preset_config["zoom_factor"]
    protected_map = {int(key): value for key, value in (protected_content_bounds or {}).items()}
    if set(protected_map) - set(panel_map):
        raise ValueError("Protected bounds reference an unknown panel")
    safe_margin = preset_config["safe_margin"]
    
    target_aspect = float(target_width) / float(target_height)
    full_comic_vp = compute_full_comic_viewport(img_w, img_h, target_aspect=target_aspect)
    
    canvas_bounds = Viewport(x=0, y=0, width=img_w, height=img_h)
    if framing == "contain":
        overview_width = max(float(img_w), float(img_h) * target_aspect)
        full_comic_vp = Viewport(x=(img_w-overview_width)/2,
            y=(img_h-overview_width/target_aspect)/2,
            width=overview_width, height=overview_width/target_aspect)
    prev_content_bounds = canvas_bounds
    shots: List[Shot] = []
    current_time = 0.0
    shot_id = 1
    
    # 1. Full Comic Intro
    if include_intro and intro_duration_seconds > 0:
        shots.append(
            Shot(
                id=shot_id,
                type="full_comic",
                start=round(current_time, 3),
                end=round(current_time + intro_duration_seconds, 3),
                duration=round(intro_duration_seconds, 3),
                movement="hold",
                start_viewport=full_comic_vp,
                end_viewport=full_comic_vp,
            )
        )
        current_time += intro_duration_seconds
        shot_id += 1
        prev_viewport = full_comic_vp
    else:
        prev_viewport = full_comic_vp

    # 2. Panel Shots & Transitions
    for idx, pid in enumerate(valid_seq):
        panel = panel_map[pid]
        p_start_vp, p_end_vp = compute_panel_viewports(
            panel=panel,
            image_width=img_w,
            image_height=img_h,
            movement=mvt_style,
            zoom_factor=zoom_factor,
            safe_margin=safe_margin,
            target_aspect=target_aspect,
            framing=framing,
            protected_content_bounds=protected_map.get(pid),
        )
        
        hold_duration = min(panel_hold_seconds, panel_duration_seconds) if framing == "contain" else 0.0
        if hold_duration >= panel_duration_seconds:
            p_end_vp = p_start_vp
        panel_bounds = Viewport(x=panel.x, y=panel.y, width=panel.width, height=panel.height)
        approach_content_start = prev_content_bounds
        approach_start = prev_viewport

        # Transition into panel
        if transition_duration_seconds > 0:
            shots.append(
                Shot(
                    id=shot_id,
                    type="transition",
                    from_panel=valid_seq[idx - 1] if idx > 0 else None,
                    to_panel=pid,
                    start=round(current_time, 3),
                    end=round(current_time + transition_duration_seconds, 3),
                    duration=round(transition_duration_seconds, 3),
                    movement="transition",
                    start_viewport=prev_viewport,
                    end_viewport=p_start_vp,

                )
            )
            current_time += transition_duration_seconds
            shot_id += 1
            
        # Panel Shot
        shots.append(
            Shot(
                id=shot_id,
                type="panel",
                panel_id=pid,
                start=round(current_time, 3),
                end=round(current_time + panel_duration_seconds, 3),
                duration=round(panel_duration_seconds, 3),
                movement="hold" if p_start_vp == p_end_vp else mvt_style,
                hold_duration_seconds=hold_duration,
                start_viewport=p_start_vp,
                end_viewport=p_end_vp,
                start_content_bounds=panel_bounds if framing == "contain" else None,
                end_content_bounds=panel_bounds if framing == "contain" else None,
                focus_x=float(panel.focus_x),
                focus_y=float(panel.focus_y),
            )
        )
        current_time += panel_duration_seconds
        shot_id += 1
        prev_viewport = p_end_vp
        prev_content_bounds = panel_bounds

        # Reverse both the panel push-in and its approach to the starting overview.
        if backtrack_to_start and (idx < len(valid_seq) - 1 or include_outro):
            reverse_segments = []
            if p_start_vp != p_end_vp and panel_duration_seconds > 0:
                reverse_segments.append((p_end_vp, p_start_vp, panel_duration_seconds-hold_duration, panel_bounds, panel_bounds))
            if transition_duration_seconds > 0:
                reverse_segments.append((p_start_vp, approach_start, transition_duration_seconds, None, None))
            for reverse_start, reverse_end, reverse_duration, content_start, content_end in reverse_segments:
                shots.append(Shot(
                    id=shot_id, type="transition", from_panel=pid,
                    start=round(current_time, 3),
                    end=round(current_time + reverse_duration, 3),
                    duration=round(reverse_duration, 3), movement="backtrack",
                    start_viewport=reverse_start, end_viewport=reverse_end,
                    start_content_bounds=content_start if framing == "contain" else None,
                    end_content_bounds=content_end if framing == "contain" else None,
                ))
                current_time += reverse_duration
                shot_id += 1
                prev_viewport = reverse_end
                prev_content_bounds = content_end


    # 3. Full Comic Outro
    if include_outro and outro_duration_seconds > 0:
        # Transition out to full comic
        if transition_duration_seconds > 0 and prev_viewport != full_comic_vp:
            shots.append(
                Shot(
                    id=shot_id,
                    type="transition",
                    from_panel=valid_seq[-1] if valid_seq else None,
                    to_panel=None,
                    start=round(current_time, 3),
                    end=round(current_time + transition_duration_seconds, 3),
                    duration=round(transition_duration_seconds, 3),
                    movement="transition",
                    start_viewport=prev_viewport,
                    end_viewport=full_comic_vp,

                )
            )
            current_time += transition_duration_seconds
            shot_id += 1
            
        # Hold on full comic
        shots.append(
            Shot(
                id=shot_id,
                type="full_comic",
                start=round(current_time, 3),
                end=round(current_time + outro_duration_seconds, 3),
                duration=round(outro_duration_seconds, 3),
                movement="hold",
                start_viewport=full_comic_vp,
                end_viewport=full_comic_vp,
            )
        )
        current_time += outro_duration_seconds
        shot_id += 1

    total_frames = int(round(current_time * fps))
    plan = CameraPlan(
        image_path=image_path,
        resolution=Resolution(width=target_width, height=target_height),
        fps=fps,
        sequence=valid_seq,
        preset=preset,
        format=detected_format,
        layout=detected_layout,
        show_full_comic_between_panels=show_full_comic_between_panels,
        backtrack_to_start=backtrack_to_start,
        framing=framing,
        panel_bounds={str(pid): Viewport(x=panel_map[pid].x,y=panel_map[pid].y,
            width=panel_map[pid].width,height=panel_map[pid].height) for pid in valid_seq},
        panel_hold_seconds=panel_hold_seconds,
        push_in_zoom=zoom_factor,
        protected_content_bounds={str(pid): protected_map.get(pid) or panel_map[pid].protected_content_bounds or
            {"x":float(panel_map[pid].x), "y":float(panel_map[pid].y),
             "width":float(panel_map[pid].width), "height":float(panel_map[pid].height)} for pid in valid_seq},
        total_duration=round(current_time, 3),
        total_frames=total_frames,
        shots=shots,
    )

    out_dir = Path(output_dir).resolve() if output_dir else OUTPUT_DIR.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    plan_file = out_dir / "camera_plan.json"
    
    plan_dict = plan.model_dump()
    with open(plan_file, "w", encoding="utf-8") as f:
        json.dump(plan_dict, f, indent=2)
        
    plan_dict["plan_file"] = str(plan_file)
    return plan_dict
