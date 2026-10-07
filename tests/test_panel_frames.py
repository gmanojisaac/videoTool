from zipfile import ZipFile
import json
import cv2
import numpy as np
import pytest
from mcp_tools import create_camera_plan
from models.schemas import CameraPlan
from video.renderer import export_panel_start_frames, extract_frame_for_viewport, calculate_file_sha256


@pytest.mark.parametrize("mode,resolution",[("desktop",(320,180)),("mobile",(180,320))])
def test_start_png_exactly_matches_complete_focus_frame_and_manifest(mode,resolution,tmp_path):
    source=tmp_path/'comic.png'
    image=np.full((300,400,3),(0,0,255),dtype=np.uint8)
    image[20:160,30:190]=(100,180,30)
    cv2.imwrite(str(source),image)
    before=calculate_file_sha256(source)
    analysis={"image_path":str(source),"image_width":400,"image_height":300,
        "panels":[{"id":1,"x":30,"y":20,"width":160,"height":140,"focus_x":110,"focus_y":90}]}
    plan=CameraPlan(**create_camera_plan(analysis,format=mode,width=resolution[0],height=resolution[1],
        sequence=[1,1],protected_content_bounds={"1":{"x":50,"y":40,"width":120,"height":100}},
        push_in_zoom=1.1,output_dir=str(tmp_path)))
    exports=export_panel_start_frames(plan,tmp_path/'frames')
    assert len(exports["frames"]) == 1
    item=exports["frames"][0]
    shot=next(shot for shot in plan.shots if shot.type=='panel')
    expected=extract_frame_for_viewport(image,shot.start_viewport,*resolution,
        content_bounds=shot.start_content_bounds,contain=True)
    np.testing.assert_array_equal(cv2.imread(item["image_path"]),expected)
    assert item["focus_start_seconds"] == shot.start
    assert item["hold_end_seconds"] == shot.start+shot.hold_duration_seconds
    np.testing.assert_array_equal(cv2.imread(item["original_image_path"]),image[20:160,30:190])
    assert calculate_file_sha256(source) == before
    with ZipFile(exports["archive_path"]) as bundle:
        assert set(bundle.namelist()) == {'panel_1_start.png','panel_1_original.png','edit_markers.json'}
        manifest=json.loads(bundle.read('edit_markers.json'))
        assert manifest["mode"] == mode and manifest["frames"][0]["panel_id"] == 1
