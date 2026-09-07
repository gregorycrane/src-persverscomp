"""Strict XML and real-parser validation against the project's reference cards."""
import argparse,json,collections
from pathlib import Path
from lxml import etree as E,html
from extract import CONFIG
from pipeline.parsers.line_commentary import parse_line_commentary_tei
N={'t':'http://www.tei-c.org/ns/1.0'}
def validate(directory,canonical):
 results={}
 for name,cfg in CONFIG.items():
  play=cfg['play'];p=directory/f'tlg0085.{play}.{cfg["short"]}.xml';t=E.parse(str(p),E.XMLParser(recover=False));a=json.loads((directory/(name+'-audit.json')).read_text());ref=E.parse(str(canonical/f'data/tlg0085/{play}/tlg0085.{play}.perseus-grc2.xml'))
  refs=set(ref.xpath('//t:l/@n',namespaces=N));units=t.xpath('//t:div[@subtype="commline"]',namespaces=N);labels=[x.get('n') for x in units];ids=t.xpath('//@xml:id');assert len(ids)==len(set(ids))
  assert len(labels)==len(set(labels))==a['summary']['unique_entries']
  assert {int(x) for x in t.xpath('//t:pb/@n',namespaces=N)}==set(range(cfg['first'],cfg['last']+1))
  assert len(t.xpath('//t:witness',namespaces=N))==1 and t.xpath('//t:citeStructure',namespaces=N) and t.xpath('//t:cRefPattern',namespaces=N)
  assert t.xpath('//t:author/text()',namespaces=N)[0]==cfg['author']
  assert cfg['year'] in t.xpath('//t:date/text()',namespaces=N)
  for u in units:
   assert u.get('corresp').startswith(f'urn:cts:greekLit:tlg0085.{play}.perseus-grc2:')
   assert all(k in refs for k in u.get('corresp').rsplit(':',1)[-1].split('-'))
   s=''.join(u.itertext());assert 'Single-witness OCR' in s and 'Reference placement provisional' in s
  assert not t.xpath('//t:app|//t:l',namespaces=N)
  intervals={'':[{'book':'','label':str(i),'start_line':i,'end_line':i} for i in range(1,1201)]}
  parsed=parse_line_commentary_tei(str(p),intervals,lineno_sigil=cfg['sigil'],anchor_axis='corresp',reference_sigil='Smyth',show_reference_line=True)['']
  s=''.join(x['1'] for x in parsed.values());dom=html.fragment_fromstring(s,create_parent='div');rendered=dom.xpath('//span[@class="comm-native-line"]/text()')
  assert collections.Counter(rendered)==collections.Counter(cfg['sigil']+' '+n for n in labels)
  assert s.count('Single-witness OCR')==a['summary']['source_notes']
  assert s.count('Reference placement provisional')==a['summary']['source_notes']
  assert 'tei-sic' in s and cfg['scan'] in s
  for el in t.xpath('//*[@source or @target or @resp]'):
   for attr in ['source','target','resp']:
    for ptr in (el.get(attr) or '').split():
     if ptr.startswith('#'):assert ptr[1:] in ids
  results[name]=dict(a['summary'],strict_xml=True,reference_endpoints=True,all_labels_render=True,all_warnings_render=True)
 print(json.dumps(results,indent=2));return results
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--canonical',type=Path,required=True);a=p.parse_args();validate(a.directory,a.canonical)
