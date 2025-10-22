import os
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, HTMLResponse
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .utils.logging import setup_logging
from . import models, crud
from .scanners.text_pii import scan_caption
from .scanners.exif_gps import scan_image_for_gps
from .scoring import score_from_detections
from .tiktok import models as tiktok_models   # ensure models registered
from .tiktok.routers import router as tiktok_router


# ---------- App setup ----------
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

# Include TikTok routes at /tiktok/...
app.include_router(tiktok_router)

# TikTok domain verification file (must exist at repo root)
VERIF_FILE = "tiktokVU7kUTuHmBNCRTt1Ys1J2fKbjXJi5v3v.txt"

# Simple homepage HTML we can reuse
HOME_HTML = """
<main style="font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial; 
             max-width: 720px; margin: 48px auto; line-height:1.55">
  <h1 style="margin:0 0 8px;">RiskScan</h1>
  <p style="margin:0 0 20px;color:#444">
    Scan your recent TikTok posts for privacy risks (Phase 1 pilot).
  </p>
  <p style="margin: 0 0 20px;">
    <a href="/tiktok/login"
       style="display:inline-block;padding:12px 16px;border-radius:10px;
              background:#000;color:#fff;text-decoration:none;">
      Login with TikTok
    </a>
  </p>
  <p style="margin: 0 0 10px;">Useful links:</p>
  <ul style="margin:0 0 24px;">
    <li><a href="/docs">/docs</a> (API)</li>
    <li><a href="/health">/health</a> (health check)</li>
    <li><a href="/privacy">/privacy</a> (privacy policy)</li>
    <li><a href="/terms">/terms</a> (terms of service)</li>
  </ul>
</main>
"""


# ---------- Public pages ----------
@app.get("/", response_class=HTMLResponse)
def home():
    # If this renders, the app is up and routing root correctly.
    return HOME_HTML


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get(f"/{VERIF_FILE}", response_class=PlainTextResponse)
def serve_tiktok_verification():
    # Serve the TikTok verification file from repo root (one level above app/)
    path = Path(__file__).resolve().parent.parent / VERIF_FILE
    return path.read_text(encoding="utf-8")


@app.get("/privacy", response_class=HTMLResponse)
def privacy():
    return """
    <h1>Privacy Policy</h1>
    <p>RiskScan analyzes TikTok captions and cover images to detect possible
    personal data exposure. We do not post to TikTok and we do not permanently
    store user media. Data is processed only to compute detections and risk scores.</p>
    """


@app.get("/terms", response_class=HTMLResponse)
def terms():
    return """
    <h1>Terms of Service</h1>
    <p>By using RiskScan, you authorize us to access your TikTok content for privacy
    analysis and agree results are informational only. We do not share or publish
    user data externally.</p>
    """


# ---------- Scan endpoints you already had ----------
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


# ---------- Friendly 404 fallback to help during demo ----------
# If any unknown path is hit (including "/"), show our homepage instead of raw JSON 404.
# This avoids the "detail: Not Found" screen in your demo.
@app.exception_handler(404)
async def not_found_to_home(_req: Request, _exc):
    return HTMLResponse(HOME_HTML, status_code=200)
