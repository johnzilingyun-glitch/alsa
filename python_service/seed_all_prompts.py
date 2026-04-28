
import sys
import os
import re
# Add project root to path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_dir)

from python_service.app.db.sqlite import session_factory
from python_service.app.db.models import PromptVersion
from sqlmodel import select, delete

def seed_all_prompts():
    templates_dir = os.path.join(root_dir, "python_service", "app", "prompting", "templates")
    files = os.listdir(templates_dir)
    
    with session_factory() as session:
        # Clear existing prompts to avoid duplicates and ensure fresh mapping
        session.exec(delete(PromptVersion))
        session.commit()
        
        for filename in files:
            if not filename.endswith(".txt"):
                continue
            
            # Extract prompt name and language/role_scope
            # Pattern: name_lang.txt (e.g. technical_analyst_zh.txt)
            match = re.match(r"(.+?)_(zh|en)\.txt", filename)
            if not match:
                # Handle special cases or single-lang files
                prompt_name = filename.replace(".txt", "")
                role_scope = "global"
            else:
                prompt_name = match.group(1)
                role_scope = f"{prompt_name}_{match.group(2)}"
            
            # Convert snake_case or hyphen-case to a "canonical" prompt_name for the DB
            # We'll keep it as is, but DiscussionService should match it
            
            pv = PromptVersion(
                prompt_name=prompt_name,
                version="v1",
                role_scope=role_scope,
                template_path=filename,
                schema_name="General"
            )
            session.add(pv)
            print(f"Seeding {prompt_name} ({role_scope}) -> {filename}")
        
        session.commit()
    print("All prompts seeded successfully.")

if __name__ == "__main__":
    seed_all_prompts()
