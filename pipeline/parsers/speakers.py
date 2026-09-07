"""Speaker-list CSV parser. Relocated from Cell 4."""
import os
import csv

def parse_speakers_csv(path):
    import csv
    speakers = {}
    if not path or not os.path.exists(path):
        return speakers
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            subdoc  = (row.get('subdoc') or row.get('sentence_id') or row.get('id') or '').strip()
            speaker = (row.get('speaker') or row.get('Speaker') or '').strip()
            if subdoc and speaker:
                speakers[subdoc] = speaker
    return speakers
