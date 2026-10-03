from __future__ import annotations
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from .features import number_features

# Curated, non-rule feature set. Correlated observations may coexist as model inputs,
# but none has a pre-imposed 'hot wins' or 'cold wins' sign.
FEATURE_KEYS=[
    'freq_10','freq_20','freq_30','freq_50','freq_100',
    'freq_z_10','freq_z_20','freq_z_50','freq_z_100',
    'omission_ratio','omission_z',
    'exp_freq_10','exp_freq_20','exp_freq_50',
    'trend_10_50','trend_20_100','bayes_mean',
    'last_draw','neighbor_last','same_tail_last','transition_lift',
    'gap_mean','gap_cv',
]


def build_dataset(draw_sets, max_n, pick_n, min_history=40):
    X=[]; y=[]
    for t in range(min_history, len(draw_sets)):
        hist=draw_sets[:t]
        target=draw_sets[t]
        for n in range(1,max_n+1):
            f=number_features(hist,n,max_n,pick_n)
            X.append([f[k] for k in FEATURE_KEYS])
            y.append(1 if n in target else 0)
    return np.asarray(X,float), np.asarray(y,int)


def fit_models(draw_sets,max_n,pick_n,dataset=None):
    X,y=dataset if dataset is not None else build_dataset(draw_sets,max_n,pick_n)
    models={}
    if len(y)<200 or len(np.unique(y))<2:
        return models
    # Logistic provides an interpretable regularized linear challenger/anchor.
    lr=make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=1500,class_weight=None,C=.25,solver='lbfgs')
    )
    lr.fit(X,y)
    models['logistic']=lr

    # Nonlinear interactions without deep-learning sample-size demands.
    gb=HistGradientBoostingClassifier(
        max_iter=140,
        learning_rate=.04,
        max_leaf_nodes=15,
        min_samples_leaf=30,
        l2_regularization=2.0,
        random_state=42,
    )
    gb.fit(X,y)
    models['hist_gb']=gb
    return models


def predict_probs(models, history_sets, max_n,pick_n):
    X=[]
    for n in range(1,max_n+1):
        f=number_features(history_sets,n,max_n,pick_n)
        X.append([f[k] for k in FEATURE_KEYS])
    X=np.asarray(X,float)
    p0=pick_n/max_n
    out={'uniform':np.full(max_n,p0)}
    # Bayesian anchor uses all-history inclusion with shrinkage; it is conservative by design.
    out['bayes']=np.array([
        number_features(history_sets,n,max_n,pick_n)['bayes_mean']
        for n in range(1,max_n+1)
    ])
    for name,m in models.items():
        out[name]=m.predict_proba(X)[:,1]
    return out
