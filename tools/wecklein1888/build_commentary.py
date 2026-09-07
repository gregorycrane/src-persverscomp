"""Build the conservatively collated Wecklein 1888 Agamemnon commentary.

Inputs: original HathiTrust OCR exports, reviewed page boundaries and heading
repairs, existing Wecklein 1885 edition and Smyth reference. No network calls.
Run extract_notes.py first. The JSON audit preserves every alternate OCR span.
"""
import argparse,collections,difflib,hashlib,json,re,unicodedata
from pathlib import Path
from lxml import etree as E
NS='http://www.tei-c.org/ns/1.0'; XML='http://www.w3.org/XML/1998/namespace'
WORK='urn:cts:greekLit:tlg0085.tlg005';VERSION=WORK+'.wecklein1888-com-ger1'
D=Path(__file__).parent

def el(parent,tag,text=None,**attrs):
 x=E.SubElement(parent,'{'+NS+'}'+tag,attrs);x.text=text;return x

def norm(s):
 return ''.join(c for c in unicodedata.normalize('NFD',s.lower().replace('ς','σ')) if '\u03b1'<=c<='\u03c9')

def prose(parts):
 # Restore words divided by physical OCR line breaks; raw exports remain intact.
 return re.sub(r'(?<=[^\W\d_])[-¬]\n(?=[^\W\d_])','', '\n'.join(x['text'] for x in parts)).replace('\n',' ').strip()

def append_text(node,text):
 if len(node):node[-1].tail=(node[-1].tail or '')+text
 else:node.text=(node.text or '')+text

GREEK=r'[\u0370-\u03ff\u1f00-\u1fff]+'
CITE=r'(?:(?:Soph\.\s+)?(?:Oed\.\s*[TK]\.|Ai\.|Ant\.|El\.|Phil\.|Trach\.)|Eum\.|Cho\.|Prom\.|Suppl\.|Sept\.|Pers\.|Ag\.)\s*\d+(?:\s*[-–—]\s*\d+)?(?:\s+ff?\.)?'
TOKEN=re.compile('('+CITE+')|('+GREEK+r'(?:[\s᾽’]+[\u0370-\u03ff\u1f00-\u1fff]+)*)')
def markup(node,text):
 last=0
 for m in TOKEN.finditer(text):
  append_text(node,text[last:m.start()]);v=m[0]
  if m[1]:el(node,'bibl',v,n=v)
  else:el(node,'mentioned',v,**{'{'+XML+'}lang':'grc'})
  last=m.end()
 append_text(node,text[last:])

