"""Parse prose arranged as citation sections containing numbered sentences.

This is the shape used by the sentence-aligned Crito files: each
``div[@subtype='section']`` supplies the Stephanus card (``43a``), and each
direct ``p[@n]`` supplies the aligned sentence number within that card.
"""
import os
from collections import OrderedDict

from pipeline.core.xml_utils import extract_text_recursive, find_text_root, safe_parse


def parse_section_sentences_tei(path):
    if not os.path.exists(path):
        return None
    text_root = find_text_root(safe_parse(path).getroot())
    if text_root is None:
        return None

    data = OrderedDict({"1": OrderedDict()})
    for div in text_root.iter():
        if div.tag.split("}")[-1] != "div":
            continue
        subtype = (div.get("subtype") or div.get("type") or "").lower()
        card = (div.get("n") or "").strip()
        if subtype != "section" or not card:
            continue

        sentences = OrderedDict()
        for child in div:
            if not isinstance(child.tag, str) or child.tag.split("}")[-1] != "p":
                continue
            sentence = (child.get("n") or "").strip()
            if not sentence:
                continue
            content = extract_text_recursive(child, strip_paragraphs=True).strip()
            if content:
                sentences[sentence] = content
        if sentences:
            data["1"][card] = sentences

    return data
