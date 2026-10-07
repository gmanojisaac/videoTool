"""Local upload-and-render web interface. Run: python web_server.py"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
import logging
from pathlib import Path
import re
from threading import Lock
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from PIL import Image, UnidentifiedImageError
from mcp_tools import analyze_comic, create_camera_plan
from models.schemas import CameraPlan
from video.renderer import render_camera_plan_video, export_panel_start_frames

ROOT = Path(__file__).resolve().parent
JOBS_DIR = ROOT / "output" / "web"
MAX_UPLOAD = 20 * 1024 * 1024
JOBS = {}
LOCK = Lock()
WORKER = ThreadPoolExecutor(max_workers=1, thread_name_prefix="comic-render")


def update(job_id, **values):
    with LOCK:
        JOBS[job_id].update(values)


def render_job(job_id, image_path, modes, panel_duration, transition_duration, hold=1.0, zoom=1.05, protected=None):
    try:
        results = []
        for index, mode in enumerate(modes):
            update(job_id, status="rendering", message=f"Preparing {mode} video")
            directory = image_path.parent / mode
            analysis = analyze_comic(str(image_path), output_dir=str(directory))
            plan = CameraPlan(**create_camera_plan(analysis, format=mode,
                panel_duration_seconds=panel_duration,
                transition_duration_seconds=transition_duration,
                backtrack_to_start=True, panel_hold_seconds=hold, push_in_zoom=zoom,
                protected_content_bounds=protected, output_dir=str(directory)))
            def progress(frame, total):
                percent = int(100 * (index + frame / max(total, 1)) / len(modes))
                update(job_id, progress=percent, message=f"Rendering {mode} video")
            result = render_camera_plan_video(plan, directory / "comic_video.mp4", progress_callback=progress)
            exports = export_panel_start_frames(plan, directory / "panel_frames", width=result.width, height=result.height)
            frames = [{**item, "image_path":None, "original_image_path":None, "url":f"/api/jobs/{job_id}/frame/{mode}/{item['panel_id']}"}
                for item in exports["frames"]]
            results.append({"frames":frames,"frames_url":f"/api/jobs/{job_id}/frames/{mode}","mode": mode, "width": result.width, "height": result.height,
                "duration": result.duration_seconds, "size": result.file_size_bytes,
                "url": f"/api/jobs/{job_id}/video/{mode}"})
            update(job_id, results=list(results))
        update(job_id, status="complete", progress=100, message="Your video is ready")
    except Exception as exc:
        logging.exception("Render failed for %s", job_id)
        update(job_id, status="failed", message=f"Video generation failed: {exc}")


class Handler(BaseHTTPRequestHandler):
    def json_response(self, data, status=200):
        content = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/":
            content = (ROOT / "web" / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return
        frame_match = re.fullmatch(r"/api/jobs/([a-f0-9]{32})/(frame|frames)/(desktop|mobile)(?:/(\d+))?", path)
        if frame_match:
            job_id, kind, mode, panel_id = frame_match.groups()
            with LOCK:
                job = JOBS.get(job_id)
                result = next((item for item in job["results"] if item["mode"] == mode),None) if job else None
            if result is None:
                self.json_response({"error":"Frames are not ready"},404)
                return
            if kind == "frames" and panel_id is None:
                self.send_asset(JOBS_DIR/job_id/mode/"panel_frames"/"panel_start_frames.zip","application/zip")
            elif kind == "frame" and any(str(item["panel_id"]) == panel_id for item in result["frames"]):
                variant = "original" if "raw" in parse_qs(urlsplit(self.path).query) else "start"
                self.send_asset(JOBS_DIR/job_id/mode/"panel_frames"/f"panel_{panel_id}_{variant}.png","image/png")
            else:
                self.json_response({"error":"Frame not found"},404)
            return
        match = re.fullmatch(r"/api/jobs/([a-f0-9]{32})(?:/video/(desktop|mobile))?", path)
        if not match:
            self.json_response({"error": "Not found"}, 404)
            return
        job_id, mode = match.groups()
        with LOCK:
            job = JOBS.get(job_id)
            snapshot = json.loads(json.dumps(job)) if job else None
        if snapshot is None:
            self.json_response({"error": "Job not found. Please upload your image again."}, 404)
        elif mode is None:
            self.json_response(snapshot)
        elif any(result["mode"] == mode for result in snapshot["results"]):
            self.send_video(JOBS_DIR / job_id / mode / "comic_video.mp4", mode)
        else:
            self.json_response({"error": "Video is not ready"}, 404)

    def send_asset(self, path, content_type):
        content = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type",content_type)
        self.send_header("Content-Length",str(len(content)))
        disposition = "attachment" if "download" in parse_qs(urlsplit(self.path).query) or content_type == "application/zip" else "inline"
        self.send_header("Content-Disposition", f'{disposition}; filename="{path.name}"')
        self.end_headers()
        self.wfile.write(content)

    def send_video(self, path, mode):
        size = path.stat().st_size
        start, end = 0, size - 1
        range_header = self.headers.get("Range")
        if range_header:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header)
            if not match or not any(match.groups()):
                self.send_error(416)
                return
            first, last = match.groups()
            if first:
                start, end = int(first), min(int(last), end) if last else end
            else:
                start = max(0, size - int(last))
            if start > end or start >= size:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
        self.send_response(206 if range_header else 200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if range_header:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        disposition = "attachment" if "download" in parse_qs(urlsplit(self.path).query) else "inline"
        self.send_header("Content-Disposition", f'{disposition}; filename="comic_{mode}.mp4"')
        self.end_headers()
        try:
            with path.open("rb") as file:
                file.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    chunk = file.read(min(65536, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        parsed = urlsplit(self.path)
        if parsed.path != "/api/jobs":
            self.json_response({"error": "Not found"}, 404)
            return
        origin = self.headers.get("Origin")
        allowed_origins = {f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"}
        if origin and origin not in allowed_origins:
            self.json_response({"error": "Invalid request origin"}, 403)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_UPLOAD:
                raise ValueError("Choose a PNG or JPG image smaller than 20 MB.")
            query = parse_qs(parsed.query)
            mode = query.get("mode", ["desktop"])[0]
            if mode not in ("desktop", "mobile", "both"):
                raise ValueError("Choose desktop, mobile, or both.")
            panel = float(query.get("panel", ["5"])[0])
            transition = float(query.get("transition", ["2"])[0])
            if not (0.5 <= panel <= 30 and 0.5 <= transition <= 10):
                raise ValueError("Panel duration must be 0.5–30 seconds and movement duration 0.5–10 seconds.")
            hold = float(query.get("hold", ["1"])[0])
            zoom = float(query.get("zoom", ["1.05"])[0])
            if not 0 <= hold <= panel or not 1 <= zoom <= 1.2:
                raise ValueError("Hold must be between zero and panel duration; zoom must be 1–1.2.")
            protected = json.loads(query.get("protected", ["{}"])[0])
            if not isinstance(protected, dict) or any(not str(key).isdigit() or not isinstance(value, dict) for key, value in protected.items()):
                raise ValueError("Protected bounds must map panel IDs to rectangles.")
            data = self.rfile.read(length)
            if len(data) != length:
                raise ValueError("Upload was incomplete. Try again.")
            with Image.open(BytesIO(data)) as image:
                if image.format not in ("PNG", "JPEG"):
                    raise ValueError("Only PNG and JPG images are supported.")
                if image.width * image.height > 40_000_000:
                    raise ValueError("Image is too large. Use an image below 40 megapixels.")
                extension = ".png" if image.format == "PNG" else ".jpg"
                image.verify()
        except (ValueError, UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            self.json_response({"error": str(exc) or "Invalid image"}, 400)
            return
        job_id = uuid4().hex
        directory = JOBS_DIR / job_id
        directory.mkdir(parents=True, exist_ok=True)
        image_path = directory / ("source" + extension)
        image_path.write_bytes(data)
        with LOCK:
            JOBS[job_id] = {"id": job_id, "status": "queued", "progress": 0,
                "message": "Waiting to render", "results": []}
        modes = ["desktop", "mobile"] if mode == "both" else [mode]
        WORKER.submit(render_job, job_id, image_path, modes, panel, transition, hold, zoom, protected)
        self.json_response({"id": job_id}, 202)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Comic Video Studio: http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        WORKER.shutdown(wait=True)


if __name__ == "__main__":
    main()
