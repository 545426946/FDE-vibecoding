from __future__ import annotations

from typing import Any, Iterable, List, Sequence

import pymysql
import psycopg2
from psycopg2.extensions import connection as PGConnection

from .config import SourceConfig, TargetConfig
from .retry import retry_call
from .schema import ColumnSchema, TableSchema


def connect_mysql(cfg: SourceConfig, retries: int = 3, backoff: float = 0.5, logger=None):
    def _connect():
        return pymysql.connect(
            host=cfg.host,
            port=cfg.port,
            user=cfg.user,
            password=cfg.password,
            database=cfg.database,
            charset=cfg.charset,
            connect_timeout=cfg.connect_timeout,
            read_timeout=30,
            write_timeout=30,
            cursorclass=pymysql.cursors.Cursor,
            autocommit=True,
        )

    return retry_call(_connect, retries, backoff, logger, "连接 MySQL")


def connect_target(cfg: TargetConfig, retries: int = 3, backoff: float = 0.5, logger=None) -> PGConnection:
    def _connect():
        conn = psycopg2.connect(
            host=cfg.host,
            port=cfg.port,
            user=cfg.user,
            password=cfg.password,
            dbname=cfg.database,
            connect_timeout=cfg.connect_timeout,
        )
        conn.autocommit = False
        return conn

    return retry_call(_connect, retries, backoff, logger, "连接目标库")


def list_mysql_tables(mysql_conn, schema_name: str) -> List[str]:
    sql = """
        SELECT TABLE_NAME
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'
        ORDER BY TABLE_NAME
    """
    with mysql_conn.cursor() as cur:
        cur.execute(sql, (schema_name,))
        return [row[0] for row in cur.fetchall()]


def inspect_table(mysql_conn, schema_name: str, table_name: str) -> TableSchema:
    sql = """
        SELECT
            COLUMN_NAME,
            DATA_TYPE,
            COLUMN_TYPE,
            IS_NULLABLE,
            CHARACTER_MAXIMUM_LENGTH,
            NUMERIC_PRECISION,
            NUMERIC_SCALE,
            DATETIME_PRECISION,
            EXTRA
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
        ORDER BY ORDINAL_POSITION
    """
    with mysql_conn.cursor() as cur:
        cur.execute(sql, (schema_name, table_name))
        rows = cur.fetchall()
    if not rows:
        raise ValueError(f"源库不存在表 {schema_name}.{table_name}")

    columns: List[ColumnSchema] = []
    for row in rows:
        column_type = row[2] or ""
        columns.append(
            ColumnSchema(
                name=row[0],
                data_type=row[1],
                column_type=column_type,
                nullable=(row[3] == "YES"),
                char_length=row[4],
                numeric_precision=row[5],
                numeric_scale=row[6],
                datetime_precision=row[7],
                unsigned="unsigned" in column_type.lower(),
                extra=row[8] or "",
            )
        )

    pk_sql = """
        SELECT COLUMN_NAME
        FROM information_schema.KEY_COLUMN_USAGE
        WHERE TABLE_SCHEMA = %s
          AND TABLE_NAME = %s
          AND CONSTRAINT_NAME = 'PRIMARY'
        ORDER BY ORDINAL_POSITION
    """
    with mysql_conn.cursor() as cur:
        cur.execute(pk_sql, (schema_name, table_name))
        pk_rows = cur.fetchall()
    return TableSchema(
        schema=schema_name,
        name=table_name,
        columns=columns,
        primary_key=[r[0] for r in pk_rows],
    )


def fetchall(conn, sql: str, params: Sequence[Any] | None = None) -> list:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())


def fetchone(conn, sql: str, params: Sequence[Any] | None = None):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def iter_rows(conn, sql: str, params: Sequence[Any] | None = None) -> Iterable[tuple]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        while True:
            rows = cur.fetchmany(1000)
            if not rows:
                break
            yield from rows
