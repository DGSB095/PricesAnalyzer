from decimal import Decimal
import pytest
import requests
from prices_analyzer.models import DataError
from prices_analyzer.sources.books_source import parse_html, load_html, collect_books

STAMP = '2026-11-22T09:00:00Z'
URL = 'https://books.toscrape.com/'


class Response:
    def __init__(self,body=b'',status=200,headers=None):
        self.content,self.status_code,self.headers = body,status,headers or {}
    def __enter__(self):
        return self
    def __exit__(self,*args):
        pass


class Client:
    def __init__(self,*responses):
        self.responses = iter(responses)
        self.calls = []
    def get(self,url,**kwargs):
        self.calls.append((url,kwargs))
        response = next(self.responses)
        if isinstance(response,Exception):
            raise response
        return response


def test_price_encoding_links_and_unknowns(html):
    page = parse_html(html,URL,STAMP)
    assert len(page.batch.records) == 2
    item = page.batch.records[0]
    assert item.offer.product.name == 'A Light in the Attic'
    assert item.price == Decimal('51.77') and item.currency == 'GBP'
    assert item.offer.url == URL+'catalogue/a-light-in-the-attic_1000/index.html'
    assert item.offer.external_id == '1000'
    assert item.availability == 'in_stock'
    assert item.minimum_quantity is item.delivery_days is item.delivery_cost is item.extra_cost is None
    assert page.next_url == URL+'catalogue/page-2.html'
    changed = html.decode('utf-8').replace('catalogue/','../',2)
    parsed = parse_html(changed,URL+'catalogue/category/books/test/index.html',STAMP)
    assert parsed.batch.records[0].offer.url.startswith(URL)


def test_partial_cards_and_markup_failure(html,backend):
    broken = (backend/'tests/fixtures/books_broken.html').read_bytes()
    with pytest.raises(DataError,match='ни один товар'):
        parse_html(broken,URL,STAMP)
    with pytest.raises(DataError,match='товары не распознаны'):
        parse_html('<html>Changed</html>',URL,STAMP)
    partial = html.decode('utf-8').replace('£51.77','???')
    page = parse_html(partial,URL,STAMP)
    assert len(page.batch.records) == 1 and len(page.batch.errors) == 1
    assert 'карточка 1' in page.batch.errors[0]
    with pytest.raises(DataError,match='UTF-8'):
        parse_html(b'\xff',URL,STAMP)


def test_availability_and_unsafe_link(html):
    text = html.decode('utf-8')
    page = parse_html(text.replace('In stock','Out of stock'),URL,STAMP)
    assert page.batch.records[0].availability == 'out_of_stock'
    page = parse_html(text.replace('In stock','Ask us'),URL,STAMP)
    assert page.batch.records[0].availability is None
    with pytest.raises(DataError,match='пределы'):
        parse_html(text.replace('catalogue/page-2.html','https://example.com/'),URL,STAMP)


def test_network_retries_are_bounded(html):
    client = Client(requests.Timeout('slow'),Response(status=503),Response(html))
    waits = []
    assert load_html(URL,client,sleeper=waits.append) == html
    assert len(client.calls) == 3 and len(waits) == 3
    assert client.calls[0][1]['timeout'] > 0
    client = Client(*[requests.ConnectionError('offline') for _ in range(3)])
    with pytest.raises(DataError,match='после 3 попыток'):
        load_html(URL,client,sleeper=lambda _:None)
    assert len(client.calls) == 3
    client = Client(Response(status=403))
    with pytest.raises(DataError,match='HTTP 403'):
        load_html(URL,client,sleeper=lambda _:None)
    assert len(client.calls) == 1


def test_rate_limit_retry_after(html):
    waits = []
    client = Client(Response(status=429,headers={'Retry-After':'3'}),Response(html))
    load_html(URL,client,sleeper=waits.append)
    assert waits == [0.5,3]
    with pytest.raises(DataError,match='отложить'):
        load_html(URL,Client(Response(status=429,headers={'Retry-After':'120'})),sleeper=lambda _:None)


def test_pagination_limit_and_cycle(html):
    client = Client(Response(html))
    batch = collect_books(1,client=client,sleeper=lambda _:None)
    assert len(client.calls) == 1 and batch.processed == 2
    second = html.decode('utf-8').replace('catalogue/a-light','a-light').replace('catalogue/tipping','tipping')
    second = second.replace('catalogue/page-2.html','/')
    client = Client(Response(html),Response(second.encode('utf-8')))
    with pytest.raises(DataError,match='цикл'):
        collect_books(3,client=client,sleeper=lambda _:None)
    assert [call[0] for call in client.calls] == [URL,URL+'catalogue/page-2.html']
    client = Client(Response(html),Response(second.replace('<li class="next">','<li class="end">').encode('utf-8')))
    batch = collect_books(3,client=client,sleeper=lambda _:None)
    assert batch.processed == 4 and len(client.calls) == 2
    assert len({r.observed_at for r in batch.records}) == 1
