"""Prepare witness derivatives. Requires Poppler pdftotext and lxml.
Usage: python extract.py --text supplied.txt --pdf supplied.pdf
Reviewed boundaries/editorial.json are inputs to build.py, not regenerated.
"""
import argparse,re,json,hashlib,subprocess
from pathlib import Path
from lxml import etree as E
D=Path(__file__).parent

def extract(text,pdf):
 raw=text.read_bytes();(D/'oxford-1893.txt').write_bytes(raw)
 parts=re.split(r'## p\.\s*(.*?)\s*\(#(\d+)\) #+\n',raw.decode('utf-8'))
 pages=[{'label':parts[i],'seq':int(parts[i+1]),'lines':[l.strip() for l in parts[i+2].splitlines() if l.strip()]} for i in range(1,len(parts),3)]
 (D/'pages1893.json').write_text(json.dumps(pages,ensure_ascii=False,indent=2))
 subprocess.run(['pdftotext','-f','44','-l','157','-bbox-layout',str(pdf),str(D/'bbox.html')],check=True)
 r=E.parse(str(D/'bbox.html'));ns={'h':'http://www.w3.org/1999/xhtml'};out={}
 for pg,p in enumerate(r.findall('.//h:page',ns),31):
  ws=[dict(text=w.text,**{k:float(v) for k,v in w.attrib.items()}) for w in p.findall('.//h:word',ns)]
  en=[w for w in ws if re.fullmatch('[a-zA-Z]{4,}',w['text'] or '')];xmin=min(w['xMin'] for w in en);xmax=max(w['xMax'] for w in en);mid=(xmin+xmax)/2;top=min(w['yMin'] for w in en)-2;bottom=max(w['yMax'] for w in en)+3
  lines=[]
  for col in [0,1]:
   ww=[w for w in ws if xmin-4<=w['xMin']<=xmax and top<=w['yMax']<=bottom and int(w['xMin']>=mid)==col];rows=[]
   for w in sorted(ww,key=lambda w:w['yMax']):
    if not rows or w['yMax']-rows[-1][0]>3:rows.append([w['yMax'],[]])
    rows[-1][1].append(w)
   lines.extend(' '.join(w['text'] for w in sorted(row,key=lambda w:w['xMin'])) for _,row in rows)
  out[str(pg)]={'pdf_page':pg+13,'lines':lines,'bounds':[xmin,top,mid,xmax,bottom]}
 (D/'secondary-columns.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
 manifest=[{'filename':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in [text,pdf]]
 (D/'sources.json').write_text(json.dumps(manifest,indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--text',type=Path,required=True);p.add_argument('--pdf',type=Path,required=True);a=p.parse_args();extract(a.text,a.pdf)
