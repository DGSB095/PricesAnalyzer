from dataclasses import dataclass
from decimal import Decimal, localcontext
from .models import DataError, Observation
from .validation import decimal_value


@dataclass(frozen=True)
class Comparison:
    observation: Observation
    status: str
    reasons: tuple[str, ...]
    quantity: Decimal
    subtotal: Decimal
    total: Decimal | None


def compare(observations, quantity, max_days):
    quantity = decimal_value(quantity, 'quantity', positive=True)
    if isinstance(max_days, bool) or not isinstance(max_days, int) or max_days < 0:
        raise DataError('max_days: требуется целое неотрицательное число')
    items = list(observations)
    keys = {(i.offer.product.id,i.currency,i.offer.product.unit) for i in items}
    if len(keys) > 1:
        raise DataError('Нельзя сравнивать разные товары, валюты или единицы в одной группе')
    results = []
    for item in items:
        reasons, excluded = [], False
        if item.minimum_quantity is None:
            reasons.append('минимальная партия неизвестна')
        elif quantity < item.minimum_quantity:
            reasons.append('количество меньше минимальной партии')
            excluded = True
        if item.delivery_days is None:
            reasons.append('срок поставки неизвестен')
        elif item.delivery_days > max_days:
            reasons.append('превышен срок поставки')
            excluded = True
        if item.availability == 'out_of_stock':
            reasons.append('товар отсутствует в наличии')
            excluded = True
        if item.delivery_cost is None:
            reasons.append('стоимость доставки неизвестна')
        if item.extra_cost is None:
            reasons.append('дополнительные расходы неизвестны')
        with localcontext() as context:
            context.prec = 160
            subtotal = item.price * quantity
            total = None if item.delivery_cost is None or item.extra_cost is None else subtotal + item.delivery_cost + item.extra_cost
        status = 'excluded' if excluded else 'incomplete' if reasons else 'eligible'
        results.append(Comparison(item,status,tuple(reasons),quantity,subtotal,total))
    return sorted(results, key=lambda r: ({'eligible':0,'incomplete':1,'excluded':2}[r.status],
        r.total if r.status == 'eligible' else Decimal(0), r.observation.offer.source,r.observation.offer.external_id))
