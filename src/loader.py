import logging
from pathlib import Path

from .db import fetchone
from .schema import TableSchema
from .type_mapping import qualified_table, quote_ident

logger = logging.getLogger(__name__)


def runtime_ddl(ddl: str, runtime: str) -> str:
    if runtime != "postgresql":
        return ddl
    kept = []
    for line in ddl.splitlines():
        if line.strip().upper().startswith("DISTRIBUTED "):
            continue
        kept.append(line)
    text = "\n".join(kept).rstrip()
    if text.endswith(")"):
        text += ";"
    elif not text.endswith(";"):
        text += ";"
    return text + "\n"


def ensure_schema(pg_conn, schema: str) -> None:
    with pg_conn.cursor() as cur:
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {quote_ident(schema)}")
    pg_conn.commit()


def table_exists(pg_conn, schema: str, table: str) -> bool:
    row = fetchone(
        pg_conn,
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = %s AND table_name = %s
        """,
        (schema, table),
    )
    return row is not None


def prepare_table(pg_conn, table: TableSchema, schema: str, ddl: str, if_exists: str, runtime: str) -> None:
    qname = qualified_table(schema, table.name)
    exists = table_exists(pg_conn, schema, table.name)
    executable = runtime_ddl(ddl, runtime)
    with pg_conn.cursor() as cur:
        if exists and if_exists == "fail":
            raise RuntimeError(f"目标表已存在: {qname}，migrate.if_exists=fail")
        if exists and if_exists == "replace":
            cur.execute(f"DROP TABLE IF EXISTS {qname} CASCADE")
            exists = False
        if not exists:
            cur.execute(executable)
            logger.info("已创建目标表 %s", qname)
        elif if_exists == "truncate":
            cur.execute(f"TRUNCATE TABLE {qname}")
            logger.info("已清空目标表 %s", qname)
    pg_conn.commit()


def copy_csv(pg_conn, table: TableSchema, schema: str, csv_path: Path) -> int:
    qname = qualified_table(schema, table.name)
    col_list = ", ".join(quote_ident(c.name) for c in table.columns)
    copy_sql = (
        f"COPY {qname} ({col_list}) FROM STDIN WITH (FORMAT csv, NULL '\\N', ENCODING 'UTF8')"
    )
    with csv_path.open("r", encoding="utf-8") as fh, pg_conn.cursor() as cur:
        cur.copy_expert(copy_sql, fh)
        rowcount = cur.rowcount
    pg_conn.commit()
    logger.info("COPY 写入 %s，rowcount=%s", qname, rowcount)
    return rowcount
