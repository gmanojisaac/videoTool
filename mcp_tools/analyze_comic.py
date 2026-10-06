"""MCP Tool: analyze_comic"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, Optional, List

from config import OUTPUT_DIR
from vision.panel_detector import analyze_comic_image


def analyze_comic(
    image: str,
    manual_panels: Optional[List[Dict[str, Any]]] = None,
    output_dir: Optional[str] = None,
    format: Optional[str] = None,
    layout: Optional[str] = None,
) -> Dict[str, Any]:
    """Analyzes a 6-tile comic sheet, detects format (desktop/mobile), layout (3x2/2x3), panels, reading order, and focus points.
    
    Args:
        image: Path to the comic PNG/JPG image file.
        manual_panels: Optional list of manual panel coordinates to override auto-detection.
        output_dir: Directory where analysis.json and diagnostic preview will be saved.
        format: Optional format override ('desktop' or 'mobile'). Automatically detected if omitted.
        layout: Optional layout override ('3x2' or '2x3'). Automatically detected if omitted.
        
    Returns:
        Analysis summary including image dimensions, detected format, layout, panels, confidence, and preview path.
    """
    img_path = Path(image).resolve()
    if not img_path.is_file():
        raise FileNotFoundError(f"Comic image file not found: {img_path}")

    out_dir = Path(output_dir).resolve() if output_dir else OUTPUT_DIR.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    
    diag_preview_path = out_dir / "panel_detection_preview.png"
    
    analysis = analyze_comic_image(
        image_path=img_path,
        manual_panels=manual_panels,
        preview_output_path=diag_preview_path,
        format=format,
        layout=layout,
    )
    
    # Save analysis.json
    analysis_dict = analysis.model_dump()
    json_path = out_dir / "analysis.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(analysis_dict, f, indent=2)
        
    analysis_dict["analysis_file"] = str(json_path)
    return analysis_dict
