"""Strict whole-resource integrity checks for the two OCR draft commentaries."""
import argparse,json,re
from pathlib import Path
from lxml import etree as E
N={'t':'http://www.tei-c.org/ns/1.0'}
XML='{http://www.w3.org/XML/1998/namespace}'
def validate(directory,canonical):
 for play,count,first,last,witnesses in [('tlg006',591,163,234,1),('tlg007',542,251,322,2)]:
  tree=E.parse(str(directory/f'tlg0085.{play}.wecklein1888-com-ger1.xml'),E.XMLParser(recover=False))
  audit=json.loads((directory/f'{play}-audit.json').read_text())
  refs=E.parse(str(canonical/f'data/tlg0085/{play}/tlg0085.{play}.perseus-grc2.xml'))
  refnums=set(refs.xpath('//t:l/@n',namespaces=N))
  nodes=tree.xpath('//t:div[@subtype="commline"]',namespaces=N)
  assert len(nodes)==count==len(audit['entries'])
  assert len({x.get('n') for x in nodes})==count
  ids=tree.xpath('//@xml:id',namespaces={'xml':XML[1:-1]});assert len(ids)==len(set(ids))
  assert tree.xpath('//t:citeStructure',namespaces=N) and tree.xpath('//t:cRefPattern',namespaces=N)
  assert len(tree.xpath('//t:witness',namespaces=N))==witnesses
  assert not tree.xpath('//t:app|//t:l',namespaces=N)
  assert {int(x) for x in tree.xpath('//t:pb/@n',namespaces=N)}==set(range(first,last+1))
  for x in tree.xpath('//*[@source or @resp or @target]',namespaces=N):
   for attr in ('source','resp','target'):
    for ptr in (x.get(attr) or '').split():
     if ptr.startswith('#'):assert ptr[1:] in ids
  for node,entry in zip(nodes,audit['entries']):
   assert node.get('n')==entry['n']
   cor=node.get('corresp');assert cor==f'urn:cts:greekLit:tlg0085.{play}.perseus-grc2:'+entry['reference']
   assert all(n in refnums for n in entry['reference'].split('-'))
   assert node.xpath('t:p[@type="source"]/t:ref',namespaces=N)
   text=''.join(node.itertext())
   if entry['alignment']=='provisional':assert 'Reference alignment provisional' in text
   if play=='tlg006':assert 'Single-witness OCR' in text and entry['hxjha8'] is None
   if entry['missing_comparison_pages']:
    assert 'not a lacuna in the ancient text' in text
    assert node.xpath('.//t:gap[@reason="ocr-source-unavailable"]',namespaces=N)
  gaps=tree.xpath('//t:gap',namespaces=N)
  assert len(gaps)==(22 if play=='tlg007' else 0)
  assert tree.xpath('//t:sic',namespaces=N)
  assert not audit['unanchored_comparison']
  print(play,'strict XML,',count,'entries, references, page coverage, pointers and draft warnings verified')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--canonical',type=Path,required=True);a=p.parse_args();validate(a.directory,a.canonical)
