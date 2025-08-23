from fastapi import APIRouter, Request, Response, HTTPException
from app.core.config import settings
import time
import jwt
import uuid

router = APIRouter()


def _issue_visitor_token(sub: str | None = None) -> str:
    now = int(time.time())
    exp = now + settings.VISITOR_JWT_TTL_DAYS * 86400
    payload = {
        "iss": settings.VISITOR_JWT_ISSUER,
        "aud": settings.VISITOR_JWT_AUDIENCE,
        "iat": now,
        "nbf": now,
        "exp": exp,
        "sub": sub or str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.VISITOR_JWT_SECRET, algorithm="HS256")


@router.get("/visitor/token")
def get_visitor_token(request: Request):
    # If a valid token is already present, return it; otherwise issue a new one
    token = request.cookies.get("visitor_token") or request.headers.get("X-Visitor-Token")
    if token:
        try:
            jwt.decode(
                token,
                settings.VISITOR_JWT_SECRET,
                algorithms=["HS256"],
                audience=settings.VISITOR_JWT_AUDIENCE,
                issuer=settings.VISITOR_JWT_ISSUER,
                options={"verify_exp": True},
            )
            return {"token": token}
        except Exception:
            pass
    new_token = _issue_visitor_token()
    resp = Response(content=f"{{\"token\": \"{new_token}\"}}", media_type="application/json")
    # 30 days ~ 2592000 seconds
    resp.set_cookie(
        key="visitor_token",
        value=new_token,
        max_age=settings.VISITOR_JWT_TTL_DAYS * 86400,
        expires=settings.VISITOR_JWT_TTL_DAYS * 86400,
        path="/",
        secure=True,
        httponly=False,
        samesite="None",
    )
    return resp


@router.get("/visitor/pixel")
def visitor_pixel(request: Request):
    # Tiny 1x1 transparent PNG
    token = request.cookies.get("visitor_token") or request.headers.get("X-Visitor-Token")
    vid = None
    if token:
        try:
            payload = jwt.decode(
                token,
                settings.VISITOR_JWT_SECRET,
                algorithms=["HS256"],
                audience=settings.VISITOR_JWT_AUDIENCE,
                issuer=settings.VISITOR_JWT_ISSUER,
                options={"verify_exp": True},
            )
            vid = payload.get("sub")
        except Exception:
            vid = None

    # Minimal logging via application logger
    import logging
    logging.getLogger("visitor").info("visitor_pixel", extra={"visitor_id": vid})

    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\x0cIDAT\x08\x99c\x60\x00\x00\x00\x02\x00\x01E\xdd\x85\xb1\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    headers = {"Cache-Control": "no-store, max-age=0"}
    return Response(content=png_bytes, media_type="image/png", headers=headers)


@router.head("/visitor/pixel")
def visitor_pixel_head():
    # Allow HEAD requests to succeed for monitoring and curl -I
    return Response(status_code=200)


