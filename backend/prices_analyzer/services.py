from itertools import groupby
from pathlib import Path
from tempfile import TemporaryDirectory
from . import database
from .comparison import compare
from .config import BACKEND_DIR, BOOKS_URL
from .models import ImportResult
from .sources.csv_source import read_csv
from .sources.books_source import collect_books, parse_html


def persist(batch, db, dry_run=False):
    added, duplicates = database.save(db,batch.records,dry_run=dry_run)
    return ImportResult(batch.processed,added,duplicates,batch.errors,dry_run)


def import_csv(path, db, dry_run=False):
    return persist(read_csv(path),db,dry_run)


def import_html(path, db, observed_at, *, page_url=BOOKS_URL, dry_run=False):
    page = parse_html(Path(path).read_bytes(),page_url,observed_at)
    return persist(page.batch,db,dry_run)


def collect(db, max_pages=1, dry_run=False):
    return persist(collect_books(max_pages),db,dry_run)


def compare_purchase(db, product, quantity, max_days):
    items = database.latest(db,product=product)
    key = lambda item: (item.currency,item.offer.product.unit)
    return [(currency,unit,compare(group,quantity,max_days))
            for (currency,unit),group in groupby(sorted(items,key=key),key=key)]


def demo(directory=None):
    directory = Path(directory) if directory is not None else BACKEND_DIR / 'db'
    directory.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory(prefix='demo-',dir=directory) as temporary:
        db = Path(temporary)/'demo.sqlite3'
        database.initialize(db)
        first = import_csv(BACKEND_DIR/'data/sample_offers.csv',db)
        repeated = import_csv(BACKEND_DIR/'data/sample_offers.csv',db)
        html = import_html(BACKEND_DIR/'tests/fixtures/books_page.html',db,'2026-11-22T09:00:00Z')
        return dict(first=first,repeated=repeated,html=html,
                    items=database.latest(db),history=database.history(db,'demo','paper-b'),
                    comparisons=compare_purchase(db,'demo:paper-a4','10',7))
