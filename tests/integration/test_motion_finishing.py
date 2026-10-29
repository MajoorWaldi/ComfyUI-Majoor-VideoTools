import numpy as np
import pytest

from majoor_videotools.core.motion import _effect


@pytest.mark.parametrize('kind',['grain','vignette','light_leak','pan','roll','handheld'])
def test_finishing_effects_are_deterministic_and_zero_is_identity(kind):
    frame=np.full((64,96,3),130,np.uint8)
    layer={'kind':kind,'amount':0,'flicker':0,'target':'frame','start':0}
    unchanged=frame.copy()
    _effect(unchanged,layer,{'alpha':1},.4,9,None)
    assert np.array_equal(frame,unchanged)
    layer['amount']=.7
    a,b=frame.copy(),frame.copy()
    _effect(a,layer,{'alpha':1},.4,9,None)
    _effect(b,layer,{'alpha':1},.4,9,None)
    assert np.array_equal(a,b)
    assert a.shape==frame.shape and a.min()>0
