# The trilingual inscription of Šābuhr I at the Kaʿba-ye Zartošt (ŠKZ)

This repository includes the corpus of Greek, Middle Persian, and Parthian versions of the inscription aligned at both sentence and word levels, a dataset of the named entities, and a gazetteer of the places the text names.

Everything here is also browsable at **https://farnoosh-shamsian.github.io/SKZ/**.

The corpus follows the line numbering of Huyse (1999). The Greek text is taken from the digital epigraphy collection of the Packard Humanities Institute, which uses the edition of Canali De Rossi (2004).  
The Parthian and Middle Persian versions are based on Huyse's edition. The Parthian version is taken from Jake Nabel's digital resource at http://parthiansources.com, and the Middle Persian was added by Farnoosh Shamsian.  
The alignments were produced using the Ugarit alignment tool. All alignments are available openly online on Ugarit here: https://ugarit.ialigner.com/userProfile.php?userid=40&tgid=21881  
The extracted alignment pairs are made available both as one file (xlsx, csv and tsv) and also as separate files (csv and xlsx) in zip, where the name of each file is the line number.

## The datasets

| file | what it is |
| --- | --- |
| `SKZ-sentence-level.{tsv,csv,xlsx}` | the three versions side by side, 51 ŠKZ lines |
| `alignment-pairs.{tsv,csv,xlsx}`, `alignment-pairs-separate-files.zip` | 1,013 word-level alignment pairs, as one table or one file per line |
| `named-entities.{tsv,csv}` | 412 named-entity attestations |
| [`geo-linking/`](geo-linking/) | the place gazetteer and the map |

The named entity dataset contains 412 named entities, extracted and classified manually as persons (PER), locations (LOC), or location derivatives (LOCderiv). The dataset includes the named entities across all three versions (if available) and the line number in which they appear.

## Places

[`geo-linking/`](geo-linking/) identifies the 149 places behind the 206 LOC and LOCderiv attestations, links them to Pleiades and Wikidata, and maps the 134 that can be located. Identifications follow Huyse's *Griechisches Glossar* (Band 1, pp. 114–171), checked entry by entry against the printed page. [`geo-linking/skz-map.html`](geo-linking/skz-map.html) is a single self-contained file with no libraries and no network requests; [`geo-linking/README.md`](geo-linking/README.md) documents the gazetteer column by column.

## Citing

F. Shamsian & M. Berti, "Annotating Named Entities in the Trilingual Inscription at Kaʿba-ye Zartošt (ŠKZ)", *Digital Classics Online* 12,2 (2026), [doi:10.11588/dco.2026.12.112297](https://doi.org/10.11588/dco.2026.12.112297).

## References

Canali De Rossi (2004): F. Canali De Rossi (ed.), Iscrizioni dello estremo oriente greco. Un repertorio. «Inschriften griechischer Städte aus Kleinasien» 65, Bonn 2004.

Huyse (1999): P. Huyse (ed.), Die dreisprachige Inschrift Šābuhrs I. an der Kaʿba-i Zardušt (ŠKZ), Corpus Inscriptionum Iranicarum III/I/I, London 1999.
