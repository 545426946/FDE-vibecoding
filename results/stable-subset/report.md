# MySQL → YMatrix 迁移校验报告

生成时间：2026-09-20T18:31:44

## 总览

- 迁移成功表：2
- 迁移失败表：0
- 校验通过表：2
- 校验未通过表：0

## 迁移成功表

| 表 | 导出行数 | COPY rowcount |
|---|---:|---:|
| users | 5 | 5 |
| orders | 5 | 5 |

## 迁移失败表

无

## 行数对比

| 表 | 源行数 | 目标行数 | 是否一致 |
|---|---:|---:|---|
| users | 5 | 5 | 是 |
| orders | 5 | 5 | 是 |

## checksum 对比

| 表 | 源 checksum | 目标 checksum | 是否一致 |
|---|---|---|---|
| users | `a2c5ebe633c1e647` | `a2c5ebe633c1e647` | 是 |
| orders | `87fb7ce158827298` | `87fb7ce158827298` | 是 |

## 不一致样例

无

## 字段类型映射风险

- created_at: DATETIME 映射为 TIMESTAMP WITHOUT TIME ZONE。MySQL DATETIME 无时区，目标库不要改成 TIMESTAMPTZ，否则会平移小时
- updated_at: MySQL TIMESTAMP 内部按 UTC 存，这里按 TIMESTAMP WITHOUT TIME ZONE 保字面值，不自动加时区，避免校验对不上
- ordered_at: DATETIME 映射为 TIMESTAMP WITHOUT TIME ZONE。MySQL DATETIME 无时区，目标库不要改成 TIMESTAMPTZ，否则会平移小时

## 后续增量迁移建议

- 本工具默认做全量：抽 CSV → COPY。适合首次切换和一次性校对。
- 增量不要在本工具里“猜 binlog”。建议：
  1. 源表有可靠更新时间或自增主键时，按水位线拉取 `WHERE id > :last_id` 或 `WHERE updated_at >= :watermark`；
  2. 需要更低延迟时，改用 Flink CDC / 官方同步工具，本工具只保留校验；
  3. 增量写入前先对主键做存在性判断，冲突默认失败并出清单，禁止静默覆盖源库，也禁止未经确认覆盖目标已有行。
- 切流前至少再跑一轮全量 checksum；对不上就不要切。

## 备注

全量迁移 + 行数 / checksum / 抽样校验
