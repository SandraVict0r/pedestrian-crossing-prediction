# -*- coding: utf-8 -*-
import argparse, sys, math
import numpy as np
import matplotlib.pyplot as plt
from collections import defaultdict
from pioneer.das.api.platform import Platform

CAND_ID_KEYS = ['track_id','tracking_id','id','uuid','uid','instance_id','object_id']

def ll_to_xy(lat, lon, lat0, lon0):
    R = 6371000.0
    lat  = np.asarray(lat, dtype=float);  lon  = np.asarray(lon, dtype=float)
    lat0 = float(lat0); lon0 = float(lon0)
    lat_r  = np.radians(lat);  lon_r  = np.radians(lon)
    lat0_r = np.radians(lat0); lon0_r = np.radians(lon0)
    x = R * (lon_r - lon0_r) * np.cos(0.5 * (lat_r + lat0_r))
    y = R * (lat_r - lat0_r)
    return x, y

def extract_track_ids(boxes3d):
    for m in ('get_track_ids','get_ids','track_ids','ids'):
        if hasattr(boxes3d, m):
            try:
                arr = getattr(boxes3d, m)()
                if arr is not None: return np.asarray(arr).astype(str)
            except Exception: pass
    for m in ('attributes','get_attributes'):
        if hasattr(boxes3d, m):
            try:
                attrs = getattr(boxes3d, m)()
                if isinstance(attrs, dict):
                    for k in CAND_ID_KEYS:
                        if k in attrs: return np.asarray(attrs[k]).astype(str)
            except Exception: pass
    return None

def first_ok(pf, names):
    for n in names:
        try:
            _ = pf[n]; return n
        except Exception: pass
    return None

def get_yaw_rad(raw_ekf):
    # essaie des clés usuelles
    for k in ('yaw','heading','course'):
        if k in raw_ekf:
            return math.radians(float(raw_ekf[k]))
    # sinon None -> on dérivera du déplacement ego
    return None

