"""Virtual 2D camera system, viewport interpolation, and easing calculations."""

from __future__ import annotations

import math
from typing import Tuple, Dict, Any, Optional
from models.schemas import Viewport, Panel, Resolution
from vision.composition import fit_aspect_ratio


def ease_in_out(t: float) -> float:
    """Smooth cosine ease-in-out easing function."""
    t_clamped = max(0.0, min(1.0, t))
    return 0.5 * (1.0 - math.cos(math.pi * t_clamped))


def smoothstep(t: float) -> float:
    """Cubic smoothstep easing."""
    t_clamped = max(0.0, min(1.0, t))
    return t_clamped * t_clamped * (3.0 - 2.0 * t_clamped)


def smootherstep(t: float) -> float:
    """Quintic smootherstep easing with zero 1st and 2nd derivatives at endpoints for silky smooth camera flight."""
    t_clamped = max(0.0, min(1.0, t))
    return t_clamped * t_clamped * t_clamped * (t_clamped * (t_clamped * 6.0 - 15.0) + 10.0)


def interpolate_viewports(
    v_start: Viewport,
    v_end: Viewport,
    progress: float,
    easing: str = "smootherstep",
) -> Viewport:
    """Interpolates between two camera viewports using specified easing."""
    if easing == "smootherstep":
        t = smootherstep(progress)
    elif easing == "ease_in_out":
        t = ease_in_out(progress)
    elif easing == "smoothstep":
        t = smoothstep(progress)
    else:
        t = max(0.0, min(1.0, progress))
        
    x = v_start.x + (v_end.x - v_start.x) * t
    y = v_start.y + (v_end.y - v_start.y) * t
    w = v_start.width + (v_end.width - v_start.width) * t
    h = v_start.height + (v_end.height - v_start.height) * t
    
    return Viewport(x=x, y=y, width=w, height=h)


def zoom_viewport_towards(
    base: Viewport,
    focus_x: float,
    focus_y: float,
    zoom_factor: float,
    max_w: float,
    max_h: float,
) -> Viewport:
    """Scales a viewport by zoom_factor towards (focus_x, focus_y).
    
    zoom_factor > 1.0 means zoom IN (viewport becomes smaller).
    """
    if zoom_factor <= 0:
        return base
        
    new_w = base.width / zoom_factor
    new_h = base.height / zoom_factor
    
    # Calculate relative position of focus point inside base viewport
    rel_x = (focus_x - base.x) / max(base.width, 1.0)
    rel_y = (focus_y - base.y) / max(base.height, 1.0)
    
    # Clamp relative position to prevent extreme drift
    rel_x = max(0.15, min(0.85, rel_x))
    rel_y = max(0.15, min(0.85, rel_y))
    
    new_x = focus_x - rel_x * new_w
    new_y = focus_y - rel_y * new_h
    
    # Clamp within image bounds
    new_x = max(0.0, min(new_x, max_w - new_w))
    new_y = max(0.0, min(new_y, max_h - new_h))
    
    return Viewport(x=new_x, y=new_y, width=new_w, height=new_h)


