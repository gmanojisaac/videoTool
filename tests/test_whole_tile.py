"""Regression coverage: whole tile artwork must survive every focus frame."""
import numpy as np
import pytest
from models.schemas import CameraPlan, Panel, Viewport
from mcp_tools import create_camera_plan
from video.camera import compute_panel_viewports
from video.renderer import extract_frame_for_viewport, get_viewport_at_time


@pytest.mark.parametrize("aspect", [16/9, 9/16])
@pytest.mark.parametrize("dimensions", [(100, 160), (160, 100)])
def test_whole_tile_viewport_and_all_edges(aspect, dimensions):
    width, height = dimensions
    panel = Panel(id=1, x=240, y=220, width=width, height=height,
        focus_x=240, focus_y=220)
    start, end = compute_panel_viewports(panel, 400, 400, framing="contain", target_aspect=aspect)
    assert start == end
    assert start.x <= panel.x and start.y <= panel.y
    assert start.x + start.width >= panel.x + width - 1e-9
    assert start.y + start.height >= panel.y + height - 1e-9
    assert start.width/start.height == pytest.approx(aspect)
    image = np.full((400,400,3), (0,0,255), dtype=np.uint8)
    image[panel.y:panel.y+height,panel.x:panel.x+width] = (0,180,0)
    image[panel.y:panel.y+6,panel.x:panel.x+width] = (255,0,0)
    image[panel.y+height-6:panel.y+height,panel.x:panel.x+width] = (0,255,255)
    image[panel.y:panel.y+height,panel.x:panel.x+6] = (255,0,255)
    image[panel.y:panel.y+height,panel.x+width-6:panel.x+width] = (255,255,0)
    bounds = Viewport(x=panel.x,y=panel.y,width=width,height=height)
    frame = extract_frame_for_viewport(image,start,320 if aspect>1 else 180,
        180 if aspect>1 else 320, content_bounds=bounds,contain=True)
    for color in [(255,0,0),(0,255,255),(255,0,255),(255,255,0)]:
        assert np.any(np.all(frame == color,axis=2)), f"Lost tile edge {color}"
    assert not np.any(np.all(frame == (0,0,255),axis=2)), "Adjacent tile leaked into padding"


@pytest.mark.parametrize("mode", ["desktop","mobile"])
def test_contain_plan_hold_and_backtrack(mode,tmp_path):
    analysis={"image_path":"comic.png","image_width":400,"image_height":400,
        "panels":[{"id":i+1,"x":(i%3)*130,"y":(i//3)*190,"width":130,"height":190,
            "focus_x":(i%3)*130+30,"focus_y":(i//3)*190+30} for i in range(6)]}
    plan=CameraPlan(**create_camera_plan(analysis,format=mode,panel_duration_seconds=1,output_dir=str(tmp_path)))
    assert plan.framing == "contain"
    for i,shot in enumerate(plan.shots):
        if shot.type != "panel":
            continue
        assert shot.movement == "hold" and shot.duration == 1
        assert shot.start_viewport == shot.end_viewport
        assert shot.start_content_bounds == shot.end_content_bounds
        for progress in [0.1,0.5,0.9]:
            assert get_viewport_at_time(plan,shot.start+progress) == shot.start_viewport
        inbound,reverse=plan.shots[i-1],plan.shots[i+1]
        assert reverse.start_viewport == inbound.end_viewport
        assert reverse.end_viewport == inbound.start_viewport
        assert reverse.start_content_bounds == inbound.end_content_bounds
        assert reverse.end_content_bounds == inbound.start_content_bounds


def test_landscape_overview_preserves_aspect_and_full_canvas(tmp_path):
    analysis={"image_path":"comic.png","image_width":400,"image_height":300,
        "panels":[{"id":i+1,"x":(i%3)*130,"y":(i//3)*150,"width":130,"height":150,
            "focus_x":(i%3)*130+65,"focus_y":(i//3)*150+75} for i in range(6)]}
    plan=CameraPlan(**create_camera_plan(analysis,format="desktop",output_dir=str(tmp_path)))
    overview=get_viewport_at_time(plan,0)
    assert overview.width/overview.height == pytest.approx(16/9)
    assert overview.x <= 0 and overview.y <= 0
    assert overview.x+overview.width >= 400 and overview.y+overview.height >= 300
    image=np.full((300,400,3),(100,150,200),dtype=np.uint8)
    frame=extract_frame_for_viewport(image,overview,1920,1080,contain=True)
    assert np.any(np.all(frame == (100,150,200),axis=2))
    assert np.any(np.all(frame == (24,24,24),axis=2))
    for i,shot in enumerate(plan.shots):
        if shot.type == "panel":
            reverse=plan.shots[i+1]
            assert reverse.end_viewport == overview
            assert shot.start_viewport.width/shot.start_viewport.height == pytest.approx(16/9)
