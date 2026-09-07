"""Extract reviewed note boundaries from the two preserved OCR exports."""
import json,re,difflib
from pathlib import Path
D=Path(__file__).parent
# Page numbers and HathiTrust sequence numbers are independent.
pages={}
for name in ['iowa','harvard']:
 blocks=re.split(r'## p\. (.*?) \(#(\d+)\) #+\n',(D/(name+'.txt')).read_text())
 pages[name]={}
 for k in range(1,len(blocks),3):
  if blocks[k].isdigit() and 30<=int(blocks[k])<=140:
   pages[name][blocks[k]]={'seq':int(blocks[k+1]),'lines':[x.strip() for x in blocks[k+2].splitlines() if x.strip()]}
 assert len(pages[name])==111
(D/'pages.json').write_text(json.dumps(pages,ensure_ascii=False,indent=2))
bounds=json.loads((D/'boundaries.json').read_text())
pat=re.compile(r'^(\d{1,4})(?:\s*[-–—]\s*(\d{1,4}))?\s*(?:(ff?\.)|[.,]|(?<=\d)(?=\s+[A-Z]))\s*')
allnotes={}
editorial=json.loads((D/'editorial.json').read_text())
for w in pages:
 notes=[];prev=1
 for p,obj in pages[w].items():
  start=bounds[p]['start' if w=='iowa' else 'harvard_start']
  lines=obj['lines'][start:]
  if p=='100' and w=='iowa':lines=['1017 f.']+lines
  if p=='84' and w=='harvard':
   lines=obj['lines'][30:64]+obj['lines'][16:27]+obj['lines'][64:]
  if p=='128' and w=='harvard':lines=[obj['lines'][21]]+obj['lines'][27:]
  for idx,s in enumerate(lines,start):
   if re.fullmatch(r'\d+',s):continue
   if s.startswith('Äschylos, Orestie'):continue
   
   for old,new in editorial['prefix_repairs'].get(w,{}).get(p,{}).values():
    if s.startswith(old):s=new+s[len(old):]
   m=pat.match(s)
   if (p,s) in [('72','617.'),('84','827.'),('136','1608.')]:m=None
   if not m and re.match(r'^\d+[-–—]\d+\s+',s):m=re.match(r'^(\d+)[-–—](\d+)(?P<ff>)\s+',s)
   if m and int(m[1]) in editorial['false_headings'].get(p,[]) and not (p=='125' and 'besser als' not in s):m=None
   if m and (abs(int(m[1])-prev)<100 or not notes):
    n=int(m[1]);end=int(m[2]) if m[2] else n+(1 if m[3]=='f.' else 0)
    if end<n:end=int(str(n)[:-len(m[2])]+m[2])
    label=f'{n}-{end}' if end!=n else str(n)
    notes.append({'n':label,'page':p,'heading':m[0],'parts':[]});prev=n
    s=s[m.end():]
   if not notes:raise ValueError((w,p,s))
   notes[-1]['parts'].append({'page':p,'index':idx,'text':s})
 allnotes[w]=notes
 print(w,len(notes))
 print('last',notes[-1]['n'])
(D/'notes.json').write_text(json.dumps(allnotes,ensure_ascii=False,indent=2))
