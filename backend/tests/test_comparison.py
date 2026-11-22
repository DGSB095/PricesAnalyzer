from dataclasses import replace
from decimal import Decimal
import pytest
from prices_analyzer.comparison import compare
from prices_analyzer.models import DataError


def test_cost_ranking_and_limits(records):
    items = [records[i] for i in (0,2,3,4,5)]
    results = compare(items,'10',7)
    eligible = [r for r in results if r.status == 'eligible']
    assert [r.total for r in eligible] == [Decimal('1300'),Decimal('2500')]
    assert eligible[0].observation.offer.external_id == 'paper-b'
    by_id = {r.observation.offer.external_id:r for r in results}
    assert by_id['paper-c'].status == by_id['paper-e'].status == 'excluded'
    assert by_id['paper-d'].status == 'incomplete' and by_id['paper-d'].total is None
    assert by_id['paper-c'].quantity == Decimal('10')


def test_unknown_constraints_and_boundaries(records):
    base = replace(records[0],minimum_quantity=Decimal(10),delivery_days=7,delivery_cost=Decimal(0),extra_cost=Decimal(0))
    assert compare([base],'10',7)[0].status == 'eligible'
    for field in ('minimum_quantity','delivery_days','delivery_cost','extra_cost'):
        assert compare([replace(base,**{field:None})],'10',7)[0].status == 'incomplete'
    assert compare([replace(base,availability='out_of_stock')],'10',7)[0].status == 'excluded'


def test_exact_decimal_cost(records):
    item = replace(records[0],price=Decimal('0.1234567890123456789012345678'),
                   delivery_cost=Decimal('0.0000000000000000000000000001'),extra_cost=Decimal(0))
    assert compare([item],'10',7)[0].total == Decimal('1.2345678901234567890123456781')


def test_incomparable_groups_rejected(records):
    item = records[0]
    variants = [replace(item,currency='GBP'),
        replace(item,offer=replace(item.offer,product=replace(item.offer.product,unit='kg'))),
        replace(item,offer=replace(item.offer,product=replace(item.offer.product,id='demo:other')))]
    for variant in variants:
        with pytest.raises(DataError,match='Нельзя сравнивать'):
            compare([item,variant],'10',7)
    for quantity in ('0','-1','NaN'):
        with pytest.raises(DataError):
            compare([item],quantity,7)
