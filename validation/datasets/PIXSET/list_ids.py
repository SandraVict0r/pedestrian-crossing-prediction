import argparse, numpy as np
from collections import defaultdict
from pioneer.das.api.platform import Platform

CAND_ID_KEYS = ['track_id','tracking_id','id','uuid','uid','instance_id','object_id']
def extract_track_ids(b):
    for m in ('get_track_ids','get_ids','track_ids','ids'):
        if hasattr(b,m):
            try:
                arr = getattr(b,m)()
                if arr is not None: return np.asarray(arr).astype(str)
            except: pass
    for m in ('attributes','get_attributes'):
        if hasattr(b,m):
            try:
                attrs = getattr(b,m)()
                if isinstance(attrs,dict):
                    for k in CAND_ID_KEYS:
                        if k in attrs: return np.asarray(attrs[k]).astype(str)
                if isinstance(attrs,(list,tuple)) and attrs and isinstance(attrs[0],dict):
                    for k in CAND_ID_KEYS:
                        if k in attrs[0]: return np.array([str(a.get(k)) for a in attrs])
            except: pass
    for k in CAND_ID_KEYS:
        for m in ('get_attribute','get_field'):
            if hasattr(b,m):
                try:
                    arr = getattr(b,m)(k)
                    if arr is not None: return np.asarray(arr).astype(str)
                except: pass
        m = 'get_'+k
        if hasattr(b,m):
            try:
                arr = getattr(b,m)()
                if arr is not None: return np.asarray(arr).astype(str)
            except: pass
    return None

ap = argparse.ArgumentParser()
ap.add_argument("run")
ap.add_argument("--boxes", required=True)
args = ap.parse_args()

pf = Platform(args.run)
sync = pf.synchronized(sync_labels=[args.boxes], tolerance_us=1e6)

by_cat = defaultdict(set)
count_by_id = defaultdict(int)
frames_with = frames_total = 0

for k in range(len(sync)):
    frames_total += 1
    b = sync[k][args.boxes]
    cats = b.get_categories()
    ids  = extract_track_ids(b)
    if ids is None or len(ids) != len(cats): 
        continue
    frames_with += 1
    for c,i in zip(cats, ids):
        by_cat[str(c)].add(str(i))
        count_by_id[str(i)] += 1

print(f"Frames totales: {frames_total}, frames avec boxes: {frames_with}")
for c in sorted(by_cat.keys()):
    ids = sorted(by_cat[c], key=lambda z: (count_by_id[z], z), reverse=True)
    print(f"[{c}]  n_ids={len(ids)}  exemples: {', '.join(ids[:20])}")
print("\nIDs les plus fréquents (toutes classes confondues):")
top = sorted(count_by_id.items(), key=lambda kv: kv[1], reverse=True)[:30]
print(", ".join(f\"{k}({v})\" for k,v in top))
