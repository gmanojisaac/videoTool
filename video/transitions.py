"""Camera transitions and trajectory generation."""

from __future__ import annotations

from typing import List, Dict, Any, Optional
from models.schemas import Viewport, Shot
from video.camera import interpolate_viewports, ease_in_out


def sample_transition_viewport(
    from_viewport: Viewport,
    to_viewport: Viewport,
    full_comic_viewport: Optional[Viewport],
    progress: float,
    show_full_comic: bool = False,
) -> Viewport:
    """Calculates interpolated camera viewport during a transition.
    
    If show_full_comic is False (default continuous canvas):
    - Direct smooth glide across the canvas from previous story area to next story area.
    
    If show_full_comic is True:
    - 0.0 to 0.5: zooms out from previous tile towards the full comic overview
    - 0.5 to 1.0: moves and zooms in from full comic overview towards the next tile
    """
    p = max(0.0, min(1.0, progress))
    
    if not show_full_comic or full_comic_viewport is None:
        return interpolate_viewports(from_viewport, to_viewport, p, easing="smootherstep")
        
    if p < 0.5:
        sub_p = p / 0.5
        return interpolate_viewports(from_viewport, full_comic_viewport, sub_p, easing="smootherstep")
    else:
        sub_p = (p - 0.5) / 0.5
        return interpolate_viewports(full_comic_viewport, to_viewport, sub_p, easing="smootherstep")
