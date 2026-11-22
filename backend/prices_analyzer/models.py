from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class Product:
    id: str
    name: str
    unit: str


@dataclass(frozen=True)
class Supplier:
    id: str
    name: str


@dataclass(frozen=True)
class Offer:
    source: str
    external_id: str
    product: Product
    supplier: Supplier
    url: str


@dataclass(frozen=True)
class Observation:
    offer: Offer
    price: Decimal
    currency: str
    minimum_quantity: Decimal | None
    delivery_cost: Decimal | None
    extra_cost: Decimal | None
    delivery_days: int | None
    observed_at: datetime
    availability: str | None = None


@dataclass
class Batch:
    records: list[Observation] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    processed: int = 0


@dataclass(frozen=True)
class ImportResult:
    processed: int
    added: int
    duplicates: int
    errors: list[str]
    dry_run: bool = False


class DataError(ValueError):
    pass
