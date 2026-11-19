import pytest


@pytest.fixture
def seeded(db):
    from apps.geo.seed import seed

    seed()
