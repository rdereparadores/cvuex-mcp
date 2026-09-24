from cvuex_mcp.state import PersistentState


def test_values_survive_between_instances(tmp_path):
    path = tmp_path / "state.json"
    PersistentState(path).set("a", 1)
    PersistentState(path).set("b", "x")
    assert PersistentState(path).get("a") == 1
    assert PersistentState(path).get("b") == "x"


def test_missing_values_are_none(tmp_path):
    assert PersistentState(tmp_path / "state.json").get("a") is None
