import re

with open('cogs/dashboard.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find all SelectOption with description
pattern = r'SelectOption\([^)]*?description="([^"]*)"'
for m in re.finditer(pattern, content):
    desc = m.group(1)
    line_num = content[:m.start()].count('\n') + 1
    if len(desc) < 15:
        print(f"Line {line_num}: len={len(desc)} desc=\"{desc}\"")

# Find all SelectOption without description
pattern2 = r'SelectOption\((label="[^"]*",\s*value="[^"]*")\)'
for m in re.finditer(pattern2, content):
    line_num = content[:m.start()].count('\n') + 1
    print(f"Line {line_num}: NO DESC - {m.group(1)}")
