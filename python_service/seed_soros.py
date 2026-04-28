from app.db.models import PromptVersion
from app.db.sqlite import build_session_factory, DATABASE_URL
from sqlmodel import Session

def seed_soros():
    session_factory = build_session_factory(DATABASE_URL)
    prompts = [
        {"prompt_name": "sorosPhilosopher", "version": "v1", "role_scope": "soros_en", "template_path": "soros_en.txt", "schema_name": "Philosophy"},
        {"prompt_name": "sorosPhilosopher", "version": "v1", "role_scope": "soros_zh", "template_path": "soros_zh.txt", "schema_name": "Philosophy"},
    ]

    with session_factory() as session:
        for p in prompts:
            session.add(PromptVersion(**p))
        session.commit()
    print("Soros philosopher seeded.")

if __name__ == "__main__":
    seed_soros()
