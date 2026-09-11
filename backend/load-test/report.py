#!/usr/bin/env python3
"""Join k6 request samples with the backend's one-second pool/JVM measurements."""
import argparse, collections, datetime, json, math
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('requests'); p.add_argument('metrics'); p.add_argument('--output',default='results.json')
a=p.parse_args()
rows=collections.defaultdict(lambda:collections.defaultdict(list)); failures=collections.defaultdict(list)
intervals=collections.defaultdict(list); statuses=collections.defaultdict(collections.Counter)
def epoch(s): return datetime.datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()*1000
def pct(values,q):
    if not values:return None
    values=sorted(values); at=(len(values)-1)*q; lo=int(at); hi=min(lo+1,len(values)-1)
    return round(values[lo]+(values[hi]-values[lo])*(at-lo),2)
with open(a.requests) as f:
    for line in f:
        x=json.loads(line)
        if x.get('type')!='Point':continue
        data=x['data']; tags=data.get('tags',{}); level=tags.get('level','ramp')
        if level=='ramp':continue
        if x['metric']=='http_req_duration':
            rows[level][tags['endpoint']].append(data['value'])
            intervals[level].append(epoch(data['time']))
            statuses[level][tags.get('status','unknown')]+=1
        elif x['metric']=='backend_failures':failures[level].append(data['value'])
metrics=[json.loads(line) for line in Path(a.metrics).read_text().splitlines()]
report=[]
for level in sorted(rows,key=int):
    values=[v for vv in rows[level].values() for v in vv]
    start=min(intervals[level]); end=max(intervals[level]); samples=[m for m in metrics if start<=m['time']<=end]
    endpoints={k:{'requests':len(v),'p50_ms':pct(v,.5),'p95_ms':pct(v,.95),'p99_ms':pct(v,.99)} for k,v in rows[level].items()}
    row={'vus':int(level),'requests':len(values),'observed_completion_window_seconds':round((end-start)/1000,2),
         'completion_rps':round(len(values)/max((end-start)/1000,1),2),'p95_ms':pct(values,.95),
         'contract_failures':sum(failures[level]),'failure_percent':round(100*sum(failures[level])/max(len(failures[level]),1),2),
         'statuses':dict(statuses[level]),'endpoints':endpoints}
    if samples:
        for k in ['db_active','db_pending','db_timeouts','tomcat_busy','tomcat_threads','async_active','async_queue','process_cpu','system_cpu','heap_bytes']:
            row[k+'_max']=max(m[k] for m in samples)
            row[k+'_median']=pct([m[k] for m in samples],.5)
        row['db_pending_sample_percent']=round(100*sum(m['db_pending']>0 for m in samples)/len(samples),2)
        row['db_timeout_delta']=max(m['db_timeouts'] for m in samples)-min(m['db_timeouts'] for m in samples)
    report.append(row)
Path(a.output).write_text(json.dumps(report,indent=2))
print('| VUs | Requests | RPS* | p95 ms | Contract failure % | Max DB waiters | Max Tomcat busy |')
print('|---:|---:|---:|---:|---:|---:|---:|')
for r in report: print(f"| {r['vus']} | {r['requests']} | {r['completion_rps']} | {r['p95_ms']} | {r['failure_percent']} | {r.get('db_pending_max','NA')} | {r.get('tomcat_busy_max','NA')} |")
print('*RPS uses the observed completion window of requests tagged at plateau start; see raw samples for transition effects.')
