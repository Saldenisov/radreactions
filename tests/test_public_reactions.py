from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from public_reactions import is_public_buxton_reaction


def test_public_buxton_reaction_requires_validation_and_public_table() -> None:
    assert is_public_buxton_reaction({"validated": 1, "table_no": 5}, [5, 6, 7, 8, 9])
    assert not is_public_buxton_reaction({"validated": 0, "table_no": 5}, [5, 6, 7, 8, 9])
    assert not is_public_buxton_reaction({"validated": 1, "table_no": 10}, [5, 6, 7, 8, 9])
    assert not is_public_buxton_reaction(None, [5, 6, 7, 8, 9])
