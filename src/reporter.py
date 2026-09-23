from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .validator import TableCheckResult

logger = logging.getLogger(__name__)


@dataclass
class TableMigrateResult:
    table: str
    status: str
    exported_rows: int = 0
    loaded_rows: Optional[int] = None
    ddl_path: str = ""
    warnings: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "table": self.table,
            "status": self.status,
            "exported_rows": self.exported_rows,
            "loaded_rows": self.loaded_rows,
            "ddl_path": self.ddl_path,
            "warnings": self.warnings,
            "error": self.error,
        }


def write_reports(
    results_dir: Path,
    migrate_results: List[TableMigrateResult],
    check_results: List[TableCheckResult],
    extra: Dict[str, Any],
) -> Path:
    results_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "extra": extra,
        "migrate": [item.to_dict() for item in migrate_results],
        "validate": [item.to_dict() for item in check_results],
    }
    json_path = results_dir / "report.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    success = [m for m in migrate_results if m.status == "success"]
    failed = [m for m in migrate_results if m.status != "success"]
    passed = [c for c in check_results if c.passed]
    not_passed = [c for c in check_results if not c.passed]
    mapping_warnings = []
    for item in migrate_results:
        mapping_warnings.extend(item.warnings)

    lines = [
        "# MySQL → YMatrix 迁移校验报告",
        "",
        f"生成时间：{payload['generated_at']}",
        "",
        "## 总览",
        "",
        f"- 迁移成功表：{len(success)}",
        f"- 迁移失败表：{len(failed)}",
        f"- 校验通过表：{len(passed)}",
        f"- 校验未通过表：{len(not_passed)}",
        "",
        "## 迁移成功表",
        "",
    ]
    if success:
        lines += ["| 表 | 导出行数 | COPY rowcount |", "|---|---:|---:|"]
        for item in success:
            lines.append(f"| {item.table} | {item.exported_rows} | {item.loaded_rows} |")
    else:
        lines.append("无")

    lines += ["", "## 迁移失败表", ""]
    if failed:
        lines += ["| 表 | 原因 |", "|---|---|"]
        for item in failed:
            lines.append(f"| {item.table} | {item.error} |")
    else:
        lines.append("无")

    lines += ["", "## 行数对比", "", "| 表 | 源行数 | 目标行数 | 是否一致 |", "|---|---:|---:|---|"]
    for item in check_results:
        lines.append(
            f"| {item.table} | {item.source_count} | {item.target_count} | {'是' if item.count_match else '否'} |"
        )

    lines += ["", "## checksum 对比", "", "| 表 | 源 checksum | 目标 checksum | 是否一致 |", "|---|---|---|---|"]
    for item in check_results:
        lines.append(
            f"| {item.table} | `{item.source_checksum}` | `{item.target_checksum}` | {'是' if item.checksum_match else '否'} |"
        )

    lines += ["", "## 不一致样例", ""]
    samples = [c for c in check_results if c.sample_mismatches]
    if not samples:
        lines.append("无")
    else:
        for item in samples:
            lines.append(f"### {item.table}")
            for mismatch in item.sample_mismatches[:5]:
                lines.append(f"- 键：`{mismatch.key}`")
                lines.append(f"  - 源：`{mismatch.source}`")
                lines.append(f"  - 目标：`{mismatch.target}`")
            lines.append("")

    lines += ["", "## 字段类型映射风险", ""]
    if mapping_warnings:
        for warn in mapping_warnings:
            lines.append(f"- {warn}")
    else:
        lines.append("本次所选表示例类型均在白名单内，仍需在真实 YMatrix 上复验 UNSIGNED / ENUM / 时区。")

    lines += [
        "",
        "## 后续增量迁移建议",
        "",
        "- 本工具默认做全量：抽 CSV → COPY。适合首次切换和一次性校对。",
        "- 增量不要在本工具里“猜 binlog”。建议：",
        "  1. 源表有可靠更新时间或自增主键时，按水位线拉取 `WHERE id > :last_id` 或 `WHERE updated_at >= :watermark`；",
        "  2. 需要更低延迟时，改用 Flink CDC / 官方同步工具，本工具只保留校验；",
        "  3. 增量写入前先对主键做存在性判断，冲突默认失败并出清单，禁止静默覆盖源库，也禁止未经确认覆盖目标已有行。",
        "- 切流前至少再跑一轮全量 checksum；对不上就不要切。",
        "",
    ]
    if extra.get("notes"):
        lines += ["## 备注", "", extra["notes"], ""]

    md_path = results_dir / "report.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("报告已写入 %s 和 %s", json_path, md_path)
    return md_path
