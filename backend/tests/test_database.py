from dataclasses import replace
from decimal import Decimal
import sqlite3
import pytest
from prices_analyzer import database, services
from prices_analyzer.models import DataError
from prices_analyzer.validation import observation_time


def test_schema_save_reopen_and_foreign_keys(tmp_path,records):
    db = tmp_path/'data.sqlite3'
    database.initialize(db)
    assert database.save(db,records) == (8,0)
    database.initialize(db)
    assert database.save(db,records) == (0,8)
    assert len(database.latest(db)) == 7
    with database.connect(db) as conn:
        assert conn.execute('PRAGMA foreign_keys').fetchone()[0] == 1
        assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        row = conn.execute('SELECT price,typeof(price),delivery_cost FROM observations WHERE delivery_cost IS NULL').fetchone()
        assert row['typeof(price)'] == 'text' and row['delivery_cost'] is None
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO offers(source,external_id,product_id,supplier_id,url) VALUES('x','x','missing','missing','https://example.com')")


def test_history_latest_and_equal_price_new_time(tmp_path,records):
    db = tmp_path/'history.sqlite3'
    database.initialize(db)
    item = records[2]
    newer = replace(item,observed_at=observation_time('2026-11-23T00:00:00Z'))
    assert database.save(db,[newer,records[1],item]) == (3,0)
    history = database.history(db,'demo','paper-b')
    assert len(history) == 3 and history[0] == newer
    assert database.latest(db,product='demo:paper-a4',supplier='demo:b',source='demo') == [newer]
    same_instant = replace(newer,observed_at=observation_time('2026-11-23T03:00:00+03:00'),price=Decimal('120.00'))
    assert database.save(db,[same_instant]) == (0,1)
    assert database.latest(db,source='books') == []


def test_conflict_rolls_back_entire_batch(tmp_path,records):
    db = tmp_path/'rollback.sqlite3'
    database.initialize(db)
    database.save(db,[records[0]])
    conflict = replace(records[0],price=Decimal('101'))
    with pytest.raises(DataError,match='Конфликт наблюдения'):
        database.save(db,[records[1],conflict])
    assert database.latest(db) == [records[0]]
    assert database.history(db,'demo','paper-b') == []


def test_sql_failure_rolls_back(tmp_path,records):
    db = tmp_path/'sql-error.sqlite3'
    database.initialize(db)
    with database.connect(db) as conn:
        conn.execute("CREATE TRIGGER fail_second BEFORE INSERT ON observations WHEN NEW.price='125' BEGIN SELECT RAISE(ABORT,'simulated storage failure'); END")
    with pytest.raises(sqlite3.IntegrityError,match='simulated storage failure'):
        database.save(db,records)
    assert database.latest(db) == []
    with database.connect(db) as conn:
        assert conn.execute('SELECT count(*) FROM products').fetchone()[0] == 0


def test_dry_run_and_snapshot_idempotence(tmp_path,backend):
    db = tmp_path/'snapshot.sqlite3'
    fixture = backend/'tests/fixtures/books_page.html'
    args = (fixture,db,'2026-11-22T09:00:00Z')
    assert services.import_html(*args,dry_run=True).added == 2
    assert not db.exists()
    database.initialize(db)
    assert services.import_html(*args).added == 2
    before = db.read_bytes()
    assert services.import_html(*args,dry_run=True).duplicates == 2
    assert db.read_bytes() == before
    assert services.import_html(*args).duplicates == 2
    assert len(database.latest(db)) == 2


def test_source_namespace_does_not_merge_titles(tmp_path,records):
    db = tmp_path/'sources.sqlite3'
    database.initialize(db)
    item = records[0]
    other = replace(item,offer=replace(item.offer,source='other',
        product=replace(item.offer.product,id='other:paper-a4')))
    assert database.save(db,[item,other]) == (2,0)
    assert len(database.latest(db)) == 2


def test_partial_csv_persists_only_valid_rows(tmp_path,backend):
    db = tmp_path/'partial.sqlite3'
    database.initialize(db)
    result = services.import_csv(backend/'data/invalid_offers.csv',db)
    assert (result.processed,result.added,result.duplicates,len(result.errors)) == (7,1,0,6)
    assert len(database.latest(db)) == 1
