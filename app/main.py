import os
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, HTMLResponse
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .utils.logging import setup_logging
from . import models, crud
from .scanners.text_pii import scan_caption
from .scanners.exif_gps import scan_image_for_gps
from .scoring import score_from_detections
from .tiktok import models as tiktok_models   # register tables
from .tiktok.routers import router as tiktok_router


# --- Setup ---
setup_logging()
Base.metadata.create_all(bind=engine)

app = FastAPI(title="RiskScan Phase 1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"],
)

# --- Include TikTok Routes ---
app.include_router(tiktok_router)

# --- Constants ---
VERIF_FILE = "tiktokVU7kUTuHmBNCRTt1Ys1J2fKbjXJi5v3v.txt"  # TikTok verification filename


# --- Homepage ---
@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <main style="font-family: system-ui; max-width: 720px; margin: 48px auto; line-height:1.5">
      <h1>RiskScan</h1>
      <p>Scan your recent TikTok posts for privacy risks (Phase 1 pilot).</p>
      <p>
        <a href="/tiktok/login"
           style="display:inline-block;padding:12px 16px;border-radius:10px;
                  background:#000;color:#fff;text-decoration:none;">
          Login with TikTok
        </a>
      </p>
      <p>API docs: <a href="/docs">/docs</a> • Health: <a href="/health">/health</a></p>
    </main>
    """


# --- Health Check ---
@app.get("/health")
def health():
    return {"status": "ok"}


# --- TikTok Verification File ---
@app.get(f"/{VERIF_FILE}", response_class=PlainTextResponse)
def serve_tiktok_verification():
    p = Path(__file__).resolve().parent.parent / VERIF_FILE
    return p.read_text(encoding="utf-8")


# --- Privacy Policy ---
@app.get("/privacy", response_class=HTMLResponse)
def privacy():
    return """
    <h1>Privacy Policy</h1>
    <p>RiskScan analyzes TikTok captions and images to detect possible
    personal data exposure. We do not post content to TikTok, and we do not
    permanently store any media. Data is processed only to compute detections
    and risk scores.</p>
    """


# --- Terms of Service ---
@app.get("/terms", response_class=HTMLResponse)
def terms():
    return """
    <h1>Terms of Service</h1>
    <p>By using RiskScan, you authorize us to access your TikTok content
    for privacy analysis and agree that results are informational only.
    We do not share or publish any user data externally.</p>
    """


# --- Post Scanning Endpoint ---
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


# --- Get Post Details ---
@app.get("/posts/{post_id}")
def get_post(post_id: int, db: Session = Depends(get_db)):
    bundle = crud.get_post_bundle(db, post_id)
    if not bundle:
        raise HTTPException(status_code=404, detail="Post not found")
    return bundle
