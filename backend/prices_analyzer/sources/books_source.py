import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

from ..config import BOOKS_URL, HTTP_TIMEOUT, HTTP_RETRIES, REQUEST_PAUSE
from ..models import Batch, DataError
from ..validation import parse_row, observation_time


@dataclass
class Page:
    batch: Batch
    next_url: str | None


def book_url(base, relative):
    url = urljoin(base, relative)
    parts = urlsplit(url)
    if parts.scheme != 'https' or parts.netloc != 'books.toscrape.com':
        raise DataError('Books: ссылка выходит за пределы https://books.toscrape.com')
    return urlunsplit((parts.scheme,parts.netloc,parts.path or '/',parts.query,''))


def load_html(url, client, *, timeout=HTTP_TIMEOUT, retries=HTTP_RETRIES,
              pause=REQUEST_PAUSE, sleeper=time.sleep):
    url = book_url(BOOKS_URL, url)
    if timeout <= 0 or retries < 0 or pause < 0:
        raise DataError('Некорректные настройки HTTP')
    wait = pause
    for attempt in range(retries + 1):
        sleeper(wait)
        try:
            with client.get(url, timeout=timeout, allow_redirects=False,
                            headers={'User-Agent':'PricesAnalyzer/0.1 (educational HTML parser)'}) as response:
                status = response.status_code
                if status == 429 or status in (500,502,503,504):
                    if attempt == retries:
                        raise DataError(f'Books: HTTP {status}, исчерпаны {retries + 1} попытки: {url}')
                    retry_after = response.headers.get('Retry-After')
                    if retry_after and (not retry_after.isdigit() or int(retry_after) > 30):
                        raise DataError(f'Books: HTTP {status}, сервер требует отложить запрос: {retry_after}')
                    wait = max(pause, 2 ** attempt, int(retry_after or 0))
                    continue
                if status != 200:
                    raise DataError(f'Books: HTTP {status}: {url}; запрос не повторяется')
                return response.content
        except (requests.Timeout, requests.ConnectionError) as exc:
            if attempt == retries:
                raise DataError(f'Books: ошибка сети после {retries + 1} попыток: {exc}') from exc
            wait = max(pause, 2 ** attempt)
        except requests.RequestException as exc:
            raise DataError(f'Books: ошибка HTTP: {exc}') from exc


def parse_html(html, page_url, observed_at):
    stamp = observation_time(observed_at)
    page_url = book_url(BOOKS_URL,page_url)
    try:
        text = html.decode('utf-8-sig') if isinstance(html, bytes) else html
    except UnicodeDecodeError as exc:
        raise DataError('Books: ожидается HTML в UTF-8') from exc
    soup = BeautifulSoup(text, 'html.parser')
    cards = soup.select('article.product_pod')
    if not cards:
        raise DataError('Books: товары не распознаны, отсутствуют article.product_pod; возможно, изменилась разметка')
    batch = Batch(processed=len(cards))
    for index, card in enumerate(cards, 1):
        try:
            anchor, price = card.select_one('h3 a'), card.select_one('.price_color')
            if anchor is None or price is None or not anchor.get('title') or not anchor.get('href'):
                raise DataError('неполная карточка: нужны название, ссылка и цена')
            match = re.fullmatch(r'£(\d+\.\d{2})',price.get_text(strip=True))
            if not match:
                raise DataError('цена не распознана: ожидается £ и десятичная цена')
            url = book_url(page_url,anchor['href'])
            external = re.search(r'_([0-9]+)/index\.html$',urlsplit(url).path)
            if not external:
                raise DataError('не распознан внешний идентификатор в ссылке')
            stock = card.select_one('.availability')
            availability = None
            if stock:
                status = stock.get_text(' ',strip=True).lower()
                if status == 'in stock':
                    availability = 'in_stock'
                elif status == 'out of stock':
                    availability = 'out_of_stock'
            batch.records.append(parse_row(dict(
                product_id='books:'+external[1],product_name=anchor['title'],unit='pcs',
                supplier_id='books',supplier_name='Books to Scrape (учебный магазин)',source='books',
                external_id=external[1],url=url,price=match[1],currency='GBP',
                observed_at=stamp.isoformat(),availability=availability)))
        except DataError as exc:
            batch.errors.append(f'{page_url}, карточка {index}: {exc}')
    if not batch.records:
        raise DataError('Books: ни один товар не распознан. ' + '; '.join(batch.errors))
    next_node = soup.select_one('li.next')
    next_url = None
    if next_node:
        anchor = next_node.select_one('a[href]')
        if anchor is None:
            raise DataError('Books: повреждена ссылка следующей страницы')
        next_url = book_url(page_url,anchor['href'])
    return Page(batch,next_url)


def collect_books(max_pages=1, *, client=None, sleeper=time.sleep):
    if isinstance(max_pages, bool) or not isinstance(max_pages, int) or max_pages <= 0:
        raise DataError('max-pages должен быть положительным целым числом')
    stamp = datetime.now(timezone.utc)
    batch, visited, url = Batch(), set(), BOOKS_URL
    session = client if client is not None else requests.Session()
    try:
        for _ in range(max_pages):
            if url in visited:
                raise DataError('Books: обнаружен цикл пагинации; сбор отменён')
            visited.add(url)
            page = parse_html(load_html(url,session,sleeper=sleeper),url,stamp)
            batch.records.extend(page.batch.records)
            batch.errors.extend(page.batch.errors)
            batch.processed += page.batch.processed
            if not page.next_url:
                break
            url = page.next_url
        return batch
    finally:
        if client is None:
            session.close()
