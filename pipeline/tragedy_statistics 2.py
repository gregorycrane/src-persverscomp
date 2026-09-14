"""Edition-specific descriptive counts from local Greek TEI, read-only."""
from pathlib import Path
import xml.etree.ElementTree as ET


def build(corpus, catalog):
    result = {}
    for tg, numbers in [('tlg0085', range(1, 8)), ('tlg0011', range(1, 8)), ('tlg0006', range(2, 20))]:
        for number in numbers:
            work = 'tlg%03d' % number
            key = tg + '.' + work
            path = Path(corpus) / tg / work / (key + '.perseus-grc2.xml')
            if not path.exists() or key not in catalog['works']:
                continue
            lines = [l for l in ET.parse(path).findall('.//{*}body//{*}l') if l.get('n') != '0']
            # Include the printed additions and bracketed/deleted text; omit
            # editorial notes and stage directions if present inside a line.
            def text(element):
                if element.tag.split('}')[-1] in ('note', 'stage', 'speaker'):
                    return ''
                return (element.text or '') + ''.join(text(c) + (c.tail or '') for c in element)
            words = sum(sum(any(c.isalpha() for c in token) for token in text(line).split()) for line in lines)
            edition = next(v for v in catalog['works'][key]['versions'] if v['short_id'] == 'perseus-grc2')
            result[key] = dict(title=catalog['works'][key]['title'], author=catalog['authors'][tg],
                               citation_span=lines[0].get('n')+'–'+lines[-1].get('n'),
                               encoded_segments=len(lines), words=words, edition=edition['label'],
                               source=str(path))
    return result
