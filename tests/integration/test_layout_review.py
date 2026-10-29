import numpy as np
from majoor_videotools.core.layout_review import subject_overlap


def test_existing_mask_reports_canvas_and_html_subject_overlap():
    masks=np.zeros((2,10,10),dtype=np.float32)
    masks[1,:,5:]=1
    samples=[{'time':1.5,'canvas':[{'rect':[5,0,10,10],'alpha':1}],
              'html':[{'rect':[0,0,4,10]}]}]
    report=subject_overlap(samples,masks,(10,10),2)
    assert report['status']=='measured'
    assert report['overlaps']==[{'time':1.5,'kind':'canvas','layer':0,'fraction':1.0}]


def test_missing_mask_is_not_a_success_and_invisible_text_is_ignored():
    samples=[{'time':0,'canvas':[{'rect':[0,0,10,10],'alpha':0}]}]
    assert subject_overlap(samples,None,(10,10),2)['status']=='not_evaluated'
    assert subject_overlap(samples,np.ones((1,10,10)),(10,10),2)['overlaps']==[]
