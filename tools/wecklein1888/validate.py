"""Strict corpus QA; run with the generated commentary path as argument."""
import json,sys
from pathlib import Path
from lxml import etree as E
p=Path(sys.argv[1]);ns={'t':'http://www.tei-c.org/ns/1.0'};t=E.parse(str(p),E.XMLParser(recover=False));root=t.getroot()
assert root.tag=='{'+ns['t']+'}TEI'
notes=t.xpath('//t:div[@subtype="commline"]',namespaces=ns)
assert len(notes)==898
assert len({x.get('n') for x in notes})==898
assert notes[0].get('n')=='1-39' and notes[-1].get('n')=='1673'
assert {x.get('n') for x in t.xpath('//t:pb',namespaces=ns)}==set(map(str,range(30,141)))
assert t.xpath('//t:citeStructure',namespaces=ns) and t.xpath('//t:cRefPattern',namespaces=ns)
assert not t.xpath('//t:app|//t:l',namespaces=ns)
ids=t.xpath('//@xml:id',namespaces=ns);assert len(ids)==len(set(ids))
for x in root.iter():
 for k in ['source','resp','target']:
  for v in x.get(k,'').split():
   if v.startswith('#'):assert v[1:] in ids,v
for x in notes:
 assert x.get('corresp','').startswith('urn:cts:greekLit:tlg0085.tlg005.perseus-grc2:')
 assert x.xpath('.//t:pb',namespaces=ns)
 assert ''.join(x.itertext()).strip()
a=json.loads(p.with_name('collation.json').read_text());assert len(a['entries'])==899
assert all(x['harvard'] for x in a['entries'])
assert sum(x['alignment']=='provisional-inherited' for x in a['entries'])==190
print('Strict XML, 898 unique entries, 111 scan pages, local pointers, both witnesses and draft-status checks passed.')
