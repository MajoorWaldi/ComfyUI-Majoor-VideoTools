import json,subprocess
import pytest
from majoor_videotools.core.motion import EFFECTS,parse_layers,render_motion
from majoor_videotools.core.hyperframes import runtime_paths
from majoor_videotools.core.media_probe import probe


def test_every_footage_effect_is_rendered_by_the_shared_compositor(tmp_path):
    try:runtime_paths()
    except RuntimeError:pytest.skip('Optional HyperFrames runtime required')
    source=tmp_path/'source.mp4'
    subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i','testsrc2=s=320x240:r=24:d=3','-c:v','libx264','-pix_fmt','yuv420p',str(source)],check=True)
    kinds=[kind for kind in EFFECTS if kind!='echo']  # echo needs a subject mask
    step=3/len(kinds)
    layers=[{'type':'effect','kind':kind,'start':i*step,'end':min(3,(i+1)*step),'amount':.7,'flicker':4,'speed':.4} for i,kind in enumerate(kinds)]
    output=tmp_path/'effects.mp4'
    render_motion(source,parse_layers(json.dumps(layers),3),output)
    info=probe(output,with_packets=False)
    assert info.frame_count==72 and info.display_size==(320,240)


@pytest.mark.parametrize('width,height,position', [(320,240,'bottom'),(240,320,'bottom_right'),(240,240,'top_right')])
def test_planner_titles_keep_their_safe_area_and_wrap_in_the_shared_compositor(tmp_path,width,height,position):
    import numpy as np
    from majoor_videotools.core.fx import safe_box, TEXT_POSITIONS
    try:runtime_paths()
    except RuntimeError:pytest.skip('Optional HyperFrames runtime required')
    source=tmp_path/'source.mp4'
    subprocess.run(['ffmpeg','-y','-v','error','-f','lavfi','-i',f'color=c=gray:s={width}x{height}:r=24:d=2','-c:v','libx264','-pix_fmt','yuv420p',str(source)],check=True)
    rows=[{'type':'text','content':'LONG PRODUCT NAME WITH EXTRA WORDS','safe':True,'position':position,'size':.2,'color':'#ff0000'}]
    output=tmp_path/'title.mp4';render_motion(source,parse_layers(json.dumps(rows),2),output)
    raw=subprocess.run(['ffmpeg','-v','error','-ss','1','-i',str(output),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'],capture_output=True,check=True).stdout
    frame=np.frombuffer(raw,np.uint8).reshape(height,width,3)
    ys,xs=np.nonzero((frame[...,0]>180)&(frame[...,1]<70)&(frame[...,2]<70))
    left,top,right,bottom=safe_box(width,height,TEXT_POSITIONS[position][0])
    assert len(xs)>50 and xs.min()>=left and xs.max()<right
    assert ys.min()>=top and ys.max()<bottom
