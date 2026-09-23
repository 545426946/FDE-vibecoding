from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import yaml


@dataclass
class SourceConfig:
    host: str
    port: int
    user: str
    password: str
    database: str
    charset: str = "utf8mb4"
    connect_timeout: int = 5


@dataclass
class TargetConfig:
    dialect: str
    host: str
    port: int
    user: str
    password: str
    database: str
    schema: str = "public"
    connect_timeout: int = 5
    # postgresql: 本地用社区版 PostgreSQL 做协议兼容验证，执行 DDL 时去掉 DISTRIBUTED BY
    # ymatrix: 按 YMatrix / Greenplum 方言原样执行
    runtime: str = "postgresql"


@dataclass
class MigrateConfig:
    tables: List[str]
    if_exists: str = "replace"
    csv_dir: str = "./data/export"
    retries: int = 3
    retry_backoff_seconds: float = 0.5
    continue_on_error: bool = True


@dataclass
class ValidateConfig:
    sample_size: int = 20
    checksum_chunk_size: int = 1000


@dataclass
class OutputConfig:
    results_dir: str = "./results"
    log_level: str = "INFO"


@dataclass
class AppConfig:
    source: SourceConfig
    target: TargetConfig
    migrate: MigrateConfig
    validate: ValidateConfig
    output: OutputConfig
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def project_root(self) -> Path:
        return Path.cwd()


def normalize_tables(tables: List[str] | None) -> List[str]:
    """去空白、去重、保序。空列表表示未选定，不会被当成「迁全库」。"""
    seen = set()
    out: List[str] = []
    for raw in tables or []:
        name = str(raw).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def parse_table_arg(text: str) -> List[str]:
    chunks = str(text).replace(";", ",").replace("\n", ",").split(",")
    return normalize_tables(chunks)


def require_selected_tables(tables: List[str]) -> List[str]:
    names = normalize_tables(tables)
    if not names:
        raise ValueError(
            "未指定要迁移的表。本工具不会默认迁移源库全部表。"
            "请在 config.yaml 的 migrate.tables 列出表名，"
            "或命令行使用 --tables users,orders，或在图形界面勾选。"
        )
    return names


def load_config(path: str) -> AppConfig:
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    source = SourceConfig(**data["source"])
    target = TargetConfig(**data["target"])
    migrate = MigrateConfig(**data["migrate"])
    migrate.tables = normalize_tables(migrate.tables)
    validate = ValidateConfig(**data.get("validate") or {})
    output = OutputConfig(**data.get("output") or {})
    if migrate.if_exists not in {"fail", "replace", "truncate"}:
        raise ValueError("migrate.if_exists 只能是 fail / replace / truncate")
    if target.dialect not in {"ymatrix", "postgresql"}:
        raise ValueError("target.dialect 只能是 ymatrix / postgresql")
    if target.runtime not in {"ymatrix", "postgresql"}:
        raise ValueError("target.runtime 只能是 ymatrix / postgresql")
    return AppConfig(source, target, migrate, validate, output, data)


def save_config(path: str, data: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=False)
