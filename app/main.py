import os
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from .database import Base, engine, get_db
from .utils.logging import setup_logging
from . import models, crud
from .scanners.text_pii import scan_caption
from .scanners.exif_gps import scan_image_for_gps
from .scoring import score_from_detections
from fastapi.responses import FileResponse


# --- NEW TikTok imports ---
from .tiktok import models as tiktok_models   # register tables
from .tiktok.routers import router as tiktok_router

setup_logging()
Base.metadata.create_all(bind=engine)

app = FastAPI(title="RiskScan Phase 1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# include TikTok routes
app.include_router(tiktok_router)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/posts/scan")
async def scan_post(
    caption: str = Form(""),
    account_handle: str | None = Form(None),
    image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    acc = crud.ensure_account(db, account_handle)
    acc_id = acc.id if acc else None
    image_path = None
    if image:
        image_path = crud.save_image_to_disk("./uploads", image)
    dets = scan_caption(caption)
    gps = scan_image_for_gps(image_path) if image_path else None
    if gps:
        dets.append(("gps", f"{gps[0]:.6f},{gps[1]:.6f}"))
    post = crud.create_post(db, acc_id, caption, image_path)
    crud.add_detections(db, post.id, [(t, v) for t, v in dets if t != "gps"], gps)
    score, band, why = score_from_detections(dets)
    crud.add_score(db, post.id, score, band, why)
    crud.add_recommendations(db, post.id, band)
    return crud.get_post_bundle(db, post.id)

@app.get("/posts/{post_id}")
def get_post(post_id: int, db: Session = Depends(get_db)):
    bundle = crud.get_post_bundle(db, post_id)
    if not bundle:
        raise HTTPException(status_code=404, detail="Post not found")
    return bundle

@app.get("/tiktokVU7kUTuHmBNCRTt1Ys1J2fKbjXJi5v3v.txt")
def serve_tiktok_verification():
    file_path = os.path.join(os.path.dirname(__file__), "..", "tiktokVU7kUTuHmBNCRTt1Ys1J2fKbjXJi5v3v.txt")
    return FileResponse(file_path, media_type="text/plain")