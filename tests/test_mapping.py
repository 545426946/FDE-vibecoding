from decimal import Decimal
from datetime import datetime

from src.canonical import canonical_value
from src.loader import runtime_ddl
from src.schema import ColumnSchema, TableSchema
from src.type_mapping import generate_create_table, map_column
from src.validator import _xor_hex


def col(**kwargs) -> ColumnSchema:
    base = {
        "name": "c",
        "data_type": "int",
        "column_type": "int(11)",
        "nullable": True,
    }
    base.update(kwargs)
    return ColumnSchema(**base)


def test_int_and_unsigned_int():
    assert map_column(col(data_type="int", unsigned=False)).pg_type == "INTEGER"
    mapped = map_column(col(data_type="int", unsigned=True, column_type="int unsigned"))
    assert mapped.pg_type == "BIGINT"
    assert mapped.warnings


def test_decimal_and_datetime():
    dec = map_column(
        col(data_type="decimal", column_type="decimal(10,2)", numeric_precision=10, numeric_scale=2)
    )
    assert dec.pg_type == "NUMERIC(10,2)"
    dt = map_column(col(data_type="datetime", column_type="datetime"))
    assert dt.pg_type == "TIMESTAMP"
    assert "TIME ZONE" in "".join(dt.warnings) or "时区" in "".join(dt.warnings)


def test_tinyint_not_boolean():
    mapped = map_column(col(data_type="tinyint", column_type="tinyint(1)"))
    assert mapped.pg_type == "SMALLINT"
    assert "BOOLEAN" in "".join(mapped.warnings)


def test_unsupported_blob():
    mapped = map_column(col(data_type="blob", column_type="blob"))
    assert mapped.unsupported


def test_canonical_decimal_keeps_scale():
    column = col(data_type="decimal", numeric_scale=2)
    assert canonical_value(Decimal("1.5"), column) == "1.50"
    assert canonical_value("1.5", column) == "1.50"
    assert canonical_value(None, column) == r"\N"


def test_canonical_datetime_truncates_microseconds():
    column = col(data_type="datetime")
    value = datetime(2026, 7, 1, 12, 0, 0, 123456)
    assert canonical_value(value, column) == "2026-07-01 12:00:00"


def test_ymatrix_ddl_distributed_by_pk():
    table = TableSchema(
        schema="biz",
        name="users",
        columns=[
            col(name="id", data_type="int", nullable=False),
            col(name="name", data_type="varchar", column_type="varchar(64)", char_length=64, nullable=False),
        ],
        primary_key=["id"],
    )
    ddl, warnings, unsupported = generate_create_table(table, "public", "ymatrix")
    assert unsupported == []
    assert "DISTRIBUTED BY" in ddl
    assert '"id"' in ddl
    pg_ddl = runtime_ddl(ddl, "postgresql")
    assert "DISTRIBUTED" not in pg_ddl
    assert pg_ddl.strip().endswith(";")


def test_checksum_order_independent():
    a = _xor_hex(0, "1|a")
    a = _xor_hex(a, "2|b")
    b = _xor_hex(0, "2|b")
    b = _xor_hex(b, "1|a")
    assert f"{a:016x}" == f"{b:016x}"
    c = _xor_hex(0, "1|a")
    c = _xor_hex(c, "2|c")
    assert f"{a:016x}" != f"{c:016x}"
