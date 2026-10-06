"""FFmpeg and FFprobe execution and media inspection."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, List

from config import FFMPEG_BIN, FFPROBE_BIN, find_ffmpeg_binaries
from models.schemas import InspectionResult


def get_ffmpeg_executable() -> str:
    """Returns the verified path to the ffmpeg executable or raises RuntimeError."""
    global FFMPEG_BIN
    if FFMPEG_BIN and Path(FFMPEG_BIN).is_file():
        return str(FFMPEG_BIN)
        
    ffmpeg, _ = find_ffmpeg_binaries()
    if ffmpeg and Path(ffmpeg).is_file():
        FFMPEG_BIN = ffmpeg
        return str(ffmpeg)
        
    raise RuntimeError(
        "FFmpeg executable not found. Please install ffmpeg or set FFMPEG_PATH environment variable."
    )


def get_ffprobe_executable() -> str:
    """Returns the verified path to the ffprobe executable or raises RuntimeError."""
    global FFPROBE_BIN
    if FFPROBE_BIN and Path(FFPROBE_BIN).is_file():
        return str(FFPROBE_BIN)
        
    _, ffprobe = find_ffmpeg_binaries()
    if ffprobe and Path(ffprobe).is_file():
        FFPROBE_BIN = ffprobe
        return str(ffprobe)
        
    raise RuntimeError(
        "FFprobe executable not found. Please install ffprobe or set FFPROBE_PATH environment variable."
    )


def inspect_video_file(video_path: str | Path) -> InspectionResult:
    """Inspects video file metadata using ffprobe and file inspection."""
    path = Path(video_path)
    if not path.is_file():
        raise FileNotFoundError(f"Video file does not exist: {path}")
        
    file_size = path.stat().st_size
    ffprobe_bin = get_ffprobe_executable()
    
    cmd = [
        ffprobe_bin,
        "-v", "error",
        "-show_entries", "format=duration,size:stream=width,height,r_frame_rate,codec_name,codec_type",
        "-of", "json",
        str(path.resolve()),
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"FFprobe failed to inspect file: {proc.stderr}")
        
    data = json.loads(proc.stdout)
    
    duration = float(data.get("format", {}).get("duration", 0.0))
    streams = data.get("streams", [])
    
    video_stream = None
    has_audio = False
    
    for s in streams:
        if s.get("codec_type") == "video" and not video_stream:
            video_stream = s
        elif s.get("codec_type") == "audio":
            has_audio = True
            
    if not video_stream:
        raise ValueError(f"No video stream found in {path}")
        
    width = int(video_stream.get("width", 0))
    height = int(video_stream.get("height", 0))
    codec = video_stream.get("codec_name", "unknown")
    
    # Calculate FPS
    r_frame_rate = video_stream.get("r_frame_rate", "30/1")
    if "/" in r_frame_rate:
        num, den = r_frame_rate.split("/")
        fps = float(num) / max(float(den), 1.0)
    else:
        fps = float(r_frame_rate)
        
    return InspectionResult(
        file_path=str(path.resolve()),
        file_size_bytes=file_size,
        duration_seconds=round(duration, 3),
        width=width,
        height=height,
        fps=round(fps, 2),
        codec=codec,
        has_audio=has_audio,
        is_valid=True,
        details=data,
    )


def mux_audio_into_video(
    video_path: str | Path,
    audio_path: str | Path,
    output_path: str | Path,
) -> Tuple[bool, Optional[str]]:
    """Muxes an external audio track into the MP4 file."""
    ffmpeg_bin = get_ffmpeg_executable()
    v_path = Path(video_path).resolve()
    a_path = Path(audio_path).resolve()
    out_path = Path(output_path).resolve()
    
    if not a_path.is_file():
        return False, f"Audio file not found: {a_path}"
        
    cmd = [
        ffmpeg_bin,
        "-y",
        "-i", str(v_path),
        "-i", str(a_path),
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        str(out_path),
    ]
    
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return False, proc.stderr
    return True, None
