import hashlib
import secrets
from typing import List, Optional, Callable
from sqlmodel import Session, select
from ..models import ApiKey


def generate_api_key() -> tuple[str, str]:
    raw = f"alsa_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    return raw, key_hash


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


class ApiKeyRepository:
    def __init__(self, session_factory: Callable[[], Session]):
        self.session_factory = session_factory

    def create(self, user_id: str, name: str, scopes: str = "[]",
               rate_limit_override: Optional[str] = None,
               expires_at=None) -> tuple[ApiKey, str]:
        raw_key, key_hash = generate_api_key()
        with self.session_factory() as session:
            api_key = ApiKey(
                user_id=user_id,
                key_hash=key_hash,
                name=name,
                scopes=scopes,
                rate_limit_override=rate_limit_override,
                expires_at=expires_at,
            )
            session.add(api_key)
            session.commit()
            session.refresh(api_key)
            return api_key, raw_key

    def list_by_user(self, user_id: str) -> List[ApiKey]:
        with self.session_factory() as session:
            stmt = select(ApiKey).where(
                ApiKey.user_id == user_id,
                ApiKey.is_active == True,
            ).order_by(ApiKey.created_at.desc())
            return session.exec(stmt).all()

    def get_by_key_hash(self, key_hash: str) -> Optional[ApiKey]:
        with self.session_factory() as session:
            stmt = select(ApiKey).where(
                ApiKey.key_hash == key_hash,
                ApiKey.is_active == True,
            )
            return session.exec(stmt).first()

    def get_by_id(self, key_id: str) -> Optional[ApiKey]:
        with self.session_factory() as session:
            return session.get(ApiKey, key_id)

    def revoke(self, key_id: str, user_id: str) -> bool:
        with self.session_factory() as session:
            stmt = select(ApiKey).where(
                ApiKey.key_id == key_id,
                ApiKey.user_id == user_id,
            )
            api_key = session.exec(stmt).first()
            if not api_key:
                return False
            api_key.is_active = False
            session.add(api_key)
            session.commit()
            return True

    def update(self, key_id: str, user_id: str, **kwargs) -> Optional[ApiKey]:
        with self.session_factory() as session:
            stmt = select(ApiKey).where(
                ApiKey.key_id == key_id,
                ApiKey.user_id == user_id,
            )
            api_key = session.exec(stmt).first()
            if not api_key:
                return None
            for k, v in kwargs.items():
                if hasattr(api_key, k):
                    setattr(api_key, k, v)
            session.add(api_key)
            session.commit()
            session.refresh(api_key)
            return api_key

    def touch_last_used(self, key_id: str):
        from ...time_utils import utc_now
        with self.session_factory() as session:
            api_key = session.get(ApiKey, key_id)
            if api_key:
                api_key.last_used_at = utc_now()
                session.add(api_key)
                session.commit()
