from decimal import Decimal, InvalidOperation
from datetime import date, datetime, time
from typing import Any

from .schema import ColumnSchema


NULL_TOKEN = r"\N"


def _is_decimal_type(col: ColumnSchema) -> bool:
    return col.data_type.lower() in {"decimal", "numeric"}


def _is_datetime_type(col: ColumnSchema) -> bool:
    return col.data_type.lower() in {"datetime", "timestamp"}


def _is_date_type(col: ColumnSchema) -> bool:
    return col.data_type.lower() == "date"


def _is_time_type(col: ColumnSchema) -> bool:
    return col.data_type.lower() == "time"


def canonical_value(value: Any, col: ColumnSchema) -> str:
    """跨库比较用的规范化字符串。两边必须走同一套规则，否则 checksum 无意义。"""
    if value is None:
        return NULL_TOKEN

    if _is_decimal_type(col):
        try:
            number = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"列 {col.name} 无法解析为 DECIMAL: {value!r}") from exc
        scale = col.numeric_scale if col.numeric_scale is not None else 0
        quantized = number.quantize(Decimal("1").scaleb(-scale))
        return format(quantized, "f")

    if _is_datetime_type(col):
        if isinstance(value, datetime):
            dt = value.replace(tzinfo=None)
            # 默认按秒对齐。MySQL DATETIME(0) 和 PG TIMESTAMP 微秒差会被当成假不一致。
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        text = str(value).replace("T", " ")
        return text[:19]

    if _is_date_type(col):
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        return str(value)[:10]

    if _is_time_type(col):
        if isinstance(value, time):
            return value.replace(microsecond=0).isoformat()
        return str(value)[:8]

    if isinstance(value, bytes):
        return value.decode("utf-8")

    if isinstance(value, bool):
        return "1" if value else "0"

    return str(value)


def csv_cell(value: Any, col: ColumnSchema) -> str:
    if value is None:
        return NULL_TOKEN
    return canonical_value(value, col)


def row_canonical(values: list[Any], columns: list[ColumnSchema]) -> str:
    parts = [canonical_value(values[i], columns[i]) for i in range(len(columns))]
    return "|".join(parts)
