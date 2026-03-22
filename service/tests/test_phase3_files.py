from pathlib import Path


def test_phase3_main_has_publishbundle():
    text = Path('app/main.py').read_text()
    assert '/publishbundle/build' in text
    assert '/publish' in text
    assert '/connectors/workflow-draft' in text
