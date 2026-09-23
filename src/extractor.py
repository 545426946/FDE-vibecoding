import csv
import logging
from pathlib import Path
from typing import List

from .canonical import csv_cell
from .db import iter_rows
from .schema import TableSchema

logger = logging.getLogger(__name__)


def export_csv(mysql_conn, table: TableSchema, csv_path: Path) -> int:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    cols = ", ".join(f"`{c.name}`" for c in table.columns)
    order = ""
    if table.primary_key:
        order = " ORDER BY " + ", ".join(f"`{c}`" for c in table.primary_key)
    sql = f"SELECT {cols} FROM `{table.name}`{order}"
    row_count = 0
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        for row in iter_rows(mysql_conn, sql):
            writer.writerow([csv_cell(row[i], table.columns[i]) for i in range(len(table.columns))])
            row_count += 1
    logger.info("导出 %s.%s -> %s，%s 行", table.schema, table.name, csv_path, row_count)
    return row_count
