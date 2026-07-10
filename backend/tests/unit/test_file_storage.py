from pathlib import Path

import pytest

from app.storage.files import FileStorage


def test_storage_paths_cannot_escape_data_root(tmp_path: Path) -> None:
    storage = FileStorage(tmp_path)
    with pytest.raises(ValueError):
        storage._safe_path("tmp", "..", "..", "escape")


def test_display_name_removes_paths_and_control_characters() -> None:
    assert FileStorage._safe_display_name("../../bad\x00name.csv") == "badname.csv"
