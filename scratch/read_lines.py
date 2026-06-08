import os

path = 'python_service/app/services/report_generator_service.py'
with open(path, 'rb') as f:
    lines = f.readlines()

output_path = 'scratch/lines_1220_1329.txt'
with open(output_path, 'w', encoding='utf-8') as outf:
    for i in range(1220, 1329):
        if i < len(lines):
            line = lines[i]
            indent = len(line) - len(line.lstrip(b' '))
            outf.write(f'{i+1:4d}: indent={indent:2d} | {line.decode("utf-8", errors="replace")}')

print(f"Lines written to {output_path}")