def compute_panel_viewports(
    panel: Panel,
    image_width: int,
    image_height: int,
    movement: str = "slow_push",
    zoom_factor: float = 1.05,
    safe_margin: float = 0.08,
    target_aspect: float = 16.0 / 9.0,
    framing: str = "crop",
    protected_content_bounds: Optional[Dict[str, float]] = None,
) -> Tuple[Viewport, Viewport]:
    """Computes borderless (start_viewport, end_viewport) for a story area on the continuous canvas.
    
    Frames the illustration strictly inside the story area so that panel border lines,
    frames, and gutters are never visibly shown on video.
    """
    if framing == "contain":
        # Fit the complete tile; unequal aspect ratios require padding.
        width = max(float(panel.width), float(panel.height) * target_aspect)
        height = width / target_aspect
        viewport = Viewport(x=panel.x + (panel.width - width) / 2,
            y=panel.y + (panel.height - height) / 2, width=width, height=height)
        protected = protected_content_bounds if protected_content_bounds is not None else panel.protected_content_bounds
        if protected is None:
            # No content detection guesses: every panel pixel is protected.
            return viewport, viewport
        if set(protected) != {"x", "y", "width", "height"}:
            raise ValueError("Protected bounds require x, y, width, height")
        bounds = {key: float(value) for key, value in protected.items()}
        if not all(math.isfinite(value) for value in bounds.values()):
            raise ValueError("Protected bounds must be finite")
        px, py, pw, ph = (bounds[key] for key in ("x", "y", "width", "height"))
        if pw <= 0 or ph <= 0 or px < panel.x or py < panel.y or px+pw > panel.x+panel.width or py+ph > panel.y+panel.height:
            raise ValueError("Protected bounds must lie inside the panel with positive dimensions")
        if not math.isfinite(zoom_factor) or zoom_factor < 1:
            raise ValueError("Zoom factor must be finite and at least 1")
        end_width = max(width / zoom_factor, pw, ph * target_aspect)
        if movement == "hold" or end_width >= width - 1e-9:
            return viewport, viewport
        end_height = end_width / target_aspect
        # Keep the target inside the complete view and enclose all protected content.
        min_x = max(viewport.x, px+pw-end_width)
        max_x = min(viewport.x+width-end_width, px)
        min_y = max(viewport.y, py+ph-end_height)
        max_y = min(viewport.y+height-end_height, py)
        end = Viewport(x=max(min_x, min(max_x, panel.focus_x-end_width/2)),
            y=max(min_y, min(max_y, panel.focus_y-end_height/2)),
            width=end_width, height=end_height)
        return viewport, end
    if framing != "crop":
        raise ValueError("framing must be contain or crop")
    img_w = float(image_width)
    img_h = float(image_height)

    # Safe inner boundaries inside the panel (insetting away from outer borders & gutters)
    inset_x = float(panel.width) * safe_margin
    inset_y = float(panel.height) * safe_margin

    inner_w = max(10.0, float(panel.width) - 2.0 * inset_x)
    inner_h = max(10.0, float(panel.height) - 2.0 * inset_y)

    inner_x1 = float(panel.x) + inset_x
    inner_y1 = float(panel.y) + inset_y
    inner_x2 = float(panel.x + panel.width) - inset_x
    inner_y2 = float(panel.y + panel.height) - inset_y

    # Determine viewport dimensions matching target_aspect and fitting inside the inner safe area
    inner_aspect = inner_w / max(inner_h, 1.0)

    if inner_aspect > target_aspect:
        # Inner safe area is wider than target aspect ratio (common in mobile 9:16)
        base_h = inner_h
        base_w = base_h * target_aspect
    else:
        # Inner safe area is taller than target aspect ratio (common in desktop 16:9)
        base_w = inner_w
        base_h = base_w / target_aspect

    # Ensure viewport does not exceed canvas dimensions
    if base_w > img_w:
        base_w = img_w
        base_h = base_w / target_aspect
    if base_h > img_h:
        base_h = img_h
        base_w = base_h * target_aspect

    # Focal center point
    fx = float(panel.focus_x)
    fy = float(panel.focus_y)

    half_w = base_w / 2.0
    half_h = base_h / 2.0

    # Clamp center within inner safe area so camera viewport borders remain strictly inside
    min_cx = inner_x1 + half_w
    max_cx = inner_x2 - half_w
    if max_cx >= min_cx:
        cx = max(min_cx, min(max_cx, fx))
    else:
        cx = (inner_x1 + inner_x2) / 2.0

    min_cy = inner_y1 + half_h
    max_cy = inner_y2 - half_h
    if max_cy >= min_cy:
        cy = max(min_cy, min(max_cy, fy))
    else:
        cy = (inner_y1 + inner_y2) / 2.0

    base_x = max(0.0, min(img_w - base_w, cx - half_w))
    base_y = max(0.0, min(img_h - base_h, cy - half_h))
    base_viewport = Viewport(x=base_x, y=base_y, width=base_w, height=base_h)

    # Zoomed viewport for push-in / pull movements
    # Since base_viewport is already within safe region, zooming in keeps it even deeper inside
    zoomed_viewport = zoom_viewport_towards(
        base=base_viewport,
        focus_x=cx,
        focus_y=cy,
        zoom_factor=zoom_factor,
        max_w=img_w,
        max_h=img_h,
    )

    if movement == "hold":
        return base_viewport, base_viewport

    elif movement == "slow_push":
        return base_viewport, zoomed_viewport

    elif movement == "slow_pull":
        return zoomed_viewport, base_viewport

    elif movement == "pan_left":
        drift_x = base_w * 0.03
        s_x = min(img_w - base_w, base_viewport.x + drift_x)
        e_x = max(0.0, base_viewport.x - drift_x)
        return (
            Viewport(x=s_x, y=base_viewport.y, width=base_w, height=base_h),
            Viewport(x=e_x, y=base_viewport.y, width=base_w, height=base_h),
        )

    elif movement == "pan_right":
        drift_x = base_w * 0.03
        s_x = max(0.0, base_viewport.x - drift_x)
        e_x = min(img_w - base_w, base_viewport.x + drift_x)
        return (
            Viewport(x=s_x, y=base_viewport.y, width=base_w, height=base_h),
            Viewport(x=e_x, y=base_viewport.y, width=base_w, height=base_h),
        )

    elif movement == "pan_up":
        drift_y = base_h * 0.03
        s_y = min(img_h - base_h, base_viewport.y + drift_y)
        e_y = max(0.0, base_viewport.y - drift_y)
        return (
            Viewport(x=base_viewport.x, y=s_y, width=base_w, height=base_h),
            Viewport(x=base_viewport.x, y=e_y, width=base_w, height=base_h),
        )

    elif movement == "pan_down":
        drift_y = base_h * 0.03
        s_y = max(0.0, base_viewport.y - drift_y)
        e_y = min(img_h - base_h, base_viewport.y + drift_y)
        return (
            Viewport(x=base_viewport.x, y=s_y, width=base_w, height=base_h),
            Viewport(x=base_viewport.x, y=e_y, width=base_w, height=base_h),
        )

    elif movement == "push_and_pan":
        drift_x = base_w * 0.02
        s_x = max(0.0, base_viewport.x - drift_x)
        start_v = Viewport(x=s_x, y=base_viewport.y, width=base_w, height=base_h)
        return start_v, zoomed_viewport

    else:
        return base_viewport, base_viewport
