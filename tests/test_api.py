from agent.tools import use_project_root, write_file


def test_file_tools_are_isolated_by_project_root(tmp_path):
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"

    with use_project_root(first_root):
        write_file.invoke({"path": "only-first.txt", "content": "first"})
    with use_project_root(second_root):
        write_file.invoke({"path": "only-second.txt", "content": "second"})

    assert (first_root / "only-first.txt").read_text() == "first"
    assert not (first_root / "only-second.txt").exists()
    assert (second_root / "only-second.txt").read_text() == "second"
    assert not (second_root / "only-first.txt").exists()
