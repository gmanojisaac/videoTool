# Comic Video MCP Server

A production-ready **Model Context Protocol (MCP)** server that converts a single **6-tile comic sheet (PNG/JPG)** into a cinematic educational video with smooth 2D virtual camera movements, rendered deterministically using FFmpeg.

---

## 1. What This MCP Does

This server enables LLM clients (such as Codex, Claude, and Antigravity) to take a 6-panel comic image and automatically generate a high-quality video storyboard and silent MP4.

* **Source of Truth**: The original comic image is never altered or regenerated.
* **Deterministic 2D Camera**: Operates as a virtual viewport moving across the comic image.
* **Educational Pacing**: Smooth easing, calm hold times, subtle push-ins, and contextual zoom-outs to display the whole comic between panels.
* **No Heavy Video AI**: Completely local, deterministic, and fast—no CapCut, Blender, Sora, Kling, Runway, or generative video APIs required.

---

## 2. Architecture

```text
6-TILE COMIC (PNG/JPG)
         ↓
    CODEX / MCP
         ↓
 COMIC VIDEO MCP SERVER
 ┌──────────────────────┐
 │  analyze_comic       │  -> OpenCV Panel & Focus Point Detection
 │  create_camera_plan  │  -> Storyboard & Viewport Trajectories
 │  preview_camera_plan │  -> Low-res MP4 + Visual Trajectory Diagram
 │  render_video        │  -> Stream frames directly to FFmpeg pipe
 └──────────────────────┘
         ↓
       FFmpeg (libx264, yuv420p)
         ↓
    SILENT MP4 (1920x1080 @ 30fps)
```

---

## 3. Requirements

* **Operating System**: Windows 10/11, macOS, or Linux (optimized for Windows PowerShell)
* **Python**: Python 3.11+
* **FFmpeg**: FFmpeg 5.0+ and FFprobe (auto-installed via `static-ffmpeg` if not already on system)

---

## 4. Python Setup

Clone or place the project on your machine (e.g. `D:\mcp\comic-video-mcp`):

```powershell
cd D:\mcp\comic-video-mcp
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## 5. FFmpeg Setup

The server automatically detects FFmpeg using:
1. Environment variables `FFMPEG_PATH` and `FFPROBE_PATH`
2. System `PATH`
3. Built-in `static-ffmpeg` package (downloads standalone binaries automatically if none found)

To specify a custom FFmpeg binary:
```powershell
$env:FFMPEG_PATH = "C:\ffmpeg\bin\ffmpeg.exe"
$env:FFPROBE_PATH = "C:\ffmpeg\bin\ffprobe.exe"
```

---

## 6. MCP Setup & Antigravity / Codex Configuration

Add the server to your Antigravity or Codex MCP configuration file:

### Antigravity (`%USERPROFILE%\.gemini\antigravity-ide\mcp_config.json`) or Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "comic-video": {
      "command": "D:\\mcp\\mcp-tile-camera\\.venv\\Scripts\\python.exe",
      "args": [
        "D:\\mcp\\comic-video-mcp\\server.py"
      ],
      "env": {
        "PYTHONPATH": "D:\\mcp\\comic-video-mcp"
      }
    }
  }
}
```

---

## 7. MCP Tools Reference

| Tool | Purpose | Primary Inputs |
| :--- | :--- | :--- |
| `analyze_comic` | Detects 6 panels, reading order, and focus points | `image`, `manual_panels` |
| `create_camera_plan` | Builds customizable camera storyboard JSON | `analysis`, `preset`, timing parameters |
| `preview_camera_plan` | Generates fast 540p video and visual diagram | `camera_plan`, `resolution_scale` |
| `render_video` | Renders final 1080p MP4 via FFmpeg | `camera_plan`, `output`, `width`, `height`, `fps` |
| `create_comic_video` | End-to-end convenience pipeline tool | `image`, `output`, `preset`, timing |
| `inspect_output` | Reports technical parameters of rendered video | `video_path` |

---

## 8. Supported Formats & Layouts

The server automatically detects whether your comic strip is **Desktop** or **Mobile** based on the image aspect ratio, or you can specify `format` and `layout` explicitly:

### 1. Desktop Format
* **Input**: 4:3 (or landscape) comic strip
* **Layout**: 3 columns × 2 rows (`3x2`)
* **Default Output Video**: Horizontal desktop video (`1920x1080` @ 30fps)
* **Reading Order**:
  ```text
  ┌──────────────┬──────────────┬──────────────┐
  │   PANEL 1    │   PANEL 2    │   PANEL 3    │
  ├──────────────┼──────────────┼──────────────┤
  │   PANEL 4    │   PANEL 5    │   PANEL 6    │
  └──────────────┴──────────────┴──────────────┘
  ```

### 2. Mobile Format
* **Input**: 9:16 (or portrait) comic strip
* **Layout**: 2 columns × 3 rows (`2x3`)
* **Default Output Video**: Vertical mobile video (`1080x1920` @ 30fps)
* **Reading Order**:
  ```text
  ┌──────────────┬──────────────┐
  │   PANEL 1    │   PANEL 2    │
  ├──────────────┼──────────────┤
  │   PANEL 3    │   PANEL 4    │
  ├──────────────┼──────────────┤
  │   PANEL 5    │   PANEL 6    │
  └──────────────┴──────────────┘
  ```

---

## 9. Continuous Canvas & Borderless Camera Behavior

