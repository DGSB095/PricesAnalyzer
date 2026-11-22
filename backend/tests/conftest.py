from pathlib import Path
import pytest
import requests
from prices_analyzer.sources.csv_source import read_csv


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Network forbidden in ordinary tests')
    monkeypatch.setattr(requests.sessions.Session,'request',forbidden)


@pytest.fixture
def backend():
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def records(backend):
    return read_csv(backend/'data/sample_offers.csv').records


@pytest.fixture
def html(backend):
    return (backend/'tests/fixtures/books_page.html').read_bytes()
