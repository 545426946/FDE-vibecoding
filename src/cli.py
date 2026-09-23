from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from pathlib import Path

from .config import load_config, parse_table_arg, require_selected_tables
from .db import connect_mysql, connect_target, list_mysql_tables
from .logging_setup import setup_logging
from .pipeline import inspect_all, migrate_tables, validate_tables
from .reporter import write_reports
from .type_mapping import generate_create_table

logger = logging.getLogger(__name__)


def _cfg(args):
    cfg = load_config(args.config)
    if getattr(args, "results_dir", None):
        cfg.output.results_dir = args.results_dir
    if getattr(args, "tables", None):
        cfg.migrate.tables = parse_table_arg(args.tables)
    if getattr(args, "if_exists", None):
        cfg.migrate.if_exists = args.if_exists
    if getattr(args, "require_tables", True):
        cfg.migrate.tables = require_selected_tables(cfg.migrate.tables)
    setup_logging(cfg.output.results_dir, cfg.output.log_level)
    return cfg


def cmd_inspect(args) -> int:
    cfg = _cfg(args)
    tables = inspect_all(cfg)
    payload = []
    for table in tables:
        payload.append(
            {
                "table": table.name,
                "primary_key": table.primary_key,
                "columns": [
                    {
                        "name": c.name,
                        "mysql_type": c.column_type,
                        "nullable": c.nullable,
                    }
                    for c in table.columns
                ],
            }
        )
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    out = Path(cfg.output.results_dir) / "schema.json"
    out.write_text(text, encoding="utf-8")
    print(text)
    logger.info("表结构已写入 %s", out)
    return 0


def cmd_generate_ddl(args) -> int:
    cfg = _cfg(args)
    tables = inspect_all(cfg)
    ddl_dir = Path(cfg.output.results_dir) / "ddl"
    ddl_dir.mkdir(parents=True, exist_ok=True)
    for table in tables:
        ddl, warnings, unsupported = generate_create_table(
            table, cfg.target.schema, cfg.target.dialect
        )
        path = ddl_dir / f"{table.name}.sql"
        if unsupported:
            path.write_text("-- unsupported\n" + "\n".join(unsupported), encoding="utf-8")
            logger.error("表 %s 无法生成 DDL: %s", table.name, unsupported)
            continue
        path.write_text(ddl, encoding="utf-8")
        for warn in warnings:
            logger.warning(warn)
        print(f"写入 {path}")
    return 0


def cmd_migrate(args) -> int:
    cfg = _cfg(args)
    results, _ok = migrate_tables(cfg)
    failed = [r for r in results if r.status != "success"]
    for item in results:
        print(f"{item.table}: {item.status} rows={item.exported_rows} err={item.error}")
    return 1 if failed else 0


def cmd_validate(args) -> int:
    cfg = _cfg(args)
    checks = validate_tables(cfg)
    for item in checks:
        print(
            f"{item.table}: passed={item.passed} count={item.source_count}/{item.target_count} "
            f"checksum={'ok' if item.checksum_match else 'DIFF'} sample_mismatch={len(item.sample_mismatches)}"
        )
    write_reports(Path(cfg.output.results_dir), [], checks, {"notes": "仅校验"})
    return 0 if all(c.passed for c in checks) else 1


def cmd_run_all(args) -> int:
    cfg = _cfg(args)
    migrate_results, ok_tables = migrate_tables(cfg)
    checks = validate_tables(cfg, ok_tables if ok_tables else None)
    write_reports(
        Path(cfg.output.results_dir),
        migrate_results,
        checks,
        {
            "source": f"{cfg.source.host}:{cfg.source.port}/{cfg.source.database}",
            "target": f"{cfg.target.host}:{cfg.target.port}/{cfg.target.database}",
            "dialect": cfg.target.dialect,
            "runtime": cfg.target.runtime,
            "notes": "全量迁移 + 行数 / checksum / 抽样校验",
        },
    )
    failed_migrate = any(r.status != "success" for r in migrate_results)
    failed_check = any(not c.passed for c in checks)
    return 1 if (failed_migrate or failed_check) else 0


def cmd_inject_mismatch(args) -> int:
    cfg = _cfg(args)
    conn = connect_target(
        cfg.target, cfg.migrate.retries, cfg.migrate.retry_backoff_seconds, logger
    )
    try:
        schema = cfg.target.schema
        with conn.cursor() as cur:
            cur.execute(
                f'UPDATE "{schema}"."products" SET "price" = "price" + 0.01 WHERE "id" = 10001'
            )
            cur.execute(f'DELETE FROM "{schema}"."edge_nulls" WHERE "id" = 1')
        conn.commit()
        print("已构造目标库脏数据：products.price +0.01，删除 edge_nulls.id=1")
        print("请接着执行: python -m src.cli validate --config", args.config)
    finally:
        conn.close()
    return 0


def cmd_demo_conn_fail(args) -> int:
    cfg = _cfg(args)
    cfg.source.port = args.port
    try:
        connect_mysql(cfg.source, retries=3, backoff=0.2, logger=logger)
        print("意外连接成功")
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"连接失败（已重试）：{exc}")
        return 0


def cmd_reset_export(args) -> int:
    cfg = _cfg(args)
    path = Path(cfg.migrate.csv_dir)
    if path.exists():
        shutil.rmtree(path)
        print(f"已删除 {path}")
    return 0


def cmd_list_tables(args) -> int:
    cfg = _cfg(args)
    mysql = connect_mysql(
        cfg.source, cfg.migrate.retries, cfg.migrate.retry_backoff_seconds, logger
    )
    try:
        names = list_mysql_tables(mysql, cfg.source.database)
    finally:
        mysql.close()
    selected = set(cfg.migrate.tables)
    print(f"源库 {cfg.source.database} 共 {len(names)} 张表（* 表示已在 migrate.tables / --tables 中勾选）")
    for name in names:
        mark = "*" if name in selected else " "
        print(f"[{mark}] {name}")
    if not names:
        print("(没有用户表)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--config", default="config.yaml")
    parent.add_argument("--results-dir", default=None, help="覆盖 config 里的 output.results_dir")
    parent.add_argument(
        "--tables",
        default=None,
        help="逗号分隔的表名，覆盖 yaml 里的 migrate.tables。只迁这些表，不会自动迁全库。",
    )
    parent.add_argument(
        "--if-exists",
        dest="if_exists",
        choices=("fail", "truncate", "replace"),
        default=None,
        help="覆盖 yaml 的 migrate.if_exists。Demo 重复跑同一张表请用 truncate。",
    )

    parser = argparse.ArgumentParser(description="MySQL 到 YMatrix 迁移与校验工具")
    sub = parser.add_subparsers(dest="command", required=True)

    for name, func in [
        ("inspect", cmd_inspect),
        ("generate-ddl", cmd_generate_ddl),
        ("migrate", cmd_migrate),
        ("validate", cmd_validate),
        ("run-all", cmd_run_all),
        ("inject-mismatch", cmd_inject_mismatch),
        ("reset-export", cmd_reset_export),
    ]:
        sub.add_parser(name, parents=[parent]).set_defaults(func=func, require_tables=True)

    listed = sub.add_parser("list-tables", parents=[parent], help="列出源库全部表，不迁移")
    listed.set_defaults(func=cmd_list_tables, require_tables=False)

    fail = sub.add_parser("demo-conn-fail", parents=[parent])
    fail.add_argument("--port", type=int, default=1)
    fail.set_defaults(func=cmd_demo_conn_fail, require_tables=False)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
