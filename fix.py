import sys
lines=open('dashboard.py', encoding='utf-8').read().splitlines()
out=[]
inside=False
for i, l in enumerate(lines):
 if l.startswith('            for page_num in range(len(doc)):') and i >= 1300:
  inside=True; out.append(l); continue
 if inside:
  if l.startswith("            if 'doc' in locals():"): inside=False; out.append(l); continue
  if l.startswith('                    '): out.append('                ' + l[20:]); continue
  if l.strip()=='': out.append(''); continue
 out.append(l)
open('dashboard.py', 'w', encoding='utf-8').write('\n'.join(out))
