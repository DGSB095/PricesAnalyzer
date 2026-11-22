import sqlite3
from contextlib import contextmanager
from pathlib import Path
from .models import DataError
from .validation import as_row, parse_row

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, unit TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS suppliers (id TEXT PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS offers (
    id INTEGER PRIMARY KEY, source TEXT NOT NULL, external_id TEXT NOT NULL,
    product_id TEXT NOT NULL REFERENCES products(id),
    supplier_id TEXT NOT NULL REFERENCES suppliers(id), url TEXT NOT NULL,
    UNIQUE(source, external_id)
);
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY, offer_id INTEGER NOT NULL REFERENCES offers(id),
    price TEXT NOT NULL, currency TEXT NOT NULL, minimum_quantity TEXT,
    delivery_cost TEXT, extra_cost TEXT, delivery_days INTEGER,
    observed_at TEXT NOT NULL, availability TEXT,
    UNIQUE(offer_id, observed_at)
);
CREATE INDEX IF NOT EXISTS observation_latest ON observations(offer_id, observed_at DESC, id DESC);
"""
JOINED = """
SELECT p.id product_id, p.name product_name, p.unit, s.id supplier_id, s.name supplier_name,
       o.source, o.external_id, o.url, n.price, n.currency, n.minimum_quantity,
       n.delivery_cost, n.extra_cost, n.delivery_days, n.observed_at, n.availability
FROM observations n JOIN offers o ON o.id=n.offer_id
JOIN products p ON p.id=o.product_id JOIN suppliers s ON s.id=o.supplier_id
"""


@contextmanager
def connect(path, *, existing=False, readonly=False):
    if existing or readonly:
        uri = Path(path).resolve().as_uri() + ("?mode=ro" if readonly else "?mode=rw")
        if not Path(path).is_file():
            raise DataError("База не найдена. Выполните init-db.")
        conn = sqlite3.connect(uri, uri=True)
    else:
        conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()


def initialize(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as conn:
        conn.executescript("BEGIN;" + SCHEMA + "COMMIT;")


def insert_observation(conn, item):
    item = parse_row(as_row(item))
    offer, product, supplier = item.offer, item.offer.product, item.offer.supplier
    old = conn.execute("SELECT name,unit FROM products WHERE id=?", (product.id,)).fetchone()
    if old and tuple(old) != (product.name, product.unit):
        raise DataError(f"Конфликт товара {product.id}: изменились название или единица")
    conn.execute("INSERT OR IGNORE INTO products VALUES(?,?,?)", (product.id,product.name,product.unit))
    old = conn.execute("SELECT name FROM suppliers WHERE id=?", (supplier.id,)).fetchone()
    if old and old[0] != supplier.name:
        raise DataError(f"Конфликт поставщика {supplier.id}")
    conn.execute("INSERT OR IGNORE INTO suppliers VALUES(?,?)", (supplier.id,supplier.name))
    old = conn.execute("SELECT * FROM offers WHERE source=? AND external_id=?", (offer.source,offer.external_id)).fetchone()
    if old and (old['product_id'],old['supplier_id'],old['url']) != (product.id,supplier.id,offer.url):
        raise DataError(f"Конфликт предложения {offer.source}/{offer.external_id}")
    conn.execute("INSERT OR IGNORE INTO offers(source,external_id,product_id,supplier_id,url) VALUES(?,?,?,?,?)",
                 (offer.source,offer.external_id,product.id,supplier.id,offer.url))
    offer_id = conn.execute("SELECT id FROM offers WHERE source=? AND external_id=?", (offer.source,offer.external_id)).fetchone()[0]
    row = as_row(item)
    old = conn.execute(JOINED + " WHERE n.offer_id=? AND n.observed_at=?", (offer_id,row['observed_at'])).fetchone()
    if old:
        if parse_row(dict(old)) != item:
            raise DataError(f"Конфликт наблюдения {offer.source}/{offer.external_id}: то же время, другие условия")
        return False
    conn.execute("""INSERT INTO observations(offer_id,price,currency,minimum_quantity,delivery_cost,
                 extra_cost,delivery_days,observed_at,availability) VALUES(?,?,?,?,?,?,?,?,?)""",
                 (offer_id,*(row[k] for k in ('price','currency','minimum_quantity','delivery_cost',
                                            'extra_cost','delivery_days','observed_at','availability'))))
    return True


def save(path, records, *, dry_run=False):
    with connect(":memory:" if dry_run else path, existing=not dry_run) as conn:
        if dry_run:
            if Path(path).is_file():
                with connect(path, readonly=True) as original:
                    original.backup(conn)
            else:
                conn.executescript(SCHEMA)
        added = duplicates = 0
        with conn:
            conn.execute("BEGIN")
            for record in records:
                if insert_observation(conn, record):
                    added += 1
                else:
                    duplicates += 1
        return added, duplicates


def latest(path, *, product=None, supplier=None, source=None):
    query = JOINED + """ WHERE n.id=(
        SELECT recent.id FROM observations recent WHERE recent.offer_id=o.id
        ORDER BY recent.observed_at DESC,recent.id DESC LIMIT 1)
        AND (? IS NULL OR p.id=?) AND (? IS NULL OR s.id=?) AND (? IS NULL OR o.source=?)
        ORDER BY p.id,o.source,o.external_id"""
    with connect(path, readonly=True) as conn:
        return [parse_row(dict(row)) for row in conn.execute(query,(product,product,supplier,supplier,source,source))]


def history(path, source, external_id):
    with connect(path, readonly=True) as conn:
        rows = conn.execute(JOINED + " WHERE o.source=? AND o.external_id=? ORDER BY n.observed_at DESC,n.id DESC", (source,external_id))
        return [parse_row(dict(row)) for row in rows]
