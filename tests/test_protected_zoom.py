import cv2
import numpy as np
import pytest
from mcp_tools import create_camera_plan, analyze_comic
from models.schemas import CameraPlan, Panel, Viewport
from video.camera import compute_panel_viewports
from video.renderer import extract_frame_for_viewport, get_viewport_at_time, render_camera_plan_video


def analysis(image_path="comic.png"):
    return {"image_path":str(image_path),"image_width":400,"image_height":300,
        "panels":[{"id":1,"x":0,"y":0,"width":160,"height":100,"focus_x":0,"focus_y":0},
                  {"id":2,"x":240,"y":200,"width":160,"height":100,"focus_x":400,"focus_y":300}]}


def encloses(view,bounds):
    assert view.x <= bounds["x"]+1e-8
    assert view.y <= bounds["y"]+1e-8
    assert view.x+view.width >= bounds["x"]+bounds["width"]-1e-8
    assert view.y+view.height >= bounds["y"]+bounds["height"]-1e-8


@pytest.mark.parametrize("aspect",[16/9,9/16])
def test_safe_zoom_reduces_requested_amount_and_preserves_every_sample(aspect):
    panel=Panel(**analysis()["panels"][1])
    protected={"x":242,"y":202,"width":156,"height":96}
    start,end=compute_panel_viewports(panel,400,300,target_aspect=aspect,
        framing="contain",zoom_factor=1.2,protected_content_bounds=protected)
    assert start.width > end.width
    assert start.width/end.width < 1.2
    from video.camera import interpolate_viewports
    for progress in np.linspace(0,1,21):
        view=interpolate_viewports(start,end,float(progress))
        encloses(view,protected)
        assert view.width/view.height == pytest.approx(aspect)


@pytest.mark.parametrize("protected",[None,{"x":0,"y":0,"width":160,"height":100}])
def test_no_safe_zoom_falls_back_to_full_panel(protected):
    panel=Panel(**analysis()["panels"][0])
    start,end=compute_panel_viewports(panel,400,300,framing="contain",zoom_factor=1.2,
        protected_content_bounds=protected)
    assert start == end
    encloses(start,{"x":0,"y":0,"width":160,"height":100})


@pytest.mark.parametrize("invalid",[{}, {"x":-1,"y":0,"width":100,"height":90},
    {"x":0,"y":0,"width":0,"height":10}, {"x":0,"y":0,"width":float("nan"),"height":10}])
def test_invalid_protected_bounds_rejected(invalid,tmp_path):
    with pytest.raises(ValueError):
        create_camera_plan(analysis(),protected_content_bounds={"1":invalid},output_dir=str(tmp_path))


def test_hold_then_push_and_exact_two_stage_reverse(tmp_path):
    plan=CameraPlan(**create_camera_plan(analysis(),panel_duration_seconds=3,panel_hold_seconds=1,
        push_in_zoom=1.1,protected_content_bounds={"1":{"x":20,"y":20,"width":100,"height":60}},
        output_dir=str(tmp_path)))
    shots=plan.shots
    index=next(i for i,s in enumerate(shots) if s.type=="panel")
    entry,shot,undo_zoom,undo_entry=shots[index-1:index+3]
    assert shot.start_viewport != shot.end_viewport
    assert undo_zoom.duration == 2
    assert undo_entry.duration == entry.duration
    assert entry.start_content_bounds is None and undo_entry.start_content_bounds is None
    assert shot.start_content_bounds is not None and undo_zoom.start_content_bounds is not None
    for offset in [0,0.25,0.99,1]:
        assert get_viewport_at_time(plan,shot.start+offset)==shot.start_viewport
    for progress in [0.1,0.3,0.7,0.9]:
        a=get_viewport_at_time(plan,shot.start+1+2*progress)
        b=get_viewport_at_time(plan,undo_zoom.start+2*(1-progress))
        assert list(a.model_dump().values())==pytest.approx(list(b.model_dump().values()))
        a=get_viewport_at_time(plan,entry.start+entry.duration*progress)
        b=get_viewport_at_time(plan,undo_entry.start+undo_entry.duration*(1-progress))
        assert list(a.model_dump().values())==pytest.approx(list(b.model_dump().values()))
    for a,b in zip(shots,shots[1:]):
        assert a.end_viewport==b.start_viewport
        assert a.end==b.start


@pytest.mark.parametrize("mode,resolution",[("desktop",(320,180)),("mobile",(180,320))])
def test_planned_zoom_and_actual_encoded_frames_preserve_protected_content(mode,resolution,tmp_path):
    image=np.full((300,400,3),(0,0,255),dtype=np.uint8)
    image[:100,:160]=(0,150,0)
    # Four corner markers represent the protected content's outer extent.
    protected={"x":20,"y":20,"width":120,"height":60}
    for x,y in [(20,20),(130,20),(20,70),(130,70)]:
        image[y:y+10,x:x+10]=(255,255,0)
    source=tmp_path/'comic.png'
    cv2.imwrite(str(source),image)
    plan=CameraPlan(**create_camera_plan(analysis(source),format=mode,width=resolution[0],height=resolution[1],
        sequence=[1],panel_duration_seconds=1,panel_hold_seconds=0.25,push_in_zoom=1.1,
        transition_duration_seconds=0.25,intro_duration_seconds=0.25,outro_duration_seconds=0.25,
        fps=20,protected_content_bounds={"1":protected},output_dir=str(tmp_path)))
    panel_shot=next(s for s in plan.shots if s.type=="panel")
    for progress in np.linspace(0,1,11):
        viewport=get_viewport_at_time(plan,panel_shot.start+float(progress)*panel_shot.duration)
        encloses(viewport,protected)
        frame=extract_frame_for_viewport(image,viewport,*resolution,
            content_bounds=panel_shot.start_content_bounds,contain=True)
        assert not np.any(np.all(frame==(0,0,255),axis=2))
    video=tmp_path/'safe.mp4'
    render_camera_plan_video(plan,video)
    capture=cv2.VideoCapture(str(video))
    for t in [panel_shot.start,panel_shot.start+0.2,panel_shot.end-0.05]:
        capture.set(cv2.CAP_PROP_POS_MSEC,t*1000)
        success,frame=capture.read()
        assert success
        mask=((frame[:,:,0]>200)&(frame[:,:,1]>200)&(frame[:,:,2]<60)).astype(np.uint8)
        count,_,stats,_=cv2.connectedComponentsWithStats(mask)
        assert sum(area>3 for area in stats[1:,cv2.CC_STAT_AREA])==4
    capture.release()


def test_manual_panel_bounds_survive_analysis(tmp_path):
    source=tmp_path/'comic.png'
    cv2.imwrite(str(source),np.full((300,400,3),200,dtype=np.uint8))
    panels=analysis()["panels"]
    panels[0]["protected_content_bounds"]={"x":20,"y":20,"width":100,"height":60}
    result=analyze_comic(str(source),manual_panels=panels,output_dir=str(tmp_path))
    assert result["panels"][0]["protected_content_bounds"]==panels[0]["protected_content_bounds"]
