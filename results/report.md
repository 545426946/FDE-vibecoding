# MySQL → YMatrix 迁移校验报告

生成时间：2026-09-24T09:43:06

## 总览

- 迁移成功表：8
- 迁移失败表：0
- 校验通过表：8
- 校验未通过表：0

## 迁移成功表

| 表 | 导出行数 | COPY rowcount |
|---|---:|---:|
| edge_empty | 0 | 0 |
| edge_nulls | 4 | 4 |
| edge_types | 3 | 3 |
| order_items | 5 | 5 |
| orders | 5 | 5 |
| payments | 3 | 3 |
| products | 4 | 4 |
| users | 5 | 5 |

## 迁移失败表

无

## 行数对比

| 表 | 源行数 | 目标行数 | 是否一致 |
|---|---:|---:|---|
| edge_empty | 0 | 0 | 是 |
| edge_nulls | 4 | 4 | 是 |
| edge_types | 3 | 3 | 是 |
| order_items | 5 | 5 | 是 |
| orders | 5 | 5 | 是 |
| payments | 3 | 3 | 是 |
| products | 4 | 4 | 是 |
| users | 5 | 5 | 是 |

## checksum 对比

| 表 | 源 checksum | 目标 checksum | 是否一致 |
|---|---|---|---|
| edge_empty | `0000000000000000` | `0000000000000000` | 是 |
| edge_nulls | `e63c404965ec726f` | `e63c404965ec726f` | 是 |
| edge_types | `3409919d1b346506` | `3409919d1b346506` | 是 |
| order_items | `a9632d73ce26eb87` | `a9632d73ce26eb87` | 是 |
| orders | `87fb7ce158827298` | `87fb7ce158827298` | 是 |
| payments | `196f19dd5b900f3a` | `196f19dd5b900f3a` | 是 |
| products | `c96de6d5114f1f92` | `c96de6d5114f1f92` | 是 |
| users | `5be0d876c08f27bb` | `5be0d876c08f27bb` | 是 |

## 不一致样例

无

## 字段类型映射风险

- happened_at: DATETIME 映射为 TIMESTAMP WITHOUT TIME ZONE。MySQL DATETIME 无时区，目标库不要改成 TIMESTAMPTZ，否则会平移小时
- id: UNSIGNED INT 映射为 BIGINT，避免 2^31 以上溢出
- tiny_flag: TINYINT 映射为 SMALLINT，而不是 BOOLEAN，避免非 0/1 值写入失败
- enum_status: ENUM 映射为 VARCHAR(32)，约束被丢掉，目标库不再拒绝非法枚举值
- event_time: DATETIME 映射为 TIMESTAMP WITHOUT TIME ZONE。MySQL DATETIME 无时区，目标库不要改成 TIMESTAMPTZ，否则会平移小时
- ts_col: MySQL TIMESTAMP 内部按 UTC 存，这里按 TIMESTAMP WITHOUT TIME ZONE 保字面值，不自动加时区，避免校验对不上
- ordered_at: DATETIME 映射为 TIMESTAMP WITHOUT TIME ZONE。MySQL DATETIME 无时区，目标库不要改成 TIMESTAMPTZ，否则会平移小时
- paid_at: MySQL TIMESTAMP 内部按 UTC 存，这里按 TIMESTAMP WITHOUT TIME ZONE 保字面值，不自动加时区，避免校验对不上
- created_at: DATETIME 映射为 TIMESTAMP WITHOUT TIME ZONE。MySQL DATETIME 无时区，目标库不要改成 TIMESTAMPTZ，否则会平移小时
- updated_at: MySQL TIMESTAMP 内部按 UTC 存，这里按 TIMESTAMP WITHOUT TIME ZONE 保字面值，不自动加时区，避免校验对不上

## 后续增量迁移建议

- 本工具默认做全量：抽 CSV → COPY。适合首次切换和一次性校对。
- 增量不要在本工具里“猜 binlog”。建议：
  1. 源表有可靠更新时间或自增主键时，按水位线拉取 `WHERE id > :last_id` 或 `WHERE updated_at >= :watermark`；
  2. 需要更低延迟时，改用 Flink CDC / 官方同步工具，本工具只保留校验；
  3. 增量写入前先对主键做存在性判断，冲突默认失败并出清单，禁止静默覆盖源库，也禁止未经确认覆盖目标已有行。
- 切流前至少再跑一轮全量 checksum；对不上就不要切。

## 备注

图形界面：仅迁移 8 张指定表 (edge_empty, edge_nulls, edge_types, order_items, orders, payments, products, users)
