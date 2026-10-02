import re
lines = open('spec/tasks.md').read().splitlines()
block = [lines[100], lines[101]]
raw = ''
for l in block:
    m = re.search(r'\*\*\s*Covers\s*\*\*\s*`?([^`·]*)`?', l)
    if m:
        raw = m.group(1)
print('raw covers:', repr(raw))
print('findall:', re.findall(r'`([^`]+)`', raw))

# Now test through parse_task
import sys
sys.path.insert(0, 'scripts')
from gen_board import parse_task
it = iter(lines[100:])
t = parse_task(it)
print('T-01 covers:', t['covers'])
print('T-01 depends:', t['depends'])
