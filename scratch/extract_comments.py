import os
import re

directories = ['core', 'editor', 'tools', 'ui']
files_to_check = ['main.py', 'studio_logger.py', 'extractor.py', 'debug_triposr.py', 'monkey_tester.py']

all_files = []
for d in directories:
    for root, _, files in os.walk(d):
        for f in files:
            if f.endswith('.py'):
                all_files.append(os.path.join(root, f))
all_files.extend([f for f in files_to_check if os.path.exists(f)])

comment_pattern = re.compile(r'^(\s*)#\s*(.+)$')

results = {}

for filepath in all_files:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        comments = []
        for i, line in enumerate(lines):
            match = comment_pattern.match(line)
            if match:
                comment = match.group(2).strip()
                if not comment.startswith('---') and not comment.startswith('noqa') and not comment.startswith('type:') and not comment.startswith('TODO'):
                    comments.append((i+1, comment))
        if comments:
            results[filepath] = comments
    except Exception as e:
        print(f"Error reading {filepath}: {e}")

with open('scratch/all_comments.txt', 'w', encoding='utf-8') as f:
    for filepath, comments in results.items():
        f.write(f"--- {filepath} ---\n")
        for line_num, comment in comments:
            f.write(f"{line_num}: {comment}\n")
        f.write("\n")
print("Done")
