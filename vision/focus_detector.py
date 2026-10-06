"""Focus point and region-of-interest detection for comic panels."""

from __future__ import annotations

import cv2
import numpy as np
from typing import Tuple, Dict, Any, Optional
from pathlib import Path


# Cache cascade classifier
_FACE_CASCADE: Optional[cv2.CascadeClassifier] = None


def get_face_cascade() -> Optional[cv2.CascadeClassifier]:
    """Loads OpenCV's default frontal face Haar Cascade."""
    global _FACE_CASCADE
    if _FACE_CASCADE is None:
        try:
            cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
            if cascade_path.is_file():
                _FACE_CASCADE = cv2.CascadeClassifier(str(cascade_path))
        except Exception:
            _FACE_CASCADE = None
    return _FACE_CASCADE


def detect_focus_point(
    image: np.ndarray,
    x: int,
    y: int,
    width: int,
    height: int,
) -> Tuple[int, int, str]:
    """Detects primary focal center within a comic panel.
    
    Returns:
        (focus_x, focus_y, focus_type) where focus_type is 'face', 'object', or 'center'
    """
    img_h, img_w = image.shape[:2]
    # Clamp panel ROI
    rx = max(0, min(x, img_w - 1))
    ry = max(0, min(y, img_h - 1))
    rw = max(1, min(width, img_w - rx))
    rh = max(1, min(height, img_h - ry))
    
    panel_crop = image[ry:ry + rh, rx:rx + rw]
    
    # 1. Try Face Detection
    cascade = get_face_cascade()
    if cascade is not None and panel_crop.size > 0:
        gray = cv2.cvtColor(panel_crop, cv2.COLOR_BGR2GRAY) if len(panel_crop.shape) == 3 else panel_crop
        # Equalize histogram for better face detection in comics/drawings
        equalized = cv2.equalizeHist(gray)
        faces = cascade.detectMultiScale(
            equalized,
            scaleFactor=1.1,
            minNeighbors=4,
            minSize=(int(rw * 0.1), int(rh * 0.1)),
            maxSize=(int(rw * 0.8), int(rh * 0.8)),
        )
        if len(faces) > 0:
            # Pick largest face
            largest_face = max(faces, key=lambda f: f[2] * f[3])
            fx, fy, fw, fh = largest_face
            center_fx = rx + fx + fw // 2
            center_fy = ry + fy + fh // 2
            return center_fx, center_fy, "face"

    # 2. Try Salient Object / Character Detection via Edge & Contrast Centroid
    # Exclude outer 12% margin of panel to avoid counting panel borders/gutters
    margin_x = int(rw * 0.12)
    margin_y = int(rh * 0.12)
    
    if rw > 2 * margin_x and rh > 2 * margin_y:
        inner_crop = panel_crop[margin_y:rh - margin_y, margin_x:rw - margin_x]
        if inner_crop.size > 0:
            gray_inner = cv2.cvtColor(inner_crop, cv2.COLOR_BGR2GRAY) if len(inner_crop.shape) == 3 else inner_crop
            # Compute gradient magnitude
            sobelx = cv2.Sobel(gray_inner, cv2.CV_32F, 1, 0, ksize=3)
            sobely = cv2.Sobel(gray_inner, cv2.CV_32F, 0, 1, ksize=3)
            magnitude = cv2.magnitude(sobelx, sobely)
            
            # Threshold to top salient edges
            threshold_val = np.percentile(magnitude, 85)
            salient_mask = (magnitude > threshold_val).astype(np.uint8)
            
            moments = cv2.moments(salient_mask)
            if moments["m00"] > 0:
                cx = int(moments["m10"] / moments["m00"])
                cy = int(moments["m01"] / moments["m00"])
                
                focal_x = rx + margin_x + cx
                focal_y = ry + margin_y + cy
                
                # Verify focal point is within safe bounds (text protection)
                safe_min_x = rx + int(rw * 0.20)
                safe_max_x = rx + int(rw * 0.80)
                safe_min_y = ry + int(rh * 0.20)
                safe_max_y = ry + int(rh * 0.80)
                
                focal_x = max(safe_min_x, min(focal_x, safe_max_x))
                focal_y = max(safe_min_y, min(focal_y, safe_max_y))
                
                return focal_x, focal_y, "object"

    # 3. Fallback: mathematical center of panel
    center_x = rx + rw // 2
    center_y = ry + rh // 2
    return center_x, center_y, "center"
