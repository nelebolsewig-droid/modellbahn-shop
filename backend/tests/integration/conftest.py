import pytest


@pytest.fixture(autouse=True)
def _clean(clean_database: None) -> None:
    """Every integration test starts with empty tables."""
