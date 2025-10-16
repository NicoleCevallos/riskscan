import os
import re
import httpx
import base64
import hashlib
import secrets
import urllib.parse
from uuid import uuid4
from datetime import datetime, timedelta, timezone
from typing import Optional, Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..database import get_db
from .models import TikTokUser, TikTokVideo

# ---------- ENV & CONSTANTS ----------
TIKTOK_CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY", "xxx")
TIKTOK_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET", "xxx")
TIKTOK_REDIRECT_URI = os.getenv("TIKTOK_REDIRECT_URI", "http://localhost:8000/tiktok/callback")

TIKTOK_AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
TIKTOK_VIDEO_LIST = "https://open.tiktokapis.com/v2/video/list/"
REQUEST_SCOPES = ["user.info.basic", "video.list"]

router = APIRouter(prefix="/tiktok", tags=["tiktok"])

# ---------- PKCE helpers ----------
def _generate_pkce_pair() -> tuple[str, str]:
    """
    Returns (code_verifier, code_challenge) using S256 per RFC 7636.
    """
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode("utf-8")).digest()
    ).rstrip(b"=").decode("utf-8")
    return code_verifier, code_challenge

# In-memory cache for pilot. (For production, store per-session/user.)
PKCE_CACHE: dict[str, str] = {}   # state -> code_verifier

def _build_auth_url(state: str, code_challenge: str) -> str:
    scope_str = " ".join(REQUEST_SCOPES)
    return (
        f"{TIKTOK_AUTH_URL}"
        f"?client_key={urllib.parse.quote(TIKTOK_CLIENT_KEY)}"
        f"&response_type=code"
        f"&scope={urllib.parse.quote(scope_str)}"
        f"&redirect_uri={urllib.parse.quote(TIKTOK_REDIRECT_URI, safe='')}"
        f"&state={urllib.parse.quote(state)}"
        f"&code_challenge={urllib.parse.quote(code_challenge)}"
        f"&code_challenge_method=S256"
    )

# ---------- SCORING ----------
LOC_PAT = re.compile(r"\b(UNCC|Charlotte|CLT|Uptown|South End|NoDa|Plaza Midwood|📍|\d{3,5}\s+\w+)\b", re.I)
CONTACT_PAT = re.compile(r"(@\w+|\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b|\b\w+@\w+\.\w+\b)", re.I)
TIME_PAT = re.compile(r"\b(mon|tue|wed|thu|fri|sat|sun)\b.*\b(\d{1,2}(:\d{2})?\s?(am|pm))|\bevery\b|\btonight\b", re.I)
WORK_PAT = re.compile(r"\b(work|shift|on duty|campus job|host|bartend)\b", re.I)

def _score_caption(caption: Optional[str]) -> Dict[str, Any]:
    if not caption:
        return {"score": 0, "band": "low", "factors": {"caption_length": 0, "ocr_cover_text": None}, "detections": []}
    s = 0
    det: List[str] = []
    if LOC_PAT.search(caption): s += 40; det.append("possible_location")
    if CONTACT_PAT.search(caption): s += 25; det.append("contact_info")
    if TIME_PAT.search(caption): s += 20; det.append("schedule_time")
    if WORK_PAT.search(caption): s += 15; det.append("workplace")
    band = "low" if s < 20 else "medium" if s < 50 else "high"
    return {"score": s, "band": band, "factors": {"caption_length": len(caption), "ocr_cover_text": None}, "detections": det}

def _recs_from_detections(detections: List[str]) -> List[str]:
    r: List[str] = []
    if "possible_location" in detections or "schedule_time" in detections:
        r.append("Remove or generalize exact locations and schedules in captions.")
    if "contact_info" in detections:
        r.append("Remove phone, email, or @handles from public captions.")
    if detections:
        r.append("Tighten TikTok privacy settings for past posts (friends-only or private).")
    if not r:
        r.append("No issues detected. Keep captions generic and avoid contact/location details.")
    return r[:4]

# ---------- ROUTES ----------

@router.get("/login-url")
def login_url():
    """
    Helper endpoint for Swagger: returns the TikTok OAuth URL with PKCE.
    """
    state = str(uuid4())
    code_verifier, code_challenge = _generate_pkce_pair()
    PKCE_CACHE[state] = code_verifier
    return {"auth_url": _build_auth_url(state, code_challenge), "state": state}

@router.get("/login")
def login():
    """
    Browser-friendly redirect to TikTok OAuth with PKCE.
    """
    state = str(uuid4())
    code_verifier, code_challenge = _generate_pkce_pair()
    PKCE_CACHE[state] = code_verifier
    return RedirectResponse(_build_auth_url(state, code_challenge))

