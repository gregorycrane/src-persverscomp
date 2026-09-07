from pipeline.parsers import DOC_TYPE_PARSERS


def test_every_registered_parser_is_callable():
    assert DOC_TYPE_PARSERS  # non-empty
    for doc_type, fn in DOC_TYPE_PARSERS.items():
        assert callable(fn), f"{doc_type} -> {fn!r} is not callable"
