from dataclasses import replace
from decimal import Decimal
import pytest
from prices_analyzer.models import DataError
from prices_analyzer.validation import as_row, parse_row, observation_time, decimal_value


@pytest.mark.parametrize('field,value',[
    ('price','-1'),('price','NaN'),('price','Infinity'),('price','1,20'),
    ('minimum_quantity','0'),('delivery_cost','-1'),('extra_cost','-1'),
    ('delivery_days','1.5'),('delivery_days','-1'),('currency','XXX'),
    ('unit','box'),('product_id','paper'),('product_name',''),('supplier_id',''),
    ('url','javascript:alert(1)'),('observed_at','2026-11-22T12:00:00'),
    ('observed_at','2026-02-30T12:00:00Z'),('availability','maybe')])
def test_invalid_values(records,field,value):
    with pytest.raises(DataError):
        parse_row({**as_row(records[0]),field:value})


def test_unknown_differs_from_zero(records):
    row = as_row(records[0])
    unknown = parse_row({**row,'delivery_cost':''})
    zero = parse_row({**row,'delivery_cost':'0'})
    assert unknown.delivery_cost is None
    assert zero.delivery_cost == Decimal(0)
    assert observation_time('2026-11-22T12:00:00+03:00') == observation_time('2026-11-22T09:00:00Z')


def test_no_float_or_excess_precision():
    for value in (0.1,'0.'+'1'*29):
        with pytest.raises(DataError):
            decimal_value(value,'price')
