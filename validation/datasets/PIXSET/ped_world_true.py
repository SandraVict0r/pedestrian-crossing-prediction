#!/usr/bin/env python3
import argparse, math
import numpy as np
import matplotlib.pyplot as plt
from pioneer.das.api.platform import Platform

def equirect_xy(lat, lon, lat0, lon0):
    R = 6371000.0
    lat = np.asarray(lat, float); lon = np.asarray(lon, float)
    lat0 = float(lat0); lon0 = float(lon0)
    latr  = np.radians(lat);  lonr  = np.radians(lon)
    lat0r = math.radians(lat0); lon0r = math.radians(lon0)
    x = R * (lonr - lon0r) * np.cos(0.5*(latr + lat0r))  # East
    y = R * (latr - lat0r)                               # North
    return x, y

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

def rad(yaw):
    y = float(yaw)
    return math.radians(y) if abs(y) > 6.28318 else y

ap = argparse.ArgumentParser()
ap.add_argument("run")
ap.add_argument("--boxes", required=True)
ap.add_argument("--track-id", help="ID à tracer (utilise list_ids.py pour le trouver)")
ap.add_argument("--step", type=int, default=3)
args = ap.parse_args()

pf = Platform(args.run)
sync = pf.synchronized(sync_labels=[args.boxes,"sbgekinox_bcc_navposvel","sbgekinox_bcc_ekfeuler"], tolerance_us=1e6)

lat0 = lon0 = None
ex_list, ey_list, px_list, py_list, tt = [], [], [], [], []

for k in range(len(sync)):
    fr = sync[k]
    try:
        nav = fr["sbgekinox_bcc_navposvel"].raw
        lat, lon = float(nav["latitude"]), float(nav["longitude"])
        if lat0 is None:
            lat0, lon0 = lat, lon
        ex, ey = equirect_xy(lat, lon, lat0, lon0)
        yaw = rad(fr["sbgekinox_bcc_ekfeuler"].raw.get("yaw", 0.0))

        b = fr[args.boxes]
        ids = extract_track_ids(b)
        if ids is None: 
            continue
        centers = b.get_centers()
        # traverse toutes les box de ce frame, on ramasse celles qui ont l'ID voulu
        for i, tid in enumerate(ids):
            if args.track-id is not None and str(tid) != str(args.track_id):
                continue
            cx, cy = float(centers[i][0]), float(centers[i][1])  # ego x,y
            dN =  cx*math.cos(yaw) - cy*math.sin(yaw)
            dE =  cx*math.sin(yaw) + cy*math.cos(yaw)
            px_list.append(ex + dE); py_list.append(ey + dN)
            ex_list.append(ex);      ey_list.append(ey)
            tt.append(k)
    except Exception:
        continue

if not px_list:
    print("[X] rien pour cet ID/cette couche (essaie d'abord list_ids.py).")
    raise SystemExit(1)

ex = np.array(ex_list); ey = np.array(ey_list)
px = np.array(px_list); py = np.array(py_list)
tt = np.array(tt)

fig, ax = plt.subplots(figsize=(12,6))
ax.plot(ex, ey, label="Ego (monde)", linewidth=2)
sc = ax.scatter(px, py, c=tt, s=22, label=f"Ped {args.track_id or 'UNKNOWN'}", cmap="viridis")
for i in range(0, len(tt), max(1, args.step)):
    ax.plot([ex[i], px[i]], [ey[i], py[i]], alpha=0.25, linewidth=1)
ax.set_aspect("equal", adjustable="box"); ax.grid(True, alpha=0.3)
ax.set_xlabel("X monde [m] (East)"); ax.set_ylabel("Y monde [m] (North)")
ax.set_title(f"Trajectoire MONDE — boxes: {args.boxes}")
ax.legend(loc="best")
cb = plt.colorbar(sc, ax=ax); cb.set_label("index de frame (temps)")
fig.tight_layout(); fig.savefig("world_xy_true.png", dpi=150)

d = np.hypot(px-ex, py-ey)
fig2, ax2 = plt.subplots(figsize=(12,3))
ax2.plot(tt, d, linewidth=2); 
j = int(np.argmin(d)); ax2.axvline(tt[j], ls="--", alpha=0.5)
ax2.set_xlabel("index de frame"); ax2.set_ylabel("distance ego–piéton [m]")
ax2.set_title(f"distance min = {float(d[j]):.2f} m"); ax2.grid(True, alpha=0.3)
fig2.tight_layout(); fig2.savefig("distance_true.png", dpi=150)

print("[✓] Sauvé: world_xy_true.png, distance_true.png")
