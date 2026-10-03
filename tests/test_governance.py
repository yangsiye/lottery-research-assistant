import numpy as np
from lottery_assistant import backtest
from lottery_assistant.models import build_dataset


def test_future_changes_cannot_alter_training_rows():
    draws=[{i%5+1} for i in range(100)]
    changed=draws[:80]+[{5} for _ in range(20)]
    X,y=build_dataset(draws,5,1);X2,y2=build_dataset(changed,5,1)
    cutoff=(80-40)*5
    np.testing.assert_array_equal(X[:cutoff],X2[:cutoff])
    np.testing.assert_array_equal(y[:cutoff],y2[:cutoff])


def test_walk_forward_training_slice_and_holdout(monkeypatch):
    draws=[{i%5+1} for i in range(120)];seen=[]
    X,y=build_dataset(draws,5,1)
    def fit(history,max_n,pick_n,dataset=None):
        seen.append(len(history))
        assert len(dataset[0])==(len(history)-40)*5
        np.testing.assert_array_equal(dataset[0],X[:len(dataset[0])])
        return {}
    monkeypatch.setattr(backtest,'fit_models',fit)
    metrics=backtest.walk_forward_metrics(draws,5,1,min_train=60,refit_every=30)
    assert metrics['uniform']['n_eval']==60
    assert metrics['uniform']['validation']['n_eval']==30
    assert metrics['uniform']['holdout']['n_eval']==30
    assert seen==[60,90]
    assert backtest.weights_from_metrics(metrics)=={'uniform':1.0}


def test_unverified_gains_cannot_enter_production():
    metrics={'uniform':{'brier':.2,'validation':{'brier':.2}},
             'hist_gb':{'brier':.01,'validation':{'brier':.01},'eligible':False}}
    assert backtest.weights_from_metrics(metrics)=={'uniform':1.0}
    metrics['hist_gb']['eligible']=True
    assert backtest.weights_from_metrics(metrics)=={'hist_gb':.05,'uniform':.95}