@router.get("/callback")
async def callback(code: str, state: Optional[str] = None, db: Session = Depends(get_db)):
    # Retrieve and clear the verifier (single-use)
    code_verifier = PKCE_CACHE.pop(state or "", None)
    if not code_verifier:
        raise HTTPException(400, "Missing PKCE verifier; start login again.")

    # Exchange code for token
    async with httpx.AsyncClient(timeout=30) as client:
        data = {
            "client_key": TIKTOK_CLIENT_KEY,
            "client_secret": TIKTOK_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": TIKTOK_REDIRECT_URI,
            "code_verifier": code_verifier,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        tok = await client.post(TIKTOK_TOKEN_URL, data=data, headers=headers)
        if tok.status_code != 200:
            raise HTTPException(tok.status_code, tok.text)
        tj = tok.json()["data"]
        access_token = tj["access_token"]
        refresh_token = tj.get("refresh_token")
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(tj["expires_in"]))

        # Get user info (open_id etc.)
        uinfo = await client.get(
            "https://open.tiktokapis.com/v2/user/info/",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"fields": "open_id,display_name,avatar_url"}
        )
        if uinfo.status_code != 200:
            raise HTTPException(uinfo.status_code, uinfo.text)
        user = uinfo.json()["data"]["user"]
        open_id = user["open_id"]

        rec = db.query(TikTokUser).filter_by(open_id=open_id).first()
        if not rec:
            rec = TikTokUser(
                open_id=open_id,
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=expires_at,
                display_name=user.get("display_name"),
                avatar_url=user.get("avatar_url"),
            )
            db.add(rec)
        else:
            rec.access_token = access_token
            rec.refresh_token = refresh_token
            rec.expires_at = expires_at
            rec.display_name = user.get("display_name") or rec.display_name
            rec.avatar_url = user.get("avatar_url") or rec.avatar_url
        db.commit()

        return {"ok": True, "open_id": open_id, "expires_at": expires_at.isoformat()}

@router.post("/video-list")
async def ingest(limit: int = Query(25, ge=1, le=100), db: Session = Depends(get_db)):
    user = db.query(TikTokUser).order_by(TikTokUser.id.desc()).first()
    if not user:
        raise HTTPException(400, "No TikTok user connected. Use /tiktok/login first.")

    async with httpx.AsyncClient(timeout=30) as client:
        headers = {"Authorization": f"Bearer {user.access_token}", "Content-Type": "application/json"}
        r = await client.post(TIKTOK_VIDEO_LIST, json={"max_count": limit}, headers=headers)
        if r.status_code != 200:
            raise HTTPException(r.status_code, r.text)
        data = r.json().get("data", {})
        vids = data.get("videos", [])
        cnt = 0
        for v in vids:
            vid = v.get("id")
            if db.query(TikTokVideo).filter_by(video_id=vid).first():
                continue
            caption = v.get("video_description") or v.get("title")
            cover = v.get("cover_image_url")
            create_time = v.get("create_time")
            share = v.get("share_url")

            scored = _score_caption(caption or "")
            dets = scored["detections"]
            recs = _recs_from_detections(dets)

            row = TikTokVideo(
                user_id=user.id,
                video_id=vid,
                caption=caption,
                cover_image_url=cover,
                create_time_utc=datetime.fromtimestamp(create_time, tz=timezone.utc) if create_time else None,
                share_url=share,
                scanned_at=datetime.now(timezone.utc),
                score=scored["score"],
                band=scored["band"],
                factors=scored["factors"],
                detections=dets,
                recs=recs,
            )
            db.add(row); cnt += 1
        db.commit()
        return {"ingested": cnt}

@router.get("/posts")
def list_posts(page: int = 1, page_size: int = 10, db: Session = Depends(get_db)):
    q = db.query(TikTokVideo).order_by(TikTokVideo.create_time_utc.desc().nullslast())
    total = q.count()
    rows = q.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [{
            "video_id": r.video_id,
            "caption": r.caption,
            "cover_image_url": r.cover_image_url,
            "create_time_utc": r.create_time_utc,
            "share_url": r.share_url,
            "score": r.score,
            "band": r.band
        } for r in rows],
        "page": page, "page_size": page_size, "total": total
    }

@router.get("/posts/{video_id}")
def get_post(video_id: str, db: Session = Depends(get_db)):
    r = db.query(TikTokVideo).filter_by(video_id=video_id).first()
    if not r:
        raise HTTPException(404, "Video not found")
    return {
        "video_id": r.video_id,
        "caption": r.caption,
        "cover_image_url": r.cover_image_url,
        "create_time_utc": r.create_time_utc,
        "share_url": r.share_url,
        "score": r.score,
        "band": r.band,
        "detections": r.detections or [],
        "factors": r.factors or {},
        "recs": r.recs or [],
    }
