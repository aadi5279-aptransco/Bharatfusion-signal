"""Replay recorded FULL-packet observations through the same research engine.
Usage: python -m insights.orderflow_replay path/to/YYYY-MM-DD.jsonl
This checks deterministic analytics, not fills or profitability.
"""
import argparse,json
from pathlib import Path
from insights.orderflow import FlowEngine

def replay(path):
    engines={};epochs={};last={};count=0
    with Path(path).open(encoding='utf-8') as f:
        for line in f:
            row=json.loads(line);key=row['instrument'];epoch=row['stream_epoch']
            if key not in engines or epochs[key]!=epoch:
                engines[key]=FlowEngine(float(row['tick_size']));epochs[key]=epoch
            engines[key].feed(row['packet'],row['received']);last[key]=row['received'];count+=1
    return dict(records=count,instruments={key:e.snapshot(last[key]) for key,e in engines.items()})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('recording');args=p.parse_args()
    print(json.dumps(replay(args.recording),indent=2))