def main():
    ap = argparse.ArgumentParser(description="Trajectoire monde d'un piéton (2 méthodes)")
    ap.add_argument("run")
    ap.add_argument("--boxes", default="auto",
                    help="ex: pixell_bfc_box3d-deepen (auto essaie plusieurs variantes)")
    ap.add_argument("--track-id", default=None, help="ID du piéton (sinon plus longue piste)")
    ap.add_argument("--method", choices=["ego","transform"], default="ego",
                    help="ego: monde = ego + R(yaw)*center ; transform: compute_transform")
    ap.add_argument("--out", default="ped_world_v2.png")
    args = ap.parse_args()

    pf = Platform(args.run)

    # boxes auto
    boxes_name = args.boxes
    if boxes_name == "auto":
        CANDS = [
            "pixell_bfc_box3d-deepen","pixell_bfc_box3d_deepen",
            "pixell_bfc/box3d-deepen","pixell_bfc/box3d_deepen",
            "pixell_bfc_box3d","pixell_bfc/box3d"
        ]
        boxes_name = first_ok(pf, CANDS)
    if not boxes_name:
        print("[X] aucune datasource boxes trouvée, passe --boxes")
        sys.exit(1)

    # datasources pose
    pose_latlon = "sbgekinox_bcc_navposvel"
    pose_ekf    = "sbgekinox_bcc_ekfeuler"
    try: _ = pf[pose_latlon]; _ = pf[pose_ekf]
    except Exception as e:
        print(f"[X] pose manquante: {e}"); sys.exit(2)

    # sync
    sync = pf.synchronized(sync_labels=[boxes_name, pose_latlon, pose_ekf], tolerance_us=1e6)
    if len(sync) == 0:
        print("[X] sync vide"); sys.exit(3)

    # ancre monde
    ego0 = sync[0][pose_latlon].raw
    lat0, lon0 = float(ego0['latitude']), float(ego0['longitude'])

    ego_xy = []
    ego_yaw = []
    tracks = defaultdict(list)   # id -> [(x,y,tidx)]
    tcount_by_id = defaultdict(int)

    for i in range(len(sync)):
        fr = sync[i]
        # ego lat/lon -> XY
        raw_nav = fr[pose_latlon].raw
        ego_lat = float(raw_nav['latitude']); ego_lon = float(raw_nav['longitude'])
        ex, ey = ll_to_xy(ego_lat, ego_lon, lat0, lon0)
        ego_xy.append([ex, ey])

        # yaw
        yaw = get_yaw_rad(fr[pose_ekf].raw)
        ego_yaw.append(yaw)

        # boxes
        boxes = fr[boxes_name]
        try:
            cats = boxes.get_categories()
            centers = boxes.get_centers()
        except Exception:
            continue
        tids = extract_track_ids(boxes)
        if tids is None or len(tids) != len(cats):
            tids = np.array([None]*len(cats), dtype=object)

        for j, cat in enumerate(cats):
            if str(cat).lower() != "pedestrian": continue
            tid = str(tids[j])
            tcount_by_id[tid] += 1

            if args.method == "ego":
                # centre supposé en repère véhicule (x avant, y gauche)
                cx, cy = float(centers[j][0]), float(centers[j][1])
                yawj = yaw
                if yawj is None:
                    yawj = 0.0  # fallback, sera affiné après via dérivée
                # rotation + translation
                px = ex + math.cos(yawj)*cx - math.sin(yawj)*cy
                py = ey + math.sin(yawj)*cx + math.cos(yawj)*cy
            else:
                # méthode transform
                T = boxes.compute_transform(j)
                world_pos = boxes.transform_pts(T, np.array([centers[j]]))[0]  # [north,east,up] (m)
                dN, dE = float(world_pos[0]), float(world_pos[1])
                d_lat = dN / 111320.0
                d_lon = dE / (40075000.0 * math.cos(math.radians(ego_lat)) / 360.0)
                ped_lat = ego_lat + d_lat
                ped_lon = ego_lon + d_lon
                px, py = ll_to_xy(ped_lat, ped_lon, lat0, lon0)

            tracks[tid].append([px, py, i])

    ego_xy = np.asarray(ego_xy, float)

    # si yaw manquant: approx par dérivée de la trajectoire ego
    if any(y is None for y in ego_yaw):
        dx = np.gradient(ego_xy[:,0]); dy = np.gradient(ego_xy[:,1])
        ego_yaw = [math.atan2(dy[k], dx[k]) for k in range(len(dx))]

    # cible
    focus = args.track_id or (max(tcount_by_id, key=tcount_by_id.get) if tcount_by_id else None)
    if focus is None or focus not in tracks or len(tracks[focus]) < 2:
        print(f"[X] piste cible indisponible: {focus}"); sys.exit(4)

    ped = np.array(tracks[focus], float)  # cols: x,y,tidx
    # plot
    fig = plt.figure(figsize=(10,8)); ax = plt.gca()
    ax.set_aspect("equal"); ax.grid(True, alpha=0.3)
    ax.set_title(f"Trajectoire MONDE — ped id: {focus} — boxes: {boxes_name} — method: {args.method}")

    # ego
    ax.plot(ego_xy[:,0], ego_xy[:,1], label="Ego (monde)", alpha=0.5)

    # piéton, coloré par le temps
    c = ped[:,2]
    sc = ax.scatter(ped[:,0], ped[:,1], c=c, s=14)
    ax.plot(ped[:,0], ped[:,1], linewidth=2.5, label=f"Ped {focus}")

    cb = plt.colorbar(sc, ax=ax); cb.set_label("index de frame (temps)")

    ax.set_xlabel("X monde [m]"); ax.set_ylabel("Y monde [m]")
    ax.legend(loc="best")
    plt.tight_layout(); plt.savefig(args.out, dpi=160)
    print(f"[✓] sauvegardé: {args.out}")
    plt.show()

if __name__ == "__main__":
    main()
