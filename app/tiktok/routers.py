# app/tiktok/routers.py
import base64
import hashlib
import os
import time
import secrets
from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, JSONResponse

router = APIRouter(prefix="/tiktok", tags=["tiktok"])

# ---- Env ----
TT_CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY", "")
TT_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET", "")
TT_REDIRECT_URI = os.getenv("TIKTOK_REDIRECT_URI", "")
TT_SCOPES = "user.info.basic,video.list"

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
VIDEO_LIST_URL = "https://open.tiktokapis.com/v2/video/list/"

# state -> (code_verifier, created_at)
PKCE_STORE: dict[str, tuple[str, float]] = {}


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _make_pkce() -> tuple[str, str]:
    verifier = _b64url(secrets.token_urlsafe(64).encode())[:128]
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge


def _bad(v: str) -> bool:
    # missing or looks like a placeholder
    if not v:
        return True
    vv = v.strip().lower()
    return vv.startswith("<") and vv.endswith(">")


def _require_env():
    if _bad(TT_CLIENT_KEY):
        raise HTTPException(
            status_code=500,
            detail="TIKTOK_CLIENT_KEY missing/placeholder. Set real Client Key in Railway Variables.",
        )
    if _bad(TT_CLIENT_SECRET):
        raise HTTPException(
            status_code=500,
            detail="TIKTOK_CLIENT_SECRET missing/placeholder. Set real Client Secret in Railway Variables.",
        )
    if _bad(TT_REDIRECT_URI):
        raise HTTPException(
            status_code=500,
            detail="TIKTOK_REDIRECT_URI missing/placeholder. Must match TikTok Login Kit exactly.",
        )


@router.get("/debug")
async def debug():
    """Simple diagnostics to verify server-side config (masked/safe)."""
    return {
        "client_key_set": bool(TT_CLIENT_KEY) and not _bad(TT_CLIENT_KEY),
        "redirect_uri": TT_REDIRECT_URI,
        "scopes": TT_SCOPES,
    }


@router.get("/login")
async def login():
    _require_env()
    verifier, challenge = _make_pkce()
    state = secrets.token_urlsafe(24)
    PKCE_STORE[state] = (verifier, time.time())

    params = {
        "client_key": TT_CLIENT_KEY,
        "scope": TT_SCOPES,
        "response_type": "code",
        "redirect_uri": TT_REDIRECT_URI,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return RedirectResponse(f"{AUTH_URL}?{urlencode(params)}")


@router.get("/callback")
async def callback(code: Optional[str] = None, state: Optional[str] = None):
    _require_env()
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")

    slot = PKCE_STORE.pop(state, None)
    if not slot or time.time() - slot[1] > 600:
        raise HTTPException(status_code=400, detail="Invalid/expired state")

    code_verifier = slot[0]
    form = {
        "client_key": TT_CLIENT_KEY,
        "client_secret": TT_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": TT_REDIRECT_URI,
        "code_verifier": code_verifier,
    }

    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            TOKEN_URL,
            data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Token exchange failed: {r.text}")
        tok = r.json()

    resp = JSONResponse(
        {
            "ok": True,
            "open_id": tok.get("open_id"),
            "expires_in": tok.get("expires_in"),
            "scopes": TT_SCOPES.split(","),
        }
    )
    if "access_token" in tok:
        resp.set_cookie(
            "tt_access_token",
            tok["access_token"],
            httponly=True,
            secure=True,
            samesite="Lax",
            max_age=tok.get("expires_in", 600),
        )
    if "open_id" in tok:
        resp.set_cookie(
            "tt_open_id",
            tok["open_id"],
            httponly=True,
            secure=True,
            samesite="Lax",
            max_age=tok.get("expires_in", 600),
        )
    return resp


@router.post("/video-list")
async def video_list(request: Request, limit: int = 25):
    token = request.cookies.get("tt_access_token")
    open_id = request.cookies.get("tt_open_id")
    if not token or not open_id:
        raise HTTPException(status_code=401, detail="Not logged in with TikTok")

    params = {
        "open_id": open_id,
        "max_count": max(1, min(limit, 50)),
        "fields": "video_id,caption,create_time,cover_image_url",
    }

    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(
            VIDEO_LIST_URL,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f"TikTok video.list failed: {r.text}")
        return {"ok": True, "data": r.json()}
