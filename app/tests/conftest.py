import pytest
from file_categorizer.core.db import Database


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.db")