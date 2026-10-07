"""Data models and schemas for Comic Video MCP."""

from __future__ import annotations

from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field


class Panel(BaseModel):
    """Represents a single comic panel boundary and focus point."""
    id: int = Field(..., description="1-indexed panel identifier according to reading order")
    x: int = Field(..., description="Left coordinate of panel on original image")
    y: int = Field(..., description="Top coordinate of panel on original image")
    width: int = Field(..., description="Width of panel in pixels")
    height: int = Field(..., description="Height of panel in pixels")
    focus_x: int = Field(..., description="X coordinate of focal center (face, object, or center)")
    focus_y: int = Field(..., description="Y coordinate of focal center")
    focus_type: str = Field("center", description="Type of focus: 'face', 'object', or 'center'")
    protected_content_bounds: Optional[Dict[str, float]] = Field(None, description="Protected rectangle in absolute source coordinates: x, y, width, height; defaults to whole panel")
    confidence: float = Field(1.0, description="Detection confidence score between 0.0 and 1.0")


class ComicAnalysis(BaseModel):
    """Output from comic analysis tool."""
    image_path: str = Field(..., description="Source comic image path")
    image_width: int = Field(..., description="Width of source image")
    image_height: int = Field(..., description="Height of source image")
    panel_count: int = Field(6, description="Number of detected panels")
    layout: str = Field("3x2", description="Detected grid layout description ('3x2' or '2x3')")
    format: str = Field("desktop", description="Detected or specified format: 'desktop' or 'mobile'")
    panels: List[Panel] = Field(default_factory=list, description="List of detected panels")
    confidence: float = Field(..., description="Overall confidence score (0.0 - 1.0)")
    warning: Optional[str] = Field(None, description="Warning if automatic detection confidence is low")
    diagnostic_preview_path: Optional[str] = Field(None, description="Path to diagnostic preview image")


class Viewport(BaseModel):
    """2D virtual camera viewport on the source image coordinate space."""
    x: float = Field(..., description="Top-left X coordinate of camera viewport")
    y: float = Field(..., description="Top-left Y coordinate of camera viewport")
    width: float = Field(..., description="Viewport width in source pixels")
    height: float = Field(..., description="Viewport height in source pixels")


class Shot(BaseModel):
    """A single camera movement shot or transition segment."""
    id: int = Field(..., description="Sequential shot index")
    type: Literal["full_comic", "panel", "transition"] = Field(..., description="Type of shot")
    panel_id: Optional[int] = Field(None, description="Panel ID if type is 'panel'")
    from_panel: Optional[int] = Field(None, description="Source panel ID if type is 'transition'")
    to_panel: Optional[int] = Field(None, description="Target panel ID if type is 'transition'")
    start: float = Field(..., description="Shot start time in seconds")
    end: float = Field(..., description="Shot end time in seconds")
    duration: float = Field(..., description="Duration in seconds")
    hold_duration_seconds: float = Field(0.0, ge=0, description="Complete-panel hold before movement")
    movement: str = Field("hold", description="Movement style: hold, slow_push, slow_pull, pan_left, etc.")
    start_viewport: Viewport = Field(..., description="Camera viewport at shot start")
    end_viewport: Viewport = Field(..., description="Camera viewport at shot end")
    start_content_bounds: Optional[Viewport] = None
    end_content_bounds: Optional[Viewport] = None
    focus_x: Optional[float] = Field(None, description="Focal X coordinate")
    focus_y: Optional[float] = Field(None, description="Focal Y coordinate")


class Resolution(BaseModel):
    """Target output video resolution."""
    width: int = Field(1920, description="Output width in pixels")
    height: int = Field(1080, description="Output height in pixels")


class CameraPlan(BaseModel):
    """Complete camera storyboard plan for video generation."""
    image_path: str = Field(..., description="Source comic image path")
    resolution: Resolution = Field(default_factory=Resolution)
    fps: int = Field(30, description="Frames per second")
    sequence: List[int] = Field(default_factory=lambda: [1, 2, 3, 4, 5, 6])
    preset: str = Field("educational", description="Camera preset used")
    format: str = Field("desktop", description="Detected or specified format: 'desktop' or 'mobile'")
    layout: str = Field("3x2", description="Grid layout: '3x2' or '2x3'")
    show_full_comic_between_panels: bool = Field(False, description="Whether to zoom out to full comic during tile transitions (False for continuous canvas)")
    framing: Literal["contain", "crop"] = "crop"
    panel_bounds: Dict[str, Viewport] = Field(default_factory=dict)
    protected_content_bounds: Dict[str, Dict[str, float]] = Field(default_factory=dict)
    panel_hold_seconds: float = Field(1.0, ge=0)
    push_in_zoom: float = Field(1.05, ge=1, le=1.2)
    backtrack_to_start: bool = Field(False, description="Reverse panel movement and approach before the next panel")
    total_duration: float = Field(..., description="Total video duration in seconds")
    total_frames: int = Field(..., description="Total number of frames")
    shots: List[Shot] = Field(default_factory=list, description="Ordered list of camera shots")


class InspectionResult(BaseModel):
    """Video inspection metrics."""
    file_path: str
    file_size_bytes: int
    duration_seconds: float
    width: int
    height: int
    fps: float
    codec: str
    has_audio: bool
    is_valid: bool
    details: Optional[Dict[str, Any]] = None
