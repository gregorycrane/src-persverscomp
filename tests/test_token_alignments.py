from pipeline.ingest_work import _merge_groups_sharing_target_indices


def test_rows_with_the_same_target_indices_become_one_many_to_many_group():
    groups = [
        {
            "src_indices": [3], "tgt_indices": [5, 6],
            "src_tokens": ["οὐκ"], "tgt_tokens": ["بیدار", "نکردی"],
            "score": 1.0, "meta": {"reference": "43b.2"},
        },
        {
            "src_indices": [5], "tgt_indices": [5, 6],
            "src_tokens": ["ἐπήγειράς"], "tgt_tokens": ["بیدار", "نکردی"],
            "score": 1.0, "meta": {"reference": "43b.2"},
        },
    ]

    assert _merge_groups_sharing_target_indices(groups) == [{
        "src_indices": [3, 5], "tgt_indices": [5, 6],
        "src_tokens": ["οὐκ", "ἐπήγειράς"],
        "tgt_tokens": ["بیدار", "نکردی"],
        "score": 1.0, "meta": {"reference": "43b.2"},
    }]


def test_different_and_empty_target_sets_remain_separate():
    groups = [
        {"src_indices": [1], "tgt_indices": [2], "src_tokens": ["a"], "tgt_tokens": ["x"], "score": .9},
        {"src_indices": [2], "tgt_indices": [3], "src_tokens": ["b"], "tgt_tokens": ["y"], "score": .8},
        {"src_indices": [3], "tgt_indices": [], "src_tokens": ["c"], "tgt_tokens": [], "score": .7},
        {"src_indices": [4], "tgt_indices": [], "src_tokens": ["d"], "tgt_tokens": [], "score": .6},
    ]

    assert len(_merge_groups_sharing_target_indices(groups)) == 4
