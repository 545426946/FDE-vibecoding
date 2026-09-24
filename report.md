# 方案与实现报告

## 1. 方案设计

客户要的不是「表已经 COPY 进去了」，而是「迁完以后数对得上，对不上能指出是哪张表、哪一行、哪类类型风险」。所以工具拆成四段，每段都可单独跑：

1. **读结构**：从 MySQL `information_schema` 取列、空值、精度、主键。
2. **生成 DDL**：用白名单做类型映射，YMatrix 方言补 `DISTRIBUTED BY`。
3. **搬数据**：源库只读导出 CSV，目标库 `COPY FROM STDIN`。目标表已存在时由 `if_exists` 决定：客户库用 `fail`，可丢弃的 Demo 才用 `replace`。失败不改源库。
4. **校验**：行数 → 规范化 checksum → 主键抽样。三道门都过才算通过。

源库 Demo 是 Docker 里的 MySQL 8.4。开发时用社区 PostgreSQL 先跑通映射和失败路径；提交时的目标是 Docker 里的 MatrixDB 4.8.12 community，`dialect` 和 `runtime` 都是 `ymatrix`，`DISTRIBUTED BY` 在这套库上执行过。连的是 PostgreSQL 协议，工具本身不绑定某台机器。

数据流：

```
MySQL (只读)
  -> information_schema / SELECT
  -> CSV (\N 表示 NULL，DECIMAL/时间已规范化)
  -> YMatrix COPY FROM STDIN
  -> 行数 + checksum + 抽样
  -> results/report.md
```

## 2. 实现说明

### 2.1 类型映射

`src/type_mapping.py` 是显式规则表，不是「目标库能隐式转就转」。作业要求覆盖的类型：

| MySQL | YMatrix / PG |
|---|---|
| int | INTEGER；UNSIGNED 则 BIGINT |
| bigint | BIGINT；UNSIGNED 则 NUMERIC(20,0) |
| varchar(n) | VARCHAR(n) |
| text | TEXT |
| datetime / timestamp | TIMESTAMP WITHOUT TIME ZONE |
| decimal(p,s) | NUMERIC(p,s) |

刻意没有把 `TINYINT(1)` 映射成 BOOLEAN，因为现场常见 0/1 以外的值。ENUM 降成 VARCHAR，并在报告里写「约束丢失」。BLOB 直接失败。

### 2.2 迁移

- 导出列顺序与建表列顺序一致。
- NULL 写成 `\N`，和 `COPY ... NULL '\N'` 对齐。
- `if_exists=replace` 会 `DROP + CREATE`，适合 Demo；现场第一次建议 `fail`，避免覆盖客户已有目标表。
- 不建外键。多表全量时外键会卡加载顺序，校验也对不齐「业务约束是否迁过去」。这是简化，不是忽略。

### 2.3 校验

跨库不能直接比二进制。MySQL `DECIMAL(10,2)` 的 `1.50` 和 PG `NUMERIC` 的 `1.5` 必须先按列精度量化，再哈希。时间去掉微秒，避免 `DATETIME(0)` 对 `TIMESTAMP` 的假差异。

checksum 用逐行 SHA256 前 8 字节异或，与行顺序无关，可以流式扫，不必把整表塞进内存。它不能替代主键抽样：异或碰撞理论上存在，所以抽样是给人看的证据。

### 2.4 失败处理

- 连接类错误按关键字重试 3 次，指数退避。
- 单表失败默认继续后面的表，报告里分开「成功表 / 失败表」。
- 源库账号在代码路径上只有读。

## 3. 测试过程

1. 单元测试：`python -m pytest -q`
   - UNSIGNED 提升、TINYINT 不转布尔、BLOB 拒绝
   - DECIMAL 补齐小数位、DATETIME 截断微秒
   - YMatrix DDL 含分布键，PostgreSQL runtime 会剥掉
   - checksum 与行顺序无关
2. 在 MatrixDB 4.8.12 上对 8 张指定表做迁移并校验，日志在 `results/report.md`（2026-09-21 09:36:59）
3. 脏数据：`inject-mismatch` 只改目标库，再 `validate`。日志在 `results/stable-mismatch/report.md`（2026-09-20）
4. 连接失败：`demo-conn-fail --port 1`，日志在 `results/stable-conn/run.log`

## 4. 测试结果

以 `sql/mysql_init.sql` 的固定数据和 `results/report.md` 为准。该次迁移成功 8，失败 0；校验通过 8，未通过 0。各表行数如下，checksum 以报告文件为准，不在这里另写一套：

| 表 | 行数 | 备注 |
|---|---:|---|
| users | 5 | 含中文、空串、NULL |
| products | 4 | DECIMAL(10,2) / DECIMAL(18,6) |
| orders | 5 | |
| order_items | 5 | |
| payments | 3 | TIMESTAMP |
| edge_nulls | 4 | NULL / 空串 / 特殊字符 |
| edge_empty | 0 | 空表也必须通过 |
| edge_types | 3 | UNSIGNED / ENUM / TINYINT |

脏数据以 `results/stable-mismatch/report.md` 为准：`products` 行数仍是 4 对 4，checksum 不一致，抽样键 `id=10001` 的价格是 `99.90` 对 `99.91`；`edge_nulls` 行数是源 4、目标 3，键 `id=1` 在目标侧缺失。源库没有被回写。

## 5. 问题和风险

- 分布键已经在 MatrixDB 上执行过，但没有做倾斜、多 Segment 和 mxgate 写入测试。社区 PostgreSQL 也覆盖不了这些。
- 应用层 checksum 在超大表上会拉全表。生产应加时间窗或按主键分段，并避开业务高峰。
- ENUM、UNSIGNED、时区如果在客户库大量出现，需要先出映射评审，而不是直接迁。
- CSV 中转适合本次数据量；客户日增量很大时应改 mxgate / 外部表，工具只保留校验。
- `if_exists=replace` 会丢掉目标表上人工加过的索引和权限，现场默认应改为 `fail`。

## 6. 后续改进方向

- `COPY FROM STDIN` 已在 MatrixDB 4.8.12 上跑通。mxgate 对比和多 Segment 压测这次没做。
- 有稳定水位线的表补增量；无水位线的表继续全量加校验。
- 把类型映射风险做成「阻断 / 告警」两级，阻断项现场必须客户确认。
- 校验任务按主键范围拆分，避免一次扫过大表。
- 输出给客户的报告再加一页：哪些表可以切流，哪些表必须先改口径。
