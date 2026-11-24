"""Deterministic diagnostic baselines. No promotion, calibration or live inference.

Input event features and outcomes must be independently point-in-time verified.
Holdout is excluded before computing any statistics, weights or transforms.
"""
from dataclasses import dataclass
from datetime import datetime,timedelta
from math import exp,sqrt,isfinite
from random import Random
from insights.alpha.research import Sample,walk_forward,uniqueness_weights,aware

@dataclass(frozen=True)
class Event:
    signal_id: str
    known_at: datetime
    feature_known_at: datetime
    end: datetime
    features: tuple[float,...]
    net_r: float

    def __post_init__(self):
        for t in (self.known_at,self.feature_known_at,self.end):aware(t)
        if (not self.signal_id or self.feature_known_at>self.known_at or self.end<=self.known_at
                or not self.features or any(not isfinite(x) for x in (*self.features,self.net_r))):
            raise ValueError('Invalid or future-dated event evidence')

def fit(train,iterations=300):
    """Fixed L2 logistic regression; standardizer fitted on training only."""
    p=len(train[0].features);n=len(train)
    mean=[sum(e.features[j] for e in train)/n for j in range(p)]
    scale=[sqrt(sum((e.features[j]-mean[j])**2 for e in train)/n) or 1. for j in range(p)]
    x=[[1.]+[(v-mean[j])/scale[j] for j,v in enumerate(e.features)] for e in train]
    weights=uniqueness_weights([Sample(e.known_at,e.end) for e in train],max(e.end for e in train),180.)
    total=sum(weights)
    if total<=0:raise ValueError('No usable sample weight')
    beta=[0.]*(p+1)
    def sigmoid(z):return 1/(1+exp(-max(-35.,min(35.,z))))
    for _ in range(iterations):
        grad=[0.]*(p+1)
        for row,event,weight in zip(x,train,weights):
            error=sigmoid(sum(a*b for a,b in zip(row,beta)))-int(event.net_r>0)
            for j in range(p+1):grad[j]+=weight*error*row[j]/total
        beta=[b-.05*(g+(.01*b if j else 0)) for j,(b,g) in enumerate(zip(beta,grad))]
    def predict(event):
        row=[1.]+[(v-mean[j])/scale[j] for j,v in enumerate(event.features)]
        return sigmoid(sum(a*b for a,b in zip(row,beta)))
    return predict

def metrics(values):
    return {'count':len(values),'mean_net_r':sum(values)/len(values) if values else None,
            'sum_net_r':sum(values)}

def evaluate(events,*,holdout_start,min_train=40,test_size=20,embargo=timedelta(days=1),seed=17):
    aware(holdout_start)
    if any(a.known_at>b.known_at for a,b in zip(events,events[1:])):raise ValueError('Chronological events required')
    if len({e.signal_id for e in events})!=len(events):raise ValueError('Duplicate signals')
    # No outcomes/features from final holdout enter any operation below.
    research=[e for e in events if e.known_at<holdout_start and e.end<holdout_start]
    if not research:raise ValueError('No pre-holdout events')
    dimensions={len(e.features) for e in research}
    if len(dimensions)!=1:raise ValueError('Inconsistent feature dimensions')
    samples=[Sample(e.known_at,e.end) for e in research]
    outcomes={'rule_candidates':[],'logistic':[],'random_candidate_selection':[]};folds=[]
    rng=Random(seed)
    for train_idx,test_idx in walk_forward(samples,min_train,test_size,embargo):
        train=[research[i] for i in train_idx];test=[research[i] for i in test_idx]
        if len({e.net_r>0 for e in train})<2:continue
        predict=fit(train)
        predictions=[predict(e) for e in test]
        selections=[p>=.5 for p in predictions]
        random_selected=set(rng.sample(range(len(test)),sum(selections)))
        outcomes['rule_candidates'].extend(e.net_r for e in test)
        outcomes['logistic'].extend(e.net_r for e,take in zip(test,selections) if take)
        outcomes['random_candidate_selection'].extend(e.net_r for i,e in enumerate(test) if i in random_selected)
        folds.append({'train_count':len(train),'test_count':len(test),
                      'train_last_end':max(e.end for e in train).isoformat(),
                      'test_start':test[0].known_at.isoformat(),
                      'brier_uncalibrated':sum((p-int(e.net_r>0))**2 for p,e in zip(predictions,test))/len(test)})
    return {'status':'DIAGNOSTIC_ONLY' if folds else 'INSUFFICIENT_FOLDS',
            'promotion_allowed':False,'holdout_evaluated':False,'folds':folds,
            'metrics':{k:metrics(v) for k,v in outcomes.items()},
            'config':{'min_train':min_train,'test_size':test_size,'embargo_seconds':embargo.total_seconds(),'seed':seed,'iterations':300,'threshold':.5},
            'limitations':['Probabilities are uncalibrated','No Nifty/buy-and-hold benchmark yet',
                           'Random selection is not the required random-entry benchmark',
                           'CPCV, DSR/PBO, stress and paper-forward validation still required',
                           'Net R and feature provenance must be independently verified']}
