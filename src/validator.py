from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .canonical import canonical_value, row_canonical
from .db import fetchall, fetchone, iter_rows
from .schema import TableSchema
from .type_mapping import qualified_table, quote_ident

logger = logging.getLogger(__name__)


@dataclass
class SampleMismatch:
    key: str
    source: str
    target: str


@dataclass
class TableCheckResult:
    table: str
    source_count: int
    target_count: int
    count_match: bool
    source_checksum: str
    target_checksum: str
    checksum_match: bool
    sample_checked: int
    sample_mismatches: List[SampleMismatch] = field(default_factory=list)
    passed: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "table": self.table,
            "source_count": self.source_count,
            "target_count": self.target_count,
            "count_match": self.count_match,
            "source_checksum": self.source_checksum,
            "target_checksum": self.target_checksum,
            "checksum_match": self.checksum_match,
            "sample_checked": self.sample_checked,
            "sample_mismatches": [
                {"key": m.key, "source": m.source, "target": m.target}
                for m in self.sample_mismatches[:10]
            ],
            "passed": self.passed,
            "error": self.error,
        }


def _xor_hex(acc: int, canonical_row: str) -> int:
    digest = hashlib.sha256(canonical_row.encode("utf-8")).digest()[:8]
    return acc ^ int.from_bytes(digest, "big")


def _select_sql(table: TableSchema, qualified: str) -> str:
    cols = ", ".join(quote_ident(c.name) for c in table.columns)
    # MySQL 端 qualified 可能是 `t`，列也用反引号。调用方自己拼。
    return f"SELECT {cols} FROM {qualified}"


def mysql_count(conn, table: TableSchema) -> int:
    row = fetchone(conn, f"SELECT COUNT(*) FROM `{table.name}`")
    return int(row[0])


def pg_count(conn, schema: str, table: TableSchema) -> int:
    row = fetchone(conn, f"SELECT COUNT(*) FROM {qualified_table(schema, table.name)}")
    return int(row[0])


def stream_checksum(conn, sql: str, table: TableSchema, chunk_size: int) -> str:
    acc = 0
    n = 0
    for row in iter_rows(conn, sql):
        acc = _xor_hex(acc, row_canonical(list(row), table.columns))
        n += 1
        if n % (chunk_size * 10) == 0:
            logger.info("%s checksum 已扫描 %s 行", table.name, n)
    return f"{acc:016x}"


def mysql_checksum(conn, table: TableSchema, chunk_size: int) -> str:
    cols = ", ".join(f"`{c.name}`" for c in table.columns)
    return stream_checksum(conn, f"SELECT {cols} FROM `{table.name}`", table, chunk_size)


def pg_checksum(conn, schema: str, table: TableSchema, chunk_size: int) -> str:
    cols = ", ".join(quote_ident(c.name) for c in table.columns)
    return stream_checksum(
        conn,
        f"SELECT {cols} FROM {qualified_table(schema, table.name)}",
        table,
        chunk_size,
    )


def _format_key(row: tuple, pk_idx: List[int], table: TableSchema) -> str:
    parts = []
    for idx in pk_idx:
        parts.append(f"{table.columns[idx].name}={canonical_value(row[idx], table.columns[idx])}")
    return ",".join(parts)


def sample_compare(
    mysql_conn,
    pg_conn,
    schema: str,
    table: TableSchema,
    sample_size: int,
) -> tuple[int, List[SampleMismatch]]:
    if sample_size <= 0:
        return 0, []
    if not table.primary_key:
        logger.warning("%s 无主键，跳过按键抽样，只保留行数和 checksum", table.name)
        return 0, []

    pk_cols = ", ".join(f"`{c}`" for c in table.primary_key)
    keys = fetchall(
        mysql_conn,
        f"SELECT {pk_cols} FROM `{table.name}` ORDER BY {pk_cols} LIMIT %s",
        (sample_size,),
    )
    if not keys:
        return 0, []

    pk_idx = [i for i, col in enumerate(table.columns) if col.name in table.primary_key]
    mysql_cols = ", ".join(f"`{c.name}`" for c in table.columns)
    pg_cols = ", ".join(quote_ident(c.name) for c in table.columns)
    mismatches: List[SampleMismatch] = []

    for key in keys:
        where_mysql = " AND ".join(f"`{col}` = %s" for col in table.primary_key)
        where_pg = " AND ".join(f"{quote_ident(col)} = %s" for col in table.primary_key)
        src = fetchone(mysql_conn, f"SELECT {mysql_cols} FROM `{table.name}` WHERE {where_mysql}", key)
        dst = fetchone(
            pg_conn,
            f"SELECT {pg_cols} FROM {qualified_table(schema, table.name)} WHERE {where_pg}",
            key,
        )
        src_c = row_canonical(list(src), table.columns) if src else "<missing>"
        dst_c = row_canonical(list(dst), table.columns) if dst else "<missing>"
        if src_c != dst_c:
            mismatches.append(
                SampleMismatch(
                    key=_format_key(src or dst or key, pk_idx, table) if (src or dst) else str(key),
                    source=src_c,
                    target=dst_c,
                )
            )
    return len(keys), mismatches


def validate_table(
    mysql_conn,
    pg_conn,
    schema: str,
    table: TableSchema,
    sample_size: int,
    chunk_size: int,
) -> TableCheckResult:
    try:
        source_count = mysql_count(mysql_conn, table)
        target_count = pg_count(pg_conn, schema, table)
        source_checksum = mysql_checksum(mysql_conn, table, chunk_size)
        target_checksum = pg_checksum(pg_conn, schema, table, chunk_size)
        sampled, mismatches = sample_compare(mysql_conn, pg_conn, schema, table, sample_size)
        count_match = source_count == target_count
        checksum_match = source_checksum == target_checksum
        passed = count_match and checksum_match and not mismatches
        result = TableCheckResult(
            table=table.name,
            source_count=source_count,
            target_count=target_count,
            count_match=count_match,
            source_checksum=source_checksum,
            target_checksum=target_checksum,
            checksum_match=checksum_match,
            sample_checked=sampled,
            sample_mismatches=mismatches,
            passed=passed,
        )
        logger.info(
            "校验 %s: count %s/%s checksum %s sample_mismatch=%s passed=%s",
            table.name,
            source_count,
            target_count,
            "match" if checksum_match else "DIFF",
            len(mismatches),
            passed,
        )
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("校验 %s 失败", table.name)
        return TableCheckResult(
            table=table.name,
            source_count=-1,
            target_count=-1,
            count_match=False,
            source_checksum="",
            target_checksum="",
            checksum_match=False,
            sample_checked=0,
            passed=False,
            error=str(exc),
        )
