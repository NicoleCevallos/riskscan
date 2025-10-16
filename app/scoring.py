from typing import List, Tuple
WEIGHTS = {"email":20.0, "phone":20.0, "address":30.0, "gps":40.0}
def score_from_detections(dets: List[Tuple[str, str]]) -> tuple[float, str, list[str]]:
    total = 0.0; whys: list[str] = []; counts = {"email":0,"phone":0,"address":0,"gps":0}
    for d_type, _ in dets:
        counts[d_type] = counts.get(d_type, 0) + 1
    for k, c in counts.items():
        if c>0:
            add = WEIGHTS.get(k, 0.0) * min(c, 3)
            total += add; whys.append(f"{k.upper()} detected x{c} (+{add:.0f})")
    band = "LOW"
    if total >= 60: band = "MEDIUM"
    if total >= 90: band = "HIGH"
    return total, band, whys
