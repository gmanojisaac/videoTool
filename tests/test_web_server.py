"""HTTP upload, validation, rendering and video delivery integration tests."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from io import BytesIO
import json
from zipfile import ZipFile
from threading import Thread
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PIL import Image
import pytest
import web_server


@pytest.fixture
def web(monkeypatch, tmp_path):
    monkeypatch.setattr(web_server, "JOBS_DIR", tmp_path)
    monkeypatch.setattr(web_server, "JOBS", {})
    worker = ThreadPoolExecutor(max_workers=1)
    monkeypatch.setattr(web_server, "WORKER", worker)
    real_render = web_server.render_camera_plan_video
    def small_render(plan, output, progress_callback):
        plan.resolution.width, plan.resolution.height = (320, 180) if plan.format == "desktop" else (180, 320)
        plan.fps = 10
        return real_render(plan, output, progress_callback=progress_callback)
    monkeypatch.setattr(web_server, "render_camera_plan_video", small_render)
    server = web_server.ThreadingHTTPServer(("127.0.0.1", 0), web_server.Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    worker.shutdown(wait=True)


def request(url, data=None, headers=None):
    try:
        response = urlopen(Request(url, data=data, headers=headers or {}), timeout=10)
    except HTTPError as error:
        response = error
    with response:
        return response.status, response.headers, response.read()


def comic():
    image = Image.new("RGB", (600, 450), "white")
    from PIL import ImageDraw
    draw = ImageDraw.Draw(image)
    for row in range(2):
        for col in range(3):
            draw.rectangle((col*200+10,row*225+10,col*200+190,row*225+215), fill=(60+col*60,90+row*80,130), outline="black", width=4)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_upload_validation_and_page(web):
    status, _, content = request(web)
    assert status == 200 and b"Create video" in content
    for query, body in [("mode=invalid", comic()), ("mode=desktop", b"invalid image"), ("panel=nan", comic())]:
        status, _, body = request(web + "/api/jobs?" + query, body)
        assert status == 400 and "error" in json.loads(body)
    status, _, _ = request(web + "/api/jobs?mode=desktop", comic(), {"Origin":"https://example.com"})
    assert status == 403
    assert request(web + "/api/jobs/" + "0"*32)[0] == 404
    assert request(web + "/api/jobs/../../requirements.txt")[0] == 404


@pytest.mark.parametrize("mode,expected", [("desktop", ["desktop"]), ("mobile", ["mobile"]), ("both", ["desktop", "mobile"])])
def test_upload_to_real_video_download(web, mode, expected):
    status, _, body = request(web + f"/api/jobs?mode={mode}&panel=0.5&transition=0.5&hold=0.1", comic())
    assert status == 202
    job_id = json.loads(body)["id"]
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        _, _, body = request(web + "/api/jobs/" + job_id)
        job = json.loads(body)
        if job["status"] in ("complete", "failed"):
            break
        time.sleep(0.1)
    assert job["status"] == "complete", job
    assert job["progress"] == 100
    assert [item["mode"] for item in job["results"]] == expected
    for item in job["results"]:
        assert len(item["frames"]) == 6
        status, headers, archive = request(web + item["frames_url"])
        assert status == 200 and headers["Content-Type"] == "application/zip"
        with ZipFile(BytesIO(archive)) as bundle:
            assert len([name for name in bundle.namelist() if name.endswith('.png')]) == 12
            assert 'edit_markers.json' in bundle.namelist()
        for frame in item["frames"]:
            status, headers, png = request(web + frame["url"] + '?download=1')
            assert status == 200 and headers["Content-Type"] == "image/png"
            assert "attachment" in headers["Content-Disposition"]
            with Image.open(BytesIO(png)) as image:
                assert image.size == (item["width"], item["height"])
        assert request(web + item["frames"][0]["url"] + "?raw=1&download=1")[0] == 200
        assert request(web + f"/api/jobs/{job_id}/frame/{item['mode']}/999")[0] == 404
        status, headers, video = request(web + item["url"] + "?download=1")
        assert status == 200
        assert headers["Content-Type"] == "video/mp4"
        assert "attachment" in headers["Content-Disposition"]
        assert b"ftyp" in video[:32]
        status, headers, chunk = request(web + item["url"], headers={"Range":"bytes=0-99"})
        assert status == 206 and chunk == video[:100]
        assert headers["Content-Range"].startswith("bytes 0-99/")
        assert request(web + item["url"], headers={"Range":"bytes=999999999-"})[0] == 416
