"""Extract selected note runs using reviewed page and heading manifests.

The unmodified OCR exports remain the transcription evidence. No raw export
is overwritten. Page-line coordinates always refer to nonempty original lines.
"""
import json,re
from pathlib import Path
D=Path(__file__).parent
CONFIG={'tlg006':{'title':'Choephoroi / Libation Bearers','first':163,'last':234,'witnesses':['hw42j8']},'tlg007':{'title':'Eumenides','first':251,'last':322,'witnesses':['hw42j8','hxjha8']}}
PAT=re.compile(r'^(\d{1,4})(?:\s*[-–—]+\s*(\d{1,4}))?\s*(?:(ff?\.)|[.,:]|(?<=\d)(?=\s+[A-Z]))\s*')
def parse_pages():
 out={}
 for w in ['hw42j8','hxjha8']:
  b=re.split(r'## p\. (.*?) \(#(\d+)\) #+\n',(D/(w+'.txt')).read_text());out[w]={}
  for i in range(1,len(b),3):
   if b[i].isdigit() and 160<=int(b[i])<=334:
    if b[i] in out[w]:raise ValueError(('duplicate printed page',w,b[i]))
    out[w][b[i]]={'seq':int(b[i+1]),'lines':[s.strip() for s in b[i+2].splitlines() if s.strip()]}
 return out

def extract():
 pages=parse_pages();bounds=json.loads((D/'boundaries.json').read_text());ed=json.loads((D/'editorial.json').read_text()) if (D/'editorial.json').exists() else {};out={};excluded=[];orphans=[]
 for play,cfg in CONFIG.items():
  out[play]={}
  for w in cfg['witnesses']:
   notes=[];prev=1;after_missing=False
   for number in range(cfg['first'],cfg['last']+1):
    page=str(number)
    if page not in pages[w]:
     after_missing=True
     continue
    lines=pages[w][page]['lines'];start=bounds[page]['start' if w=='hw42j8' else 'second_start'];indices=ed.get('orders',{}).get(w,{}).get(page,list(range(start,len(lines))))
    if page=='172':indices=[2]+indices # displaced continuation syllable
    if page=='251':
     # Both OCRs displace 'zum' above the first heading. Restore only its
     # unambiguous connection: 'Nebenraume des Tempels zum Haupteingange'.
     indices.remove(6) if 6 in indices else None
     after=next(i for i in indices if lines[i]=='Nebenraume des Tempels')
     indices.insert(indices.index(after)+1,6)
    for i in indices:
     raw=lines[i];s=raw
     rule=ed.get('lines',{}).get(w,{}).get(page,{}).get(str(i),{})
     if rule.get('skip'):excluded.append([w,page,i,raw,rule['skip']]);continue
     if s.isdigit() or (not re.search(r'[A-Za-z\u0370-\u03ff\u1f00-\u1fff]',s) and not re.fullmatch(r'\d+\.',s)) or s.startswith('Äschylos, Orestie'):
      excluded.append([w,page,i,raw,'isolated layout marker']);continue
     if rule.get('replace') is not None:s=rule['replace']
     m=PAT.match(s)
     if not m and re.match(r'^\d+[-–—]+\d+\s+',s):m=re.match(r'^(\d+)[-–—]+(\d+)(?P<ff>)\s+',s)
     if rule.get('not_heading'):m=None
     if m and (abs(int(m[1])-prev)<100 or not notes or rule.get('heading')):
      n=int(m[1]);end=int(m[2]) if m[2] else n+(1 if m[3]=='f.' else 0)
      if end<n:end=int(str(n)[:-len(m[2])]+m[2])
      label=f'{n}-{end}' if end!=n else str(n)
      after_missing=False
      notes.append({'n':label,'page':page,'heading':m[0],'original_heading_line':raw,'parts':[]});prev=n;s=s[m.end():]
     if after_missing:
      orphans.append({'play':play,'witness':w,'page':page,'index':i,'text':raw,'reason':'Continuation after unavailable comparison pages; not attached to preceding note.'})
      continue
     if not notes:raise ValueError(('unanchored opening',play,w,page,i,s))
     notes[-1]['parts'].append({'page':page,'index':i,'text':s})
   out[play][w]=notes
   print(play,w,len(notes),'notes; last',notes[-1]['n'])
 (D/'pages.json').write_text(json.dumps(pages,ensure_ascii=False,indent=2)+'\n');(D/'notes.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');(D/'excluded-layout.json').write_text(json.dumps(excluded,ensure_ascii=False,indent=2)+'\n')
 (D/'unanchored-comparison.json').write_text(json.dumps(orphans,ensure_ascii=False,indent=2)+'\n')
 return out
if __name__=='__main__':extract()
