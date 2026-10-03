from lottery_assistant.features import number_features, structure_features, ac_value


def test_features_basic():
    h=[{1,2,3},{2,3,4},{3,4,5}]
    f=number_features(h,3,10,3)
    assert f['omission']==0
    assert 'omission_z' in f
    assert 'transition_lift' in f
    s=structure_features([1,3,5],10,{2,4,5})
    assert s['odd']==3
    assert s['repeat_prev']==1
    assert 'ac' in s


def test_ac_value_nonnegative():
    assert ac_value([1,2,3]) >= 0
    assert ac_value([1]) == 0
