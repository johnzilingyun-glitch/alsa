import os
import glob

def rename_imports(base_dir):
    for root, _, files in os.walk(base_dir):
        for f in files:
            if f.endswith('.py'):
                path = os.path.join(root, f)
                with open(path, 'r', encoding='utf-8') as file:
                    content = file.read()
                
                if 'app.db.sqlite' in content:
                    content = content.replace('app.db.sqlite', 'app.db.database')
                    with open(path, 'w', encoding='utf-8') as file:
                        file.write(content)
                        print(f"Updated: {path}")

if __name__ == "__main__":
    rename_imports('/home/ubuntu/work/alsa/python_service')
