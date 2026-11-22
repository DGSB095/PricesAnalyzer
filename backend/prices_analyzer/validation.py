import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit
from .models import DataError, Observation, Offer, Product, Supplier

CURRENCIES = {"RUB", "GBP", "USD", "EUR", "CNY"}
UNITS = {"pcs", "pack", "kg", "g", "l", "m"}
AVAILABILITY = {"in_stock", "out_of_stock"}
FIELDS = "product_id product_name unit supplier_id supplier_name source external_id url price currency minimum_quantity delivery_cost extra_cost delivery_days observed_at availability".split()


def decimal_value(value, name, *, optional=False, positive=False):
    if value is None or str(value).strip() == "":
        if optional:
            return None
        raise DataError(f"{name}: обязательное число")
    text = str(value).strip()
    if isinstance(value, float) or not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", text):
        raise DataError(f"{name}: требуется десятичное число с точкой")
    try:
        result = Decimal(text)
    except InvalidOperation:
        raise DataError(f"{name}: некорректное число") from None
    if not result.is_finite() or result < 0 or (positive and result == 0):
        raise DataError(f"{name}: значение вне допустимого диапазона")
    if len(result.as_tuple().digits) > 28 or abs(result.as_tuple().exponent) > 28:
        raise DataError(f"{name}: допускается до 28 цифр и 28 десятичных разрядов")
    return result


def observation_time(value):
    try:
        stamp = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).strip())
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError()
        return stamp.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise DataError("observed_at: требуется ISO 8601 с часовым поясом") from None


def timestamp(value):
    return observation_time(value).isoformat(timespec="microseconds")


def parse_row(row):
    def required(name):
        value = str(row.get(name) or "").strip()
        if not value:
            raise DataError(f"{name}: обязательное поле")
        return value

    unit, currency = required("unit"), required("currency")
    if unit not in UNITS:
        raise DataError(f"unit: допустимы {', '.join(sorted(UNITS))}")
    if currency not in CURRENCIES:
        raise DataError(f"currency: допустимы {', '.join(sorted(CURRENCIES))}")
    source = required("source")
    if not re.fullmatch(r"[a-z][a-z0-9_-]*", source):
        raise DataError("source: нужны строчные латинские буквы, цифры, _ или -")
    product_id = required("product_id")
    if not product_id.startswith(source + ":") or not product_id[len(source)+1:]:
        raise DataError("product_id: требуется пространство имён source:идентификатор")
    url = required("url")
    try:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.username:
            raise ValueError()
    except ValueError:
        raise DataError("url: требуется HTTP(S) ссылка без авторизации") from None
    days = decimal_value(row.get("delivery_days"), "delivery_days", optional=True)
    if days is not None and (days != days.to_integral_value() or days > 2147483647):
        raise DataError("delivery_days: требуется целое неотрицательное число дней")
    availability = str(row.get("availability") or "").strip() or None
    if availability is not None and availability not in AVAILABILITY:
        raise DataError("availability: in_stock, out_of_stock или пустое поле")
    return Observation(
        Offer(source, required("external_id"),
              Product(product_id, required("product_name"), unit),
              Supplier(required("supplier_id"), required("supplier_name")), url),
        decimal_value(required("price"), "price"), currency,
        decimal_value(row.get("minimum_quantity"), "minimum_quantity", optional=True, positive=True),
        decimal_value(row.get("delivery_cost"), "delivery_cost", optional=True),
        decimal_value(row.get("extra_cost"), "extra_cost", optional=True),
        None if days is None else int(days), observation_time(required("observed_at")), availability,
    )


def as_row(item):
    offer = item.offer
    return dict(product_id=offer.product.id, product_name=offer.product.name, unit=offer.product.unit,
                supplier_id=offer.supplier.id, supplier_name=offer.supplier.name,
                source=offer.source, external_id=offer.external_id, url=offer.url,
                price=format(item.price, 'f'), currency=item.currency,
                minimum_quantity=None if item.minimum_quantity is None else format(item.minimum_quantity, 'f'),
                delivery_cost=None if item.delivery_cost is None else format(item.delivery_cost, 'f'),
                extra_cost=None if item.extra_cost is None else format(item.extra_cost, 'f'),
                delivery_days=item.delivery_days, observed_at=timestamp(item.observed_at), availability=item.availability)
