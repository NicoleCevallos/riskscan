import os, uuid
from typing import List, Tuple
from sqlalchemy.orm import Session
from . import models

def ensure_account(db: Session, handle: str | None):
    if not handle: return None
    acc = db.query(models.Account).filter(models.Account.handle==handle).first()
    if not acc:
        acc = models.Account(handle=handle, platform="local")
        db.add(acc); db.commit(); db.refresh(acc)
    return acc

def save_image_to_disk(upload_dir: str, file) -> str:
    os.makedirs(upload_dir, exist_ok=True)
    ext = (file.filename or "image").split(".")[-1]
    name = f"{uuid.uuid4().hex}.{ext}"
    path = os.path.join(upload_dir, name)
    with open(path, "wb") as f:
        f.write(file.file.read())
    return path

def create_post(db: Session, account_id, caption: str, image_path: str | None):
    p = models.Post(account_id=account_id, caption=caption or "", image_path=image_path)
    db.add(p); db.commit(); db.refresh(p)
    return p

def add_detections(db: Session, post_id: int, dets: List[Tuple[str,str]], gps: tuple[float,float] | None):
    rows = []
    for d_type, value in dets:
        rows.append(models.Detection(post_id=post_id, detector=d_type, value=value))
    if gps:
        rows.append(models.Detection(post_id=post_id, detector="gps", value=f"{gps[0]:.6f},{gps[1]:.6f}"))
    db.add_all(rows); db.commit()
    return rows

def add_score(db: Session, post_id: int, score: float, band: str, why: list[str]):
    rs = models.RiskScore(post_id=post_id, score=score, band=band, why="|".join(why))
    db.add(rs); db.commit(); db.refresh(rs)
    return rs

def add_recommendations(db: Session, post_id: int, band: str):
    recs = []
    if band == "LOW":
        recs.append("Looks safe. Double-check caption for sensitive context.")
    elif band == "MEDIUM":
        recs.append("Remove contact details from caption (email/phone).")
    else:
        recs.append("Strip EXIF data and remove address/contacts before posting.")
    rows = [models.Recommendation(post_id=post_id, text=t) for t in recs]
    db.add_all(rows); db.commit()
    return rows

def get_post_bundle(db: Session, post_id: int):
    p = db.query(models.Post).get(post_id)
    if not p: return None
    dets = [{"detector":d.detector, "value":d.value, "extra":d.extra} for d in p.detections]
    rs = p.risk_score[0] if p.risk_score else None
    recs = [{"text":r.text} for r in p.recommendations]
    risk = {"score": rs.score, "band": rs.band, "why": rs.why.split("|")} if rs else {"score":0,"band":"LOW","why":[]}
    return {"id": p.id, "caption": p.caption, "image_path": p.image_path, "detections": dets, "risk": risk, "recommendations": recs}
