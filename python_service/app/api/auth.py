from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlmodel import Session, select
from sqlalchemy import text as sa_text
from sqlalchemy.exc import OperationalError, ProgrammingError
from ..db.database import get_session
from ..db.models import User
from .limiter import limiter
import os
import secrets
import logging

logger = logging.getLogger(__name__)

def get_or_create_jwt_secret():
    secret = os.getenv("JWT_SECRET_KEY")
    if secret:
        return secret
    
    runtime_env = ".env.runtime"
    if os.path.exists(runtime_env):
        with open(runtime_env, "r") as f:
            for line in f:
                if line.startswith("JWT_SECRET_KEY="):
                    return line.strip().split("=", 1)[1]
                    
    new_secret = secrets.token_hex(32)
    try:
        with open(runtime_env, "a") as f:
            f.write(f"\nJWT_SECRET_KEY={new_secret}\n")
    except IOError:
        pass
    return new_secret

# Secret key for JWT. Use an env variable in production
SECRET_KEY = get_or_create_jwt_secret()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15  # 15 minutes (financial security best practice)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/token", auto_error=False)

router = APIRouter()

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_session)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if token is None:
        raise credentials_exception
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = db.exec(select(User).where(User.username == username)).first()
    if user is None:
        raise credentials_exception
    return user

async def get_optional_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_session)) -> Optional[User]:
    if token is None:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
    except JWTError:
        return None
    user = db.exec(select(User).where(User.username == username)).first()
    return user

def require_role(roles: list[str]):
    async def role_checker(current_user: User = Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role}' not authorized. Required: {roles}"
            )
        return current_user
    return role_checker


class UserRegister(BaseModel):
    username: str
    password: str
    display_name: Optional[str] = None

class AdminUserCreate(BaseModel):
    username: str
    password: str
    display_name: Optional[str] = None
    role: str = "viewer"

class UserUpdate(BaseModel):
    role: Optional[str] = None
    status: Optional[str] = None
    display_name: Optional[str] = None

class PasswordChange(BaseModel):
    old_password: str
    new_password: str


@router.post("/register", response_model=dict)
@limiter.limit("5/minute")
def register(request: Request, payload: UserRegister, db: Session = Depends(get_session)):
    user = db.exec(select(User).where(User.username == payload.username)).first()
    if user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    hashed_password = get_password_hash(payload.password)
    new_user = User(
        username=payload.username,
        hashed_password=hashed_password,
        display_name=payload.display_name or payload.username,
        role="viewer"
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"msg": "User registered successfully", "user_id": new_user.user_id}

@router.post("/admin-create-user", response_model=dict)
def admin_create_user(payload: AdminUserCreate, current_user: User = Depends(require_role(["admin"])), db: Session = Depends(get_session)):
    if payload.role not in ("admin", "researcher", "viewer"):
        raise HTTPException(status_code=400, detail="Invalid role")
    existing = db.exec(select(User).where(User.username == payload.username)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")
    hashed_password = get_password_hash(payload.password)
    new_user = User(
        username=payload.username,
        hashed_password=hashed_password,
        display_name=payload.display_name or payload.username,
        role=payload.role,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"msg": "User created", "user_id": new_user.user_id, "username": new_user.username, "role": new_user.role, "status": new_user.status}

@router.post("/token", response_model=dict)
@limiter.limit("10/minute")
def login_for_access_token(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_session)):
    user = db.exec(select(User).where(User.username == form_data.username)).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if user.status != "active":
        raise HTTPException(status_code=403, detail="Account is deactivated")
    user.last_login = datetime.utcnow()
    db.add(user)
    db.commit()
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role, "user_id": user.user_id},
        expires_delta=access_token_expires
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "user_id": user.user_id,
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role
        }
    }

@router.get("/me", response_model=dict)
def read_users_me(current_user: User = Depends(get_current_user)):
    return {
        "user_id": current_user.user_id,
        "username": current_user.username,
        "display_name": current_user.display_name,
        "role": current_user.role
    }

