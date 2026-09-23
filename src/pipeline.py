from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Tuple

from .config import AppConfig, require_selected_tables
from .db import connect_mysql, connect_target, inspect_table
from .extractor import export_csv
from .loader import copy_csv, ensure_schema, prepare_table
from .reporter import TableMigrateResult
from .retry import retry_call
from .schema import TableSchema
from .type_mapping import generate_create_table
from .validator import TableCheckResult, validate_table

logger = logging.getLogger(__name__)


class UnsupportedTypeError(RuntimeError):
    pass


def inspect_all(cfg: AppConfig) -> List[TableSchema]:
    mysql = connect_mysql(
        cfg.source, cfg.migrate.retries, cfg.migrate.retry_backoff_seconds, logger
    )
    try:
        tables = []
        names = require_selected_tables(cfg.migrate.tables)
        logger.info("读取指定表结构: %s", ", ".join(names))
        for name in names:
            tables.append(inspect_table(mysql, cfg.source.database, name))
        return tables
    finally:
        mysql.close()


def migrate_tables(cfg: AppConfig) -> Tuple[List[TableMigrateResult], List[TableSchema]]:
    results_dir = Path(cfg.output.results_dir)
    ddl_dir = results_dir / "ddl"
    ddl_dir.mkdir(parents=True, exist_ok=True)
    csv_dir = Path(cfg.migrate.csv_dir)
    csv_dir.mkdir(parents=True, exist_ok=True)

    names = require_selected_tables(cfg.migrate.tables)
    logger.info("本次只迁移 %s 张指定表（不会搬源库其余表）: %s", len(names), ", ".join(names))

    mysql = connect_mysql(
        cfg.source, cfg.migrate.retries, cfg.migrate.retry_backoff_seconds, logger
    )
    target = connect_target(
        cfg.target, cfg.migrate.retries, cfg.migrate.retry_backoff_seconds, logger
    )
    results: List[TableMigrateResult] = []
    ok_tables: List[TableSchema] = []
    try:
        ensure_schema(target, cfg.target.schema)
        for name in names:
            try:
                table = inspect_table(mysql, cfg.source.database, name)
                ddl, warnings, unsupported = generate_create_table(
                    table, cfg.target.schema, cfg.target.dialect
                )
                if unsupported:
                    raise UnsupportedTypeError("; ".join(unsupported))
                ddl_path = ddl_dir / f"{table.name}.sql"
                ddl_path.write_text(ddl, encoding="utf-8")
                csv_path = csv_dir / f"{table.name}.csv"

                exported = retry_call(
                    lambda: export_csv(mysql, table, csv_path),
                    cfg.migrate.retries,
                    cfg.migrate.retry_backoff_seconds,
                    logger,
                    f"导出 {table.name}",
                )
                retry_call(
                    lambda: prepare_table(
                        target,
                        table,
                        cfg.target.schema,
                        ddl,
                        cfg.migrate.if_exists,
                        cfg.target.runtime,
                    ),
                    cfg.migrate.retries,
                    cfg.migrate.retry_backoff_seconds,
                    logger,
                    f"准备目标表 {table.name}",
                )
                loaded = retry_call(
                    lambda: copy_csv(target, table, cfg.target.schema, csv_path),
                    cfg.migrate.retries,
                    cfg.migrate.retry_backoff_seconds,
                    logger,
                    f"COPY {table.name}",
                )
                results.append(
                    TableMigrateResult(
                        table=name,
                        status="success",
                        exported_rows=exported,
                        loaded_rows=loaded,
                        ddl_path=str(ddl_path),
                        warnings=warnings,
                    )
                )
                ok_tables.append(table)
            except Exception as exc:  # noqa: BLE001
                logger.exception("迁移表 %s 失败", name)
                try:
                    target.rollback()
                except Exception:
                    pass
                results.append(
                    TableMigrateResult(
                        table=name,
                        status="failed",
                        error=str(exc),
                    )
                )
                if not cfg.migrate.continue_on_error:
                    break
        return results, ok_tables
    finally:
        mysql.close()
        target.close()


def validate_tables(cfg: AppConfig, tables: List[TableSchema] | None = None) -> List[TableCheckResult]:
    mysql = connect_mysql(
        cfg.source, cfg.migrate.retries, cfg.migrate.retry_backoff_seconds, logger
    )
    target = connect_target(
        cfg.target, cfg.migrate.retries, cfg.migrate.retry_backoff_seconds, logger
    )
    try:
        if tables is None:
            tables = [
                inspect_table(mysql, cfg.source.database, name)
                for name in require_selected_tables(cfg.migrate.tables)
            ]
        results = []
        for table in tables:
            results.append(
                validate_table(
                    mysql,
                    target,
                    cfg.target.schema,
                    table,
                    cfg.validate.sample_size,
                    cfg.validate.checksum_chunk_size,
                )
            )
        return results
    finally:
        mysql.close()
        target.close()
