#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Visualiser trajectoires monde (ego + piétons) à partir d’un run PIXSET/DAS.

Usage simple (auto-détecte la datasource des boxes) :
    python viz_ped_world.py "<CHEMIN_RUN>"

Avec track ID ciblé :
    python viz_ped_world.py "<CHEMIN_RUN>" --track-id 123

Forcer la datasource des boxes :
    python viz_ped_world.py "<CHEMIN_RUN>" --boxes pixell_bfc_box3d_deepen

Afficher toutes les classes (pas seulement les piétons) :
    python viz_ped_world.py "<CHEMIN_RUN>" --keep-all-labels
"""

import argparse
import math
import sys
from collections import defaultdict
import os, glob
from zipfile import ZipFile

import numpy as np
import matplotlib.pyplot as plt

from pioneer.das.api.platform import Platform

# --- helpers géo ---
try:
    import utm  # installé avec pioneer-common
except Exception:
    utm = None

def _deg2rad(v):
    return v * math.pi / 180.0

def _is_deg(v):
    return abs(v) > math.pi * 2.0

# --- détection datasource boxes (intégré ici pour être autonome) ---
BOX_HINTS = ("box3d", "bbox3d", "boxes_3d", "box_3d", "box2d", "bbox2d", "detections", "labels")

def detect_boxes_key(pf, run):
    sensors = list(pf.sensors.keys())
    zips = glob.glob(os.path.join(run, "**", "*.zip"), recursive=True)
    found_pairs = set()
    for z in zips:
        try:
            with ZipFile(z) as f:
                for n in f.namelist():
                    ln = n.lower()
                    if any(h in ln for h in BOX_HINTS):
                        sensor = None
                        for s in sensors:
                            if s.lower() in ln:
                                sensor = s
                                break
                        if sensor is None and "pixell" in ln:
                            for s in sensors:
                                if s.lower().startswith("pixell"):
                                    sensor = s
                                    break
                        if sensor is None:
                            continue
                        if "box3d" in ln or "boxes_3d" in ln or "box_3d" in ln or "bbox3d" in ln:
                            ds_type = "box3d_deepen" if ("deepen" in ln) else "box3d"
                        elif "box2d" in ln or "bbox2d" in ln:
                            ds_type = "box2d"
                        elif "detections" in ln:
                            ds_type = "detections"
                        else:
                            ds_type = "labels"
                        found_pairs.add((sensor, ds_type))
        except Exception:
            continue

    def try_key(sensor, ds_type):
        for sep in ("_", "/"):
            k = f"{sensor}{sep}{ds_type}"
            try:
                _ = pf[k]
                return k
            except Exception:
                pass
        return None

    good = []
    for s, t in sorted(found_pairs):
        k = try_key(s, t)
        if k:
            good.append(k)

    if not good:
        for s in sensors:
            for t in ("box3d_deepen", "box3d", "box2d", "detections", "labels"):
                k = try_key(s, t)
                if k:
                    good.append(k)

    if not good:
        return None

    def prio(k):
        kl = k.lower()
        if "box3d_deepen" in kl: return 0
        if "box3d"        in kl: return 1
        if "box2d"        in kl: return 2
        if "detections"   in kl: return 3
        return 4
    good.sort(key=prio)
    return good[0]

# --- pose depuis sbgekinox (navposvel + ekfeuler) ---
def find_nav_euler_keys(pf):
    sensors = list(pf.sensors.keys())
    nav = eul = None
    for s in sensors:
        for sep in ("_", "/"):
            k1 = f"{s}{sep}navposvel"
            k2 = f"{s}{sep}ekfeuler"
            try:
                _ = pf[k1]; nav = k1
            except Exception:
                pass
            try:
                _ = pf[k2]; eul = k2
            except Exception:
                pass
    return nav, eul

def get_ts_array(ds):
    """Renvoie une liste de timestamps si dispo, sinon None."""
    for attr in ("timestamps", "time_stamps", "ts"):
        if hasattr(ds, attr):
            try:
                a = getattr(ds, attr)
                return np.asarray(a, dtype=np.int64)
            except Exception:
                pass
    # parfois accessible via ds.datasource
    if hasattr(ds, "datasource"):
        for attr in ("timestamps", "time_stamps", "ts"):
            if hasattr(ds.datasource, attr):
                try:
                    a = getattr(ds.datasource, attr)
                    return np.asarray(a, dtype=np.int64)
                except Exception:
                    pass
    return None

def extract_sample_ts(smp, fallback_t=None):
    for attr in ("timestamp", "time", "ts"):
        if hasattr(smp, attr):
            try:
                return int(getattr(smp, attr))
            except Exception:
                pass
    if isinstance(smp, dict):
        for k in ("timestamp", "time", "ts"):
            if k in smp:
                try:
                    return int(smp[k])
                except Exception:
                    pass
    return int(fallback_t) if fallback_t is not None else None

def mercator_xy(lat, lon, lat0=None, lon0=None):
    """Projete (lat,lon) -> (x,y) en mètres (approx locale)."""
    if utm:
        e, n, *_ = utm.from_latlon(lat, lon)
        if lat0 is None or lon0 is None:
            e0, n0, *_ = utm.from_latlon(lat, lon)
        else:
            e0, n0, *_ = utm.from_latlon(lat0, lon0)
        return e - e0, n - n0

    # fallback simple (équirectangulaire locale)
    R = 6378137.0
    if lat0 is None: lat0 = lat
    if lon0 is None: lon0 = lon
    x = _deg2rad(lon - lon0) * R * math.cos(_deg2rad((lat + lat0) * 0.5))
    y = _deg2rad(lat - lat0) * R
    return x, y

def yaw_from_fields(obj, euler_obj=None):
    """Essaie de sortir yaw (rad) depuis navposvel / ekfeuler."""
    # navposvel : heading / course (souvent degrés)
    for name in ("heading", "course", "trk", "cog", "yaw_deg", "yaw"):
        v = getattr(obj, name, None)
        if v is None and isinstance(obj, dict):
            v = obj.get(name)
        if v is not None:
            v = float(v)
            return _deg2rad(v) if _is_deg(v) else v

    # ekfeuler : yaw, psi (souvent rad)
    if euler_obj is not None:
        for name in ("yaw", "psi", "heading", "yaw_deg"):
            v = getattr(euler_obj, name, None)
            if v is None and isinstance(euler_obj, dict):
                v = euler_obj.get(name)
            if v is not None:
                v = float(v)
                return _deg2rad(v) if _is_deg(v) else v

    return 0.0

def extract_boxes(sample):
    """
    Renvoie une liste de dicts : {track_id, label, center(np.array([x,y,z]))}
    """
    def norm_list(lst):
        out=[]
        for o in lst:
            if isinstance(o, dict):
                tid = o.get("track_id", o.get("id"))
                lab = (o.get("label") or o.get("class"))
                ctr = o.get("center")
                if ctr is None:
                    xs = [k for k in o.keys() if str(k).lower() in ("x","cx")]
                    ys = [k for k in o.keys() if str(k).lower() in ("y","cy")]
                    zs = [k for k in o.keys() if str(k).lower() in ("z","cz")]
                    if xs and ys:
                        ctr = [o[xs[0]], o[ys[0]], (o[zs[0]] if zs else 0.0)]
                if ctr is not None:
                    c = np.asarray(ctr, dtype=float).reshape(-1)
                    if c.size>=2:
                        out.append({"track_id": (int(tid) if tid is not None else None),
                                    "label": (str(lab).lower() if lab is not None else None),
                                    "center": c})
            else:
                # objets avec attributs
                try:
                    tid = getattr(o, "track_id", getattr(o, "id", None))
                    lab = getattr(o, "label", getattr(o, "clazz", None))
                    ctr = getattr(o, "center", None)
                    if ctr is None and hasattr(o, "x") and hasattr(o, "y"):
                        ctr = [float(o.x), float(o.y), float(getattr(o, "z", 0.0))]
                    if ctr is not None:
                        c = np.asarray(ctr, dtype=float).reshape(-1)
                        if c.size>=2:
                            out.append({"track_id": (int(tid) if tid is not None else None),
                                        "label": (str(lab).lower() if lab is not None else None),
                                        "center": c})
                except Exception:
                    pass
        return out

    if isinstance(sample, dict):
        for k in ("objects","boxes","detections"):
            if k in sample and isinstance(sample[k], (list,tuple)):
                return norm_list(sample[k])

    for k in ("objects","boxes","detections","instances"):
        if hasattr(sample, k):
            return norm_list(getattr(sample, k))

    # pandas DataFrame ?
    try:
        import pandas as pd
        for k in ("df","dataframe","data"):
            if hasattr(sample, k):
                val = getattr(sample, k)
                if isinstance(val, pd.DataFrame):
                    cols = [c.lower() for c in val.columns]
                    def col(name):
                        for c in val.columns:
                            if c.lower().startswith(name): return c
                        return None
                    cx, cy, cz = col("x"), col("y"), col("z")
                    lab = col("label") or col("class")
                    tid = col("track") or col("id") or col("track_id")
                    out=[]
                    if cx and cy:
                        for _, r in val.iterrows():
                            c = np.array([r[cx], r[cy], (r[cz] if cz else 0.0)], dtype=float)
                            out.append({"track_id": (int(r[tid]) if tid and not pd.isna(r[tid]) else None),
                                        "label": (str(r[lab]).lower() if lab else None),
                                        "center": c})
                    return out
    except Exception:
        pass

    raise RuntimeError("Impossible d'extraire les boxes du sample.")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset", help="Chemin du run (dossier avec platform.yml).")
    ap.add_argument("--boxes", default=None, help="Nom exact de la datasource des boxes (ex: pixell_bfc_box3d_deepen).")
    ap.add_argument("--track-id", type=int, default=None, help="Track ID à mettre en avant.")
    ap.add_argument("--keep-all-labels", action="store_true", help="Ne pas filtrer aux piétons, tracer toutes les classes.")
    ap.add_argument("--max-frames", type=int, default=20000, help="Limiter le nombre de frames lues.")
    args = ap.parse_args()

    print(f"[i] Ouverture dataset: {args.dataset}")
    pf = Platform(args.dataset)

    boxes_key = args.boxes or detect_boxes_key(pf, args.dataset)
    if not boxes_key:
        print("[!] Aucune datasource 'box*' trouvée automatiquement.\n"
              "    Ouvre le run dans dasview et note le nom exact, puis relance avec --boxes <nom>.")
        sys.exit(1)
    print(f"[i] Boxes datasource: {boxes_key}")

    try:
        ds_boxes = pf[boxes_key]
    except Exception as e:
        print(f"[X] Impossible d'ouvrir {boxes_key}: {e}")
        sys.exit(2)

    # Pose : navposvel pour (lat,lon), ekfeuler pour yaw si besoin
    nav_key, eul_key = find_nav_euler_keys(pf)
    if not nav_key:
        print("[X] Datasource 'navposvel' introuvable → pose monde non disponible.")
        sys.exit(3)
    ds_nav = pf[nav_key]
    ds_eul = pf[eul_key] if eul_key else None
    print(f"[i] Pose (navposvel): {nav_key}" + (f"  | euler: {eul_key}" if eul_key else ""))

    ts_boxes = get_ts_array(ds_boxes)
    use_index_loop = False
    if ts_boxes is None or len(ts_boxes) == 0:
        use_index_loop = True
        print("[!] Impossible de lire les timestamps des boxes → parcours par index (max-frames).")

    # Accumulateurs
    ego_xy = []
    ped_tracks = defaultdict(list)
    ped_label_keys = {"ped", "pedestrian", "person", "piéton", "pieton"}

    # origine géo pour (x,y) en m
    origin_lat = origin_lon = None

    def get_nav_at(t=None, i=None):
        """Retourne (lat,lon,yaw_rad,timestamp) à t (si dispo) sinon index i."""
        smp_nav = None
        if t is not None:
            try:
                smp_nav = ds_nav.get_at_timestamp(int(t))
            except Exception:
                smp_nav = None
        if smp_nav is None:
            # fallback index
            try:
                smp_nav = ds_nav[i]
            except Exception:
                return None

        # extraire lat/lon
        lat = getattr(smp_nav, "lat", getattr(smp_nav, "latitude", None))
        lon = getattr(smp_nav, "lon", getattr(smp_nav, "longitude", None))
        if lat is None and isinstance(smp_nav, dict):
            lat = smp_nav.get("lat", smp_nav.get("latitude"))
            lon = smp_nav.get("lon", smp_nav.get("longitude"))
        if lat is None or lon is None:
            return None

        # yaw via navposvel (heading/course) et/ou ekfeuler
        smp_e = None
        if ds_eul is not None:
            try:
                smp_e = ds_eul.get_at_timestamp(int(extract_sample_ts(smp_nav)))
            except Exception:
                try:
                    smp_e = ds_eul[i]
                except Exception:
                    smp_e = None
        yaw = yaw_from_fields(smp_nav, smp_e)
        return float(lat), float(lon), float(yaw), extract_sample_ts(smp_nav)

    # boucle
    nread = 0
    imax = args.max_frames if use_index_loop else min(len(ts_boxes), args.max_frames)
    for i in range(imax):
        if use_index_loop:
            try:
                smp_box = ds_boxes[i]
            except Exception:
                break
            tbox = extract_sample_ts(smp_box)
        else:
            tbox = int(ts_boxes[i])
            try:
                smp_box = ds_boxes[i]
            except Exception:
                try:
                    smp_box = ds_boxes.get_at_timestamp(tbox)
                except Exception:
                    continue

        nav = get_nav_at(t=tbox, i=i)
        if nav is None:
            continue
        lat, lon, yaw, tnav = nav
        if origin_lat is None:
            origin_lat, origin_lon = lat, lon
        ex, ey = mercator_xy(lat, lon, origin_lat, origin_lon)
        ego_xy.append([ex, ey])

        # boxes → piétons → monde
        try:
            boxes = extract_boxes(smp_box)
        except Exception:
            continue

        for b in boxes:
            lab = (b.get("label") or "").lower()
            if not args.keep_all_labels:
                if lab and all(k not in lab for k in ped_label_keys):
                    continue  # pas un piéton
            tid = b.get("track_id")
            ctr = b["center"].astype(float)
            x_rel, y_rel = float(ctr[0])