@router.post("/change-password", response_model=dict)
def change_password(payload: PasswordChange, current_user: User = Depends(get_current_user), db: Session = Depends(get_session)):
    if not verify_password(payload.old_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect old password")
    current_user.hashed_password = get_password_hash(payload.new_password)
    db.add(current_user)
    db.commit()
    return {"msg": "Password changed successfully"}


# --- Admin User Management ---

@router.get("/users", response_model=list)
def list_users(current_user: User = Depends(require_role(["admin"])), db: Session = Depends(get_session)):
    users = db.exec(select(User)).all()
    return [
        {
            "user_id": u.user_id,
            "username": u.username,
            "display_name": u.display_name,
            "role": u.role,
            "status": u.status,
            "created_at": u.created_at.isoformat() + "Z" if u.created_at else None,
            "last_login": u.last_login.isoformat() + "Z" if u.last_login else None,
        }
        for u in users
    ]

@router.put("/users/{user_id}", response_model=dict)
def update_user(user_id: str, payload: UserUpdate, current_user: User = Depends(require_role(["admin"])), db: Session = Depends(get_session)):
    user = db.exec(select(User).where(User.user_id == user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if payload.role is not None:
        if payload.role not in ("admin", "researcher", "viewer"):
            raise HTTPException(status_code=400, detail="Invalid role")
        user.role = payload.role
    if payload.status is not None:
        if payload.status not in ("active", "deactivated"):
            raise HTTPException(status_code=400, detail="Invalid status")
        user.status = payload.status
    if payload.display_name is not None:
        user.display_name = payload.display_name
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"msg": "User updated", "user_id": user.user_id, "role": user.role, "status": user.status}

@router.delete("/users/{user_id}", response_model=dict)
def delete_user(user_id: str, current_user: User = Depends(require_role(["admin"])), db: Session = Depends(get_session)):
    if user_id == current_user.user_id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    user = db.exec(select(User).where(User.user_id == user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # ── Cascade-delete all user-related data using raw SQL ──
    # Raw SQL is used because some legacy tables have schemas that
    # don't match the current SQLModel definitions (e.g. watchlist).
    def _exec_safe(sql: str, **kwargs) -> None:
        """Execute raw SQL via SQLAlchemy execute(), catching schema mismatches."""
        try:
            db.execute(sa_text(sql), kwargs)
        except (OperationalError, ProgrammingError) as e:
            logger.warning("Cascade-delete skipped for: %s — %s", sql.split()[2] if len(sql.split()) > 2 else sql, e)

    def _fetch_ids(sql: str, **kwargs) -> list:
        """Fetch a list of scalar values from a query, or empty on schema mismatch."""
        try:
            return [r[0] for r in db.execute(sa_text(sql), kwargs).all()]
        except (OperationalError, ProgrammingError) as e:
            logger.warning("Cascade-delete query skipped: %s — %s", sql.split()[2] if len(sql.split()) > 2 else sql, e)
            return []

    # Order matters: child FK records before parent records.

    # SearchAlert → Catalyst
    for alert_id in _fetch_ids("SELECT alert_id FROM searchalert WHERE user_id = :uid", uid=user_id):
        _exec_safe("DELETE FROM catalyst WHERE alert_id = :aid", aid=alert_id)
    _exec_safe("DELETE FROM searchalert WHERE user_id = :uid", uid=user_id)

    # AnalysisJob → PromptRun
    for job_id in _fetch_ids("SELECT job_id FROM analysisjob WHERE user_id = :uid", uid=user_id):
        _exec_safe("DELETE FROM promptrun WHERE job_id = :jid", jid=job_id)
    _exec_safe("DELETE FROM analysisjob WHERE user_id = :uid", uid=user_id)

    # AnalysisRun → AnalysisArtifact
    for analysis_id in _fetch_ids("SELECT analysis_id FROM analysisrun WHERE user_id = :uid", uid=user_id):
        _exec_safe("DELETE FROM analysisartifact WHERE analysis_id = :aid", aid=analysis_id)
    _exec_safe("DELETE FROM analysisrun WHERE user_id = :uid", uid=user_id)

    # MockAccount → MockPosition / MockTrade / MockAccountSnapshot / AnomalyLog / PendingOrder
    for account_id in _fetch_ids("SELECT account_id FROM mockaccount WHERE user_id = :uid", uid=user_id):
        _exec_safe("DELETE FROM mockposition WHERE account_id = :aid", aid=account_id)
        _exec_safe("DELETE FROM mocktrade WHERE account_id = :aid", aid=account_id)
        _exec_safe("DELETE FROM mockaccountsnapshot WHERE account_id = :aid", aid=account_id)
        _exec_safe("DELETE FROM anomalylog WHERE account_id = :aid", aid=account_id)
        _exec_safe("DELETE FROM pendingorder WHERE account_id = :aid", aid=account_id)
    _exec_safe("DELETE FROM mockaccount WHERE user_id = :uid", uid=user_id)

    # Tables with user_id — skip the legacy watchlist/watchlistitem schema
    _exec_safe("DELETE FROM reflectionmemory WHERE user_id = :uid", uid=user_id)
    _exec_safe("DELETE FROM tradeintent WHERE user_id = :uid", uid=user_id)
    _exec_safe("DELETE FROM journalentry WHERE user_id = :uid", uid=user_id)
    _exec_safe("DELETE FROM apikey WHERE user_id = :uid", uid=user_id)

    # Finally delete the user
    db.delete(user)
    db.commit()
    return {"msg": "User deleted", "user_id": user_id}

@router.get("/users/{user_id}/queries", response_model=dict)
def list_user_queries(user_id: str, current_user: User = Depends(require_role(["admin"])), db: Session = Depends(get_session)):
    from app.db.models import AnalysisJob
    jobs = db.exec(select(AnalysisJob).where(AnalysisJob.user_id == user_id).order_by(AnalysisJob.created_at.desc()).limit(50)).all()
    return {
        "queries": [
            {
                "job_id": j.job_id,
                "symbol": j.symbol,
                "market": j.market,
                "analysis_level": j.analysis_level,
                "status": j.status,
                "created_at": j.created_at.isoformat() if j.created_at else None,
            }
            for j in jobs
        ]
    }
