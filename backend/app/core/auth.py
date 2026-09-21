"""
Authentication abstraction: DevIdentity vs OIDC.
"""
from fastapi import Header, Depends, HTTPException
from typing import Optional
from ..config import settings, is_dev_auth_allowed
from ..db import SessionLocal
from ..models.user import User

def get_current_user_id(
    x_dev_user_id: Optional[str] = Header(None, alias="X-Dev-User-Id"),
    authorization: Optional[str] = Header(None)
) -> str:
    """
    Returns user_id.
    In dev mode, allow X-Dev-User-Id or default.
    In prod, require Bearer token (simplified OIDC validation placeholder).
    """
    # Dev mode
    if settings.DEV_AUTH_ENABLED:
        try:
            is_dev_auth_allowed()
        except RuntimeError as e:
            raise HTTPException(status_code=500, detail=str(e))

        if x_dev_user_id:
            return x_dev_user_id
        # Check Bearer token? In dev we also allow default
        return settings.DEV_DEFAULT_USER_ID

    # Production: require Bearer with OIDC validation
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = authorization.split(" ", 1)[1]
    if not token:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Attempt real OIDC validation if env vars set
    try:
        import os
        oidc_issuer = os.getenv("OIDC_ISSUER")
        oidc_audience = os.getenv("OIDC_AUDIENCE")
        if oidc_issuer and oidc_audience:
            # Real validation would use python-jose and fetch JWKS
            from jose import jwt
            try:
                payload = jwt.decode(token, settings.JWT_SECRET, audience=oidc_audience, issuer=oidc_issuer)
                user_id = payload.get("sub")
                if not user_id:
                    raise HTTPException(status_code=401, detail="Invalid token payload")
                return user_id
            except Exception as e:
                print(f"OIDC validation failed {e}, falling back to token as user_id for testing")
                if settings.ENV == "production":
                    raise HTTPException(status_code=401, detail=f"OIDC validation failed: {e}")
                return token
        else:
            if settings.ENV == "production":
                raise HTTPException(status_code=401, detail="OIDC not configured in production")
            return token
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Auth error: {e}")

def get_db_user(user_id: str = Depends(get_current_user_id)) -> User:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            # Auto-create in dev mode
            if settings.DEV_AUTH_ENABLED:
                user = User(id=user_id, email=f"dev-{user_id}@example.com", display_name="Dev User")
                db.add(user)
                db.commit()
                db.refresh(user)
            else:
                raise HTTPException(status_code=401, detail="User not found")
        return user
    finally:
        db.close()

def require_user(user: User = Depends(get_db_user)) -> User:
    return user
