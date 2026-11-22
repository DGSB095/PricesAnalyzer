import pytest
from prices_analyzer.models import DataError
from prices_analyzer.sources.csv_source import read_csv


def test_bom_and_cyrillic(backend,tmp_path):
    path = tmp_path/'bom.csv'
    path.write_text((backend/'data/sample_offers.csv').read_text(encoding='utf-8'),encoding='utf-8-sig')
    batch = read_csv(path)
    assert batch.processed == 8
    assert len(batch.records) == 8
    assert not batch.errors
    assert batch.records[0].offer.product.name == 'Учебная бумага A4'
    assert len({r.offer.product.id for r in batch.records}) == 3


def test_invalid_rows_have_line_numbers(backend):
    batch = read_csv(backend/'data/invalid_offers.csv')
    assert batch.processed == 7
    assert len(batch.records) == 1
    assert len(batch.errors) == 6
    assert 'Строка 3: price:' in batch.errors[0]
    assert 'Строка 8: delivery_days:' in batch.errors[-1]


def test_bad_headers_and_column_count(backend,tmp_path):
    path = tmp_path/'bad.csv'
    path.write_text('price,price\n1,2',encoding='utf-8')
    with pytest.raises(DataError,match='повторяющиеся'):
        read_csv(path)
    path.write_text('price\n1',encoding='utf-8')
    with pytest.raises(DataError,match='отсутствуют'):
        read_csv(path)
    sample = (backend/'data/sample_offers.csv').read_text(encoding='utf-8').splitlines()
    path.write_text(sample[0]+'\n'+sample[1]+',extra\n',encoding='utf-8')
    batch = read_csv(path)
    assert not batch.records
    assert 'Строка 2' in batch.errors[0]
