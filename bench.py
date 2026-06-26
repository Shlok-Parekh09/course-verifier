import fitz, time, re
t0=time.time()
doc=fitz.open('link_compile.pdf')
print('Pages:', len(doc))
c=0
m=0
for i in range(len(doc)):
 text=doc[i].get_text()
 if text:
  c+=1
  if re.search(r'^\s*(\d+)\.\s+(.+?)\s*$', text, re.MULTILINE):
   m+=1
print('Parsed', c, 'pages,', m, 'matches in', time.time()-t0, 'sec')
