import fitz
doc = fitz.open('oiji.pdf')
for i in range(3, min(6, len(doc))):
    print(f'--- Page {i+1} ---')
    print(doc[i].get_text()[:3000])
