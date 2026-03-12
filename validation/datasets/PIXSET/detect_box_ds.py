#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, sys, glob, re
from zipfile import ZipFile, BadZipFile
from pioneer.das.api.platform import Platform

BOX_HINTS = ("box3d", "bbox3d", "boxes_3d", "box_3d", "box2d", "bbox2d", "detections", "labels")

def _try_key(pf, sensor, ds_type):
    """Essaie pf['sensor_ds'] avec '_' ou '/'."""
    for sep in ("_", "/"):
        k = f"{sensor}{sep}{ds_type}"
        try:
            # accéder déclenche la vérification d'existence
            _ = pf[k]
            return k
        except Exception:
            pass
    return None

def detect_boxes_key(run):
    pf = Platform(run)
    sensors = list(pf.sensors.keys())

    # 1) Scanner tous les .zip pour repérer sensor + type
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
                        # fallback si "pixell" mais capteur non détecté
                        if sensor is None and "pixell" in ln:
                            for s in sensors:
                                if s.lower().startswith("pixell"):
                                    sensor = s
                                    break
                        if sensor is None:
                            continue
                        # ds_type
                        if "box3d" in ln or "boxes_3d" in ln or "box_3d" in ln or "bbox3d" in ln:
                            ds_type = "box3d_deepen" if ("deepen" in ln) else "box3d"
                        elif "box2d" in ln or "bbox2d" in ln:
                            ds_type = "box2d"
                        elif "detections" in ln:
                            ds_type = "detections"
                        else:
                            ds_type = "labels"
                        found_pairs.add((sensor, ds_type))
        except BadZipFile:
            continue
        except Exception:
            continue

    # 2) Tester les clés candidates
    good = []
    for sensor, ds_type in sorted(found_pairs):
        k = _try_key(pf, sensor, ds_type)
        if k:
            good.append(k)

    # 3) Brute force (au cas où)
    if not good:
        for s in sensors:
            for ds_type in ("box3d_deepen", "box3d", "box2d", "detections", "labels"):
                k = _try_key(pf, s, ds_type)
                if k:
                    good.append(k)

    if not good:
        return None, pf

    # Priorité: deepen > box3d > box2d > detections > labels
    def prio(k):
        kl = k.lower()
        if "box3d_deepen" in kl: return 0
        if "box3d"        in kl: return 1
        if "box2d"        in kl: return 2
        if "detections"   in kl: return 3
        return 4
    good.sort(key=prio)
    return good[0], pf

def main():
    if len(sys.argv) < 2:
        print("Usage: python detect_box_ds.py <RUN_PATH>")
        sys.exit(2)
    run = sys.argv[1]
    key, _ = detect_boxes_key(run)
    if not key:
        print("[X] Aucune datasource 'box*' trouvée. Ouvre le run dans dasview et note le nom du layer.")
        sys.exit(1)
    print(key)

if __name__ == "__main__":
    main()
