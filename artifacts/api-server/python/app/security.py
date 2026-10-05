from datetime import UTC, datetime
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.config import ACCESS_TOKEN_TTL, jwt_secret
from app.database import get_db
from app.models import User

password_hash = PasswordHash.recommended()
bearer_scheme = HTTPBearer(auto_error=False)
JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return password_hash.verify(password, encoded)
    except Exception:
        return False


def create_access_token(user_id: UUID) -> tuple[str, int]:
    expires_in = int(ACCESS_TOKEN_TTL.total_seconds())
    expires_at = datetime.now(UTC).timestamp() + expires_in
    token = jwt.encode(
        {"sub": str(user_id), "exp": int(expires_at), "iat": int(datetime.now(UTC).timestamp())},
        jwt_secret(),
        algorithm=JWT_ALGORITHM,
    )
    return token, expires_in


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication is required.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        payload = jwt.decode(credentials.credentials, jwt_secret(), algorithms=[JWT_ALGORITHM])
        user_id = UUID(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise unauthorized
    user = db.get(User, user_id)
    if user is None:
        raise unauthorized
    return user


def require_staff(user: User = Depends(get_current_user)) -> User:
    if user.role not in {"support_engineer", "admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Support staff access is required.")
    return user