* **Single Continuous Canvas**: The entire comic strip is treated as one large 2D scene, not a 6-frame slideshow.
* **No Visible Borders or Frames**: Story area viewports are safely inset inside panel boundaries so panel frame strokes, black border lines, and white gutters are never visibly displayed on video.
* **Continuous Travel**: The camera smoothly pushes in from the full comic overview into Panel 1, glides continuously across the canvas between story areas (Panel 1 → 2 → 3 → 4 → 5 → 6), and smoothly pulls back to the full scene overview at the end.
* **No Hard Cuts or Flashes**: Zero hard cuts, zero slideshow transitions, and zero flashing to black or white.

---

## 10. How to Analyze a Comic

Call `analyze_comic`:

```json
{
  "image": "D:/mcp/comic-video-mcp/comic.png"
}
```

* Automatically detects `format` (`desktop` or `mobile`) and `layout` (`3x2` or `2x3`).
* Can be overridden with `"format": "mobile"` or `"layout": "2x3"`.

**Output**:
* `output/analysis.json`
* `output/panel_detection_preview.png` (displays panel boundaries, badges, and reading order arrows)

---

## 11. How to Generate a Camera Plan

Call `create_camera_plan`:

```json
{
  "analysis": "output/analysis.json",
  "panel_duration_seconds": 5.0,
  "transition_duration_seconds": 2.0,
  "preset": "educational",
  "include_intro": true,
  "include_outro": true,
  "sequence": [1, 2, 3, 4, 5, 6]
}
```

* Automatically sets target resolution (`1920x1080` for desktop, `1080x1920` for mobile).
* Sets `show_full_comic_between_panels: false` so the camera glides continuously across the single canvas.

**Camera Presets**:
* `educational`: Calm framing with subtle push-in, prioritizing readability (default).
* `gentle`: Very slow, barely perceptible camera motion.
* `emotional`: Slow push-in focused on character faces.
* `object_focus`: Slow push-in focused on high-contrast objects.
* `wide`: Minimal zoom, framing the whole panel with generous margins.

---

## 12. How to Preview the Plan

Call `preview_camera_plan`:

```json
{
  "camera_plan": "output/camera_plan.json",
  "resolution_scale": 0.5
}
```

**Output**:
* `output/camera_preview.mp4` (960x540 fast preview)
* `output/camera_plan_preview.png` (camera trajectory diagram)

---

## 13. How to Render the Final Video

Call `render_video`:

```json
{
  "camera_plan": "output/camera_plan.json",
  "output": "output/comic_video.mp4",
  "width": 1920,
  "height": 1080,
  "fps": 30
}
```

Or run the complete pipeline in one shot with `create_comic_video`:

```json
{
  "image": "comic.png",
  "output": "output/comic_video.mp4",
  "preset": "educational",
  "panel_duration_seconds": 5.0,
  "transition_duration_seconds": 2.0
}
```

---

## 14. How to Change Timing

Timing parameters can be configured per run:
* `intro_duration_seconds`: Hold on full comic at the start (default: 2.0s)
* `panel_duration_seconds`: Time spent on each tile (default: 5.0s)
* `transition_duration_seconds`: Time traveling between tiles (default: 2.0s)
* `outro_duration_seconds`: Final zoom-out hold on the full comic (default: 2.0s)

---

## 14. How to Manually Override Panels and Focus

If a comic has non-standard layouts or custom focal targets, provide manual coordinates in `analyze_comic` or `create_comic_video`:

```json
{
  "image": "comic.png",
  "manual_panels": [
    { "id": 1, "x": 0, "y": 0, "width": 1300, "height": 750, "focus_x": 650, "focus_y": 375 },
    { "id": 2, "x": 1300, "y": 0, "width": 1300, "height": 750, "focus_x": 1950, "focus_y": 375 },
    { "id": 3, "x": 2600, "y": 0, "width": 1300, "height": 750, "focus_x": 3250, "focus_y": 375 },
    { "id": 4, "x": 0, "y": 750, "width": 1300, "height": 750, "focus_x": 650, "focus_y": 1125 },
    { "id": 5, "x": 1300, "y": 750, "width": 1300, "height": 750, "focus_x": 1950, "focus_y": 1125 },
    { "id": 6, "x": 2600, "y": 750, "width": 1300, "height": 750, "focus_x": 3250, "focus_y": 1125 }
  ]
}
```

---

## 15. Source Safety Verification

The original source comic file is **never modified**.
Before rendering, the system calculates the SHA-256 cryptographic hash of the input file.
After rendering, it verifies the SHA-256 hash again to guarantee 100% data immutability.

---

## 16. Running the Test Suite

Run all unit and integration tests:

```powershell
pytest tests -v
```

All 13 tests covering panel detection, reading order, manual overrides, camera plans, timing math, real FFmpeg rendering, and source safety pass with 100% green status.

---

## 17. Troubleshooting

* **FFmpeg not found**: Install `static-ffmpeg` (`pip install static-ffmpeg`) or set `$env:FFMPEG_PATH = "C:\path\to\ffmpeg.exe"`.
* **Low panel detection confidence**: Inspect `output/panel_detection_preview.png`. If the comic layout has unusual borders, supply `manual_panels` coordinates.
* **Audio Voiceover**: Audio is OFF by default (silent MP4). To mux external audio, pass `"audio": "path/to/voiceover.wav"` to `render_video`.