def build(edition,reference,out):
 notes=json.loads((D/'notes.json').read_text());pages=json.loads((D/'pages.json').read_text());bounds=json.loads((D/'boundaries.json').read_text())
 ns={'t':NS};weck=E.parse(str(edition));ref=E.parse(str(reference))
 refs={x.get('n') for x in ref.xpath('//t:l',namespaces=ns)}
 lines={x.get('n'):x for x in weck.xpath('//t:l',namespaces=ns)}
 supplement=json.loads((D/'alignment_supplement.json').read_text())
 def mapped(n):
  x=lines.get(str(n));v=x.get('corresp','').split(':')[-1] if x is not None else ''
  v=v or supplement.get(str(n),'')
  if not v or any(z not in refs for z in v.split('-')):raise ValueError(('unresolved reference',n,v))
  return v
 root=E.Element('{'+NS+'}TEI',nsmap={None:NS});hd=el(root,'teiHeader');fd=el(hd,'fileDesc');ts=el(fd,'titleStmt')
 el(ts,'title','Wecklein’s explanatory commentary on Aeschylus, Agamemnon (1888): collated OCR draft');el(ts,'author','N. Wecklein')
 rs=el(ts,'respStmt');el(rs,'resp','OCR collation and TEI conversion; unresolved OCR and unverified alignment explicitly retained');el(rs,'name','OpenAI Codex, for Gregory Crane')
 ps=el(fd,'publicationStmt');el(ps,'publisher','Perseus Multitext project');el(ps,'date','2026-09-06',when='2026-09-06');el(ps,'idno',VERSION,type='CTS-URN');el(el(ps,'availability'),'p','Public-domain print source, as identified by the HathiTrust exports. Original OCR provenance and rights statements are retained with the conversion inputs.')
 sd=el(fd,'sourceDesc');bib=el(sd,'bibl');el(bib,'title','Äschylos Orestie mit erklärenden Anmerkungen von N. Wecklein. Erster Teil: Agamemnon.');el(bib,'editor','N. Wecklein');el(bib,'pubPlace','Leipzig');el(bib,'publisher','B. G. Teubner');el(bib,'date','1888',when='1888');el(bib,'biblScope','30–140',unit='page')
 lw=el(sd,'listWit');scans={'iowa':'iau.31858021876903','harvard':'hvd.hw42j8'}
 for w,scan in scans.items():
  wit=el(lw,'witness',**{'{'+XML+'}id':w});el(wit,'ref',scan,target='https://hdl.handle.net/2027/'+scan);el(wit,'p','Google-digitized HathiTrust OCR; '+('University of Iowa' if w=='iowa' else 'Harvard University')+' copy. SHA-256: '+hashlib.sha256((D/(w+'.txt')).read_bytes()).hexdigest())
 enc=el(hd,'encodingDesc');ed=el(enc,'editorialDecl')
 for text in [
  'Explanatory notes only, pp. 30–140. The introduction, Greek running text and separate textual appendix (pp. 141–160) are excluded. Greek readings naturally discussed within notes are retained.',
  'Iowa is the base OCR. Harvard is collated entry by entry. Disagreements are not automatically emended: base readings appear in sic, with alternate readings in collation.json. Identical OCR may still be wrong. Line-end hyphenation is mechanically joined; no spelling modernization is applied.',
  'Source note numbers remain in n. Corresp reuses the existing Wecklein 1885-to-Smyth crosswalk. Content corroboration against the 1888 Greek page text is recorded per entry; otherwise the alignment is explicitly provisional. This is not a newly verified complete 1888 crosswalk.',
  'f. is expanded to one following line; ff. anchors only its starting line. Broad source ranges remain ranges. Repeated source numbers are combined into one addressable entry. Physical pages remain pb milestones within notes.',
  'Greek script is marked as mentioned. Recognizable abbreviated citations are marked bibl; unverified cross-work line correspondences are not invented. Further quotation/gloss tagging and scan proofreading remain necessary.'
 ]:el(ed,'p',text)
 rd=el(enc,'refsDecl',n='CTS');cr=el(rd,'cRefPattern',n='commline',matchPattern='(.+)',replacementPattern="#xpath(/tei:TEI/tei:text/tei:body/tei:div/tei:div[@n='$1'])");el(cr,'p','Select an entry by its printed source line or range.')
 modern=el(enc,'refsDecl',**{'{'+XML+'}id':'CTS-modern'});cs=el(modern,'citeStructure',match='/TEI/text/body/div',use='@n');el(cs,'citeStructure',match="div[@subtype='commline']",use='@n',unit='commline',delim=':')
 lu=el(el(hd,'profileDesc'),'langUsage')
 for ident,name in [('ger','German'),('grc','Ancient Greek'),('lat','Latin')]:el(lu,'language',name,ident=ident)
 el(el(hd,'revisionDesc'),'change','Initial conservative two-witness integration; unresolved OCR and provisional alignment retained.',when='2026-09-06')
 text=el(root,'text',**{'{'+XML+'}lang':'ger'});body=el(text,'body');div=el(body,'div',type='commentary',n=VERSION)
 hindex=collections.defaultdict(list)
 for n in notes['harvard']:hindex[(n['page'],n['n'].split('-')[0])].append(n)
 report={'version':VERSION,'status':'collated OCR draft','entries':[]};used=collections.Counter();entries={}
 for count,a in enumerate(notes['iowa'],1):
  key=(a['page'],a['n'].split('-')[0]);hc=hindex[key];h=hc[min(used[key],len(hc)-1)] if hc else None;used[key]+=1
  native=a['n'];nums=[int(z) for z in native.split('-')]
  target=mapped(nums[0]);last=mapped(nums[-1])
  if len(nums)>1:
   # Crosswalk can contain transpositions: use full covered numeric envelope.
   targets=[int(v) for n in range(nums[0],nums[-1]+1) for v in mapped(n).split('-') if v.isdigit()]
   target=str(min(targets))+'-'+str(max(targets))
  x=entries.get(native)
  if x is None:x=el(div,'div',type='textpart',subtype='commline',n=native,corresp=WORK+'.perseus-grc2:'+target,**{'{'+XML+'}id':'comm-'+native});entries[native]=x
  original=lines[str(nums[0])];greek=norm(''.join(original.itertext()))
  pageverse=norm(' '.join(pages['iowa'][a['page']]['lines'][:bounds[a['page']]['start']]))
  checked=len(greek)>=12 and greek in pageverse
  if not checked:el(el(x,'p',type='alignment-status'),'note','Reference alignment provisional: inherited from Wecklein 1885; verify against the 1888 scan.',type='alignment',cert='low')
  meta=el(x,'p',type='source');el(meta,'ref','Wecklein 1888, p. '+a['page'],target='https://babel.hathitrust.org/cgi/pt?id='+scans['iowa']+'&seq='+str(pages['iowa'][a['page']]['seq']))
  raw=' '.join(prose(list(g)) for _,g in __import__('itertools').groupby(a['parts'],lambda v:v['page']));alt=prose(h['parts']) if h else ''; aw=raw.split();hw=alt.split();flags=set();diffs=[]
  for op,i,j,k,l in difflib.SequenceMatcher(None,aw,hw,autojunk=False).get_opcodes():
   if op!='equal':flags.update(range(i,j));diffs.append({'base_words':[i,j],'iowa':' '.join(aw[i:j]),'harvard':' '.join(hw[k:l])})
  # Explicitly flag mixed-script words even when the two OCR engines agree.
  for i,w in enumerate(aw):
   if re.search(GREEK,w) and re.search('[A-Za-z]',w):flags.add(i)
  audit={'n':native,'page':a['page'],'source_heading':a['heading'],'harvard_heading':h['heading'] if h else None,'reference':target,'alignment':'page-content-corroborated' if checked else 'provisional-inherited','differences':diffs,'iowa':raw,'harvard':alt}
  report['entries'].append(audit)
  p=el(x,'p');wi=0;currentpage=None
  # Each physical page is independently normalized so pb provenance survives.
  groups=[]
  for part in a['parts']:
   if not groups or groups[-1][0]!=part['page']:groups.append((part['page'],[]))
   groups[-1][1].append(part)
  for pg,parts in groups:
   el(p,'pb',n=pg,facs='https://babel.hathitrust.org/cgi/pt?id='+scans['iowa']+'&seq='+str(pages['iowa'][pg]['seq']))
   words=prose(parts).split();start=0
   # Collation uses the same page-wise word normalization (see assertion below).
   while start<len(words):
    uncertain=(wi+start in flags);end=start+1
    while end<len(words) and (wi+end in flags)==uncertain:end+=1
    node=el(p,'sic',source='#iowa',resp='#ocr-conversion') if uncertain else p
    markup(node,' '.join(words[start:end]));append_text(p,' ');start=end
   wi+=len(words)
  if any(not d['iowa'] and d['harvard'] for d in diffs):
   el(el(x,'p',type='ocr-status'),'note','Harvard has additional OCR text here; see collation record. Possible omission or layout disagreement remains unresolved.',type='ocr')
  if not h:el(el(x,'p',type='ocr-status'),'note','Corresponding Harvard note boundary unresolved; this entry retains the Iowa OCR.',type='ocr')
  assert wi==len(aw),(native,wi,len(aw))
 # Attach the conversion responsibility identifier after all header construction.
 rs.set('{'+XML+'}id','ocr-conversion')
 out.mkdir(parents=True,exist_ok=True)
 path=out/(VERSION.split(':')[-1]+'.xml');E.ElementTree(root).write(str(path),encoding='UTF-8',xml_declaration=True,pretty_print=True)
 report['summary']={'entries':len(entries),'source_notes':len(notes['iowa']),'pages':111,'differences':sum(len(x['differences']) for x in report['entries']),'content_corroborated':sum(x['alignment']=='page-content-corroborated' for x in report['entries']),'provisional':sum(x['alignment']=='provisional-inherited' for x in report['entries'])}
 (out/'collation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report['summary']))
 return path
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--edition',type=Path,required=True);ap.add_argument('--reference',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();build(a.edition,a.reference,a.out)
