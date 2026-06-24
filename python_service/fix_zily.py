import os
import sys

# Setup environment to connect to ALSA DB
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from app.db.database import session_factory
from app.db.models import User
from app.api.auth import get_password_hash
from sqlmodel import select

with session_factory() as session:
    user = session.exec(select(User).where(User.username == "zily")).first()
    if not user:
        print("User zily not found! Creating...")
        new_user = User(
            username="zily",
            hashed_password=get_password_hash("zily9958"),
            display_name="Zily Admin",
            role="admin",
            status="active"
        )
        session.add(new_user)
        session.commit()
        print("Created zily user with admin role.")
    else:
        print(f"User zily exists! Role: {user.role}, Status: {user.status}")
        # Reset password to zily9958 just in case
        user.hashed_password = get_password_hash("zily9958")
        user.role = "admin"
        user.status = "active"
        session.add(user)
        session.commit()
        print("Reset zily password and ensured admin role.")
