# AI 使用说明

## 1. 使用了哪些 AI 工具

- Cursor（本作业主工具）：拆任务、写脚手架、补测试、改报告结构。
- 没有把分数、校验结论、能不能写库交给模型口算。所有通过 / 失败都以脚本跑出来的 `results/` 为准。

## 2. 关键 Prompt 示例

实际约束会先写在对话里，再让模型改代码。核心几条是：

```text
做 MySQL 到 YMatrix 的最小迁移校验工具。
源库只读，禁止覆盖源数据。
类型映射必须是显式规则，TINYINT(1) 不要映射成 BOOLEAN。
DATETIME 不要转 TIMESTAMPTZ。
校验至少包含行数、规范化 checksum、主键抽样。
单表失败要留下原因并继续其他表。
本地用 PostgreSQL 做协议兼容运行时，但生成的 DDL 仍要带 DISTRIBUTED BY。
不要编造没跑过的性能数字。
```

生成报告时用过的约束：

```text
report.md 按作业模板写：方案设计、实现说明、测试过程、测试结果、风险、后续改进。
assessment.md 必须写清选了什么、放弃了什么。
异常场景要能真正构造：写入后的脏数据、连接失败、空表、NULL。
```

## 3. AI 帮助完成了哪些部分

- 项目目录、CLI 子命令、Docker Compose 初稿
- 类型映射表和 DDL 拼接
- CSV / COPY 管道、校验流程、Markdown 报告模板
- pytest 用例骨架
- README / report / assessment 的章节编排

我自己定的部分：

- 选题和第 1 / 2 / 4 / 5 题的取舍
- 源库只读、不覆盖、对不上只出清单
- TINYINT、UNSIGNED、时区、ENUM 的处理原则
- 用 PostgreSQL runtime 剥掉 `DISTRIBUTED BY`，而不是假装本地就是 YMatrix 集群
- 正常 / 脏数据 / 连接失败三套可复现实验怎么跑

## 4. AI 生成内容中出现过哪些问题

1. 容易把 `TINYINT(1)` 直接映射成 `BOOLEAN`。这在 MySQL 业务里会把 2、127 写成失败或截断。
2. 容易把 `DATETIME` 映射成 `TIMESTAMPTZ`。本地时区一变，校验会整表对不上。
3. 初稿想用 MySQL `CHECKSUM TABLE` 对 PG。两边算法不同，数字不可比。
4. 有草稿把外键、CDC、mxgate 压测一次写进 v1。一周内跑不完，而且会把「数对不对」淹没在环境问题上。
5. 报告里容易出现没有运行依据的「高性能」「生产可用」。这些我删掉了。

## 5. 你如何验证和修正

- 映射和规范化先用 pytest 锁死，不连库也能发现 TINYINT / DECIMAL / 时区问题。
- Docker 固定样例数据后跑 `run-all`，要求 8 张表行数和 checksum 一致。
- 用 `inject-mismatch` 改目标库，确认工具会失败而不是“看起来差不多”。
- 用错误端口跑 `demo-conn-fail`，确认会重试再报错，而不是堆栈直接甩给客户。
- 生成的 YMatrix DDL 人工看是否带 `DISTRIBUTED BY`；本地执行日志确认 PG 上没有这条子句。

## 6. 如果不使用 AI，预计需要多久完成

- 纯手写可运行闭环（读表、映射、CSV、COPY、三类校验、两份报告）：大约 2 到 3 天。
- 加上异常构造、边界表、文档按作业模板写完：大约 4 到 5 天。
- AI 主要缩短的是脚手架和文档排版。类型规则、校验口径、哪些结论能写进报告，仍然要自己跑、自己看。
