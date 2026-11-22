import csv
from ..models import Batch, DataError
from ..validation import FIELDS, parse_row


def read_csv(path):
    batch = Batch()
    with open(path, encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        headers = reader.fieldnames or []
        if len(headers) != len(set(headers)):
            raise DataError("CSV: повторяющиеся заголовки")
        missing = set(FIELDS) - set(headers)
        if missing:
            raise DataError("CSV: отсутствуют столбцы: " + ", ".join(sorted(missing)))
        if set(headers) - set(FIELDS):
            raise DataError("CSV: неизвестные столбцы: " + ", ".join(sorted(set(headers)-set(FIELDS))))
        try:
            for row in reader:
                batch.processed += 1
                try:
                    if None in row or any(v is None for v in row.values()):
                        raise DataError("число полей не совпадает с заголовком")
                    batch.records.append(parse_row(row))
                except DataError as exc:
                    batch.errors.append(f"Строка {reader.line_num}: {exc}")
        except csv.Error as exc:
            batch.processed += 1
            batch.errors.append(f"Строка {reader.line_num}: повреждён CSV: {exc}; дальнейший разбор остановлен")
    return batch
