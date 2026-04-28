from app.db.models import PromptVersion
from app.db.sqlite import build_session_factory, DATABASE_URL
from sqlmodel import Session

def seed_prompts():
    session_factory = build_session_factory(DATABASE_URL)
    prompts = [
        {"prompt_name": "chiefStrategist", "version": "v1", "role_scope": "chiefStrategist_en", "template_path": "chiefStrategist_en.txt", "schema_name": "SOTP"},
        {"prompt_name": "chiefStrategist", "version": "v1", "role_scope": "chiefStrategist_zh", "template_path": "chiefStrategist_zh.txt", "schema_name": "SOTP"},
        {"prompt_name": "fundamentalAnalyst", "version": "v1", "role_scope": "fundamentalAnalyst_en", "template_path": "fundamentalAnalyst_en.txt", "schema_name": "SOTP"},
        {"prompt_name": "fundamentalAnalyst", "version": "v1", "role_scope": "fundamentalAnalyst_zh", "template_path": "fundamentalAnalyst_zh.txt", "schema_name": "SOTP"},
        {"prompt_name": "technicalAnalyst", "version": "v1", "role_scope": "technicalAnalyst_en", "template_path": "technicalAnalyst_en.txt", "schema_name": "Technical"},
        {"prompt_name": "technicalAnalyst", "version": "v1", "role_scope": "technicalAnalyst_zh", "template_path": "technicalAnalyst_zh.txt", "schema_name": "Technical"},
    ]

    with session_factory() as session:
        for p in prompts:
            session.add(PromptVersion(**p))
        session.commit()
    print("Prompts seeded.")

if __name__ == "__main__":
    seed_prompts()
