import os

path = 'python_service/app/services/report_generator_service.py'
with open(path, 'rb') as f:
    lines = f.readlines()

for i in range(1220, 1280):
    if i < len(lines):
        line = lines[i]
        indent = len(line) - len(line.lstrip(b' '))
        print(f'{i+1:4d}: indent={indent:2d} | {line.decode("utf-8", errors="replace").strip()}')
