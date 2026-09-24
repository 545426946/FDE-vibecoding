# mysql2ymatrix

按配置把 **MySQL 表批量迁到 YMatrix**（Greenplum / PostgreSQL 协议），并做行数、checksum、主键抽样校验。面向 FDE 现场：先迁过去，再给出「一致 / 不一致」的书面证据。迁失败只出报告，**不写源库**。

本仓库是一份可运行的 Demo，不是生产级 CDC。本地 Docker 只是一种验证环境；真正决定连哪里的是 `config.yaml`（或图形界面里填的连接信息）。

---

## 1. 能做什么

- 读取源库表结构（列类型、空值、主键），按显式规则生成 YMatrix `CREATE TABLE`（含 `DISTRIBUTED BY`）。
- 经 CSV + `COPY ... FROM STDIN` 把数据写入目标库。
- 迁移后做三件事：行数是否一致、规范化 checksum 是否一致、按主键抽样是否一致。
- 输出成功表、失败表、不一致样例、类型映射告警。源库只执行 `SELECT` / 读 `information_schema`。

一次运行的路径：

```
填写源库 + 目标库 + 表名单
        ↓
   inspect 看结构
        ↓
 generate-ddl 审 SQL
        ↓
  migrate（建表 + COPY）
        ↓
  validate（行数 / checksum / 抽样）
        ↓
  results/*/report.md
```

---

## 2. 做不到什么

- 不是整库一键搬迁：只迁 `migrate.tables` 里列出的表。
- 不做 binlog / 实时 CDC，不迁外键、触发器、存储过程、视图、用户权限。
- 不支持 BLOB / BINARY / SET / 空间类型；遇到会失败并写明原因，不会悄悄丢列。
- 配置里没有 SSL、SSH 隧道。两边必须允许**运行本工具的这台机器**直接 TCP 访问。
- checksum 是应用层规范化后的逐行 SHA256 异或，不是 MySQL `CHECKSUM TABLE`。

---

## 3. 安装

需要 Python 3.10+（推荐 3.12），以及能访问源 MySQL、目标 YMatrix 的网络。

```powershell
cd mysql2ymatrix
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item config.example.yaml config.yaml
```

Linux / macOS 把激活命令换成 `source .venv/bin/activate`。之后都在项目根目录、**已激活的虚拟环境**里执行命令。

Windows 上直接敲 `python` 经常落到系统自带的 3.7，没有本项目的依赖，会报 `No module named 'yaml'`。请先看提示符是否带 `(.venv)`，或改用：

```powershell
.\.venv\Scripts\python.exe -m src.gui
.\.venv\Scripts\python.exe -m src.cli run-all --config config.yaml
```

---

## 4. 怎么配才能迁对

工具**不绑定本机 Docker**。`source.host` / `target.host` 填 IP 或域名即可：本机、局域网、VPN 后的客户库都可以。数据流是：

```
MySQL  --(本机导出 CSV)-->  本工具所在电脑  --(COPY STDIN)-->  YMatrix
```

MySQL 和 YMatrix 不必在同一台机器上，但**这一台电脑必须能同时连上两边**。

### 4.1 必改项

| 段 | 字段 | 含义 |
|---|---|---|
| `source` | `host` `port` `user` `password` `database` | 源 MySQL。账号至少要能读指定库的表和 `information_schema` |
| `target` | `host` `port` `user` `password` `database` `schema` | 目标 YMatrix。账号要能建表、`COPY`、查询 |
| `target` | `dialect` / `runtime` | 真 YMatrix 都填 `ymatrix`（保留并执行 `DISTRIBUTED BY`）。若目标只是社区 PostgreSQL，把 `runtime` 改成 `postgresql`，执行时会去掉分布键子句 |
| `migrate` | `tables` | **要迁的表名列表（多选）**。只迁列出的表，不会自动搬源库其余表。图形界面可勾选；命令行可用 `--tables a,b` 覆盖 |
| `migrate` | `if_exists` | 目标已有同名表时怎么办，见下表 |

### 4.2 `if_exists`（写错会伤目标库）

| 值 | 行为 | 适用 |
|---|---|---|
| `fail` | 目标表已存在则失败，不覆盖 | **远程 / 客户库默认用这个** |
| `truncate` | 清空目标表再导入 | 表结构已对齐、只想重灌数据 |
| `replace` | `DROP` 后重建 | 仅限可丢弃的 Demo 库 |

客户库、生产库不要用 `replace`。

### 4.3 远程库示例

```yaml
source:
  host: mysql.example.com      # 或内网 IP
  port: 3306
  user: migrate_ro
  password: "..."
  database: biz
  charset: utf8mb4
  connect_timeout: 10

target:
  dialect: ymatrix
  runtime: ymatrix
  host: ymatrix.example.com
  port: 5432                   # 对方真实端口，不是 Demo 里的映射口
  user: mxadmin
  password: "..."
  database: warehouse
  schema: public
  connect_timeout: 15

migrate:
  tables:
    - orders
    - order_items
  if_exists: fail
  csv_dir: ./data/export
  retries: 3
  retry_backoff_seconds: 0.5
  continue_on_error: true
```

远程迁移前先确认：

1. 本机 `ping` / Telnet（或 Navicat）能连上源端口和目标端口。
2. `tables` 已改成对方表名，不要照抄 Demo 的 `users` / `products`。
3. `if_exists: fail`。
4. 目标库已存在（工具不会 `CREATE DATABASE`）。
5. 防火墙、安全组、白名单包含你这台机器的出口 IP。

本工具不能替你做 SSH 跳板。需要跳板时，先在本机做端口转发，再把 yaml 里的 host/port 指到转发出来的本地端口。

---

## 5. 图形界面（选源库 / 目标库）

可以。项目带一个本地窗口，用来填连接、勾选表、测连通、执行迁移，底层仍是同一套 pipeline，结果同样写入 `config.yaml` 和 `results/report.md`。

```powershell
.\.venv\Scripts\Activate.ps1
python -m src.gui
```

未激活虚拟环境时：

```powershell
.\.venv\Scripts\python.exe -m src.gui
```

或双击项目里的 `run_gui.bat`。

建议操作顺序：

1. 填左侧 **源库 MySQL**、右侧 **目标库**（主机、端口、账号、库名）。
2. 点 **测试源库并列出表**：会列出该库**全部**用户表。用勾选做多选；可用筛选、全选、全不选、反选。
3. **只迁勾选的表**。源库里未勾选的表不会导出、不会建表、不会 COPY。
4. 点 **测试目标库**，确认 YMatrix 能连上。
5. 「目标已存在」选 `fail`（远程）或 `truncate`；不要对客户库选 `replace`。
6. 点 **迁移并校验** 时会再确认一遍表名单。
7. 看日志和 `results/report.md`。

图形界面不会把数据库「画」在浏览器里，只是减少手改 yaml。命令行与界面可以混用：界面保存的 `config.yaml` 里只会留下你勾选的表。

---

## 6. 命令行：一次正确迁移

在项目根目录、已填好 `config.yaml` 的前提下：

### 6.1 列出源库表并指定要迁哪些

```powershell
python -m src.cli list-tables --config config.yaml
python -m src.cli run-all --config config.yaml --tables users,orders --if-exists truncate --results-dir results/run --results-dir results/run
```

`--tables` 覆盖 yaml 里的名单。不写 `--tables` 时，只迁 `migrate.tables` 里列出的表，**不会**自动迁源库全部表。

### 6.2 看源表结构

```powershell
python -m src.cli inspect --config config.yaml --results-dir results/run
```

确认表名、主键、类型无误。输出在 `results/run/schema.json`。

### 6.3 只生成 DDL，先审 SQL

```powershell
python -m src.cli generate-ddl --config config.yaml --results-dir results/run
```

查看 `results/run/ddl/*.sql`。真 YMatrix 下应看到 `DISTRIBUTED BY (...)`。`ENUM` 会映射成 `VARCHAR` 并告警，这是有意设计。

### 6.4 迁移并校验

```powershell
python -m src.cli run-all --config config.yaml --results-dir results/run
```

过程：导出 CSV（空值 `\N`）→ 目标库执行 DDL → `COPY` → 行数 / checksum / 抽样。退出码 `0` 表示全部通过。打开 `results/run/report.md` 看每张表的结论。

也可以拆开：

```powershell
python -m src.cli migrate --config config.yaml --results-dir results/run
python -m src.cli validate --config config.yaml --results-dir results/run
```

### 6.5 怎样算迁对了

- 报告里每张表 `passed`，行数相等，checksum 一致，抽样无差异。
- 用 Navicat / DBeaver / `psql` **按 yaml 里的目标 host/port/database** 打开表，抽几行和源库对照（中文、空值、小数）。
- 不要用「源和目标是不是同一套 Docker 网页」来判断；连错库、连错端口都会看成空表。

连目标库时客户端类型选 **PostgreSQL**。主机、端口、库名与 `config.yaml` 的 `target` 保持一致。

---

## 7. 依赖：Python、Docker、数据库

本工具没有调用云服务。运行依赖是本机 Python，以及你要连的 MySQL 和 YMatrix。下面是这次 Demo 实际用的环境。

| 依赖 | 这次怎么来的 |
|---|---|
| Python 3.10+ | `requirements.txt`：`pymysql`、`psycopg2-binary`、`PyYAML`、`pytest`。用项目里的 `.venv`，不要用 Windows 自带的 Python 3.7 |
| 源库 | `docker compose` 启动官方镜像 `mysql:8.4`，容器 `mx-migrate-mysql`，本机 `127.0.0.1:12306`，库 `biz`，用户 `root` / `demo`。样例数据是 `sql/mysql_init.sql` |
| 目标库 | 镜像 `matrixdb/centos7_demo`（MatrixDB 4.8.12 community）。Docker Hub 直连超时，本机从镜像站 `docker.1ms.run/matrixdb/centos7_demo` 拉取，摘要与 `matrixdb/centos7_demo` 相同。容器名 `mx-ymatrix` |
| 图形界面 | Python 标准库 `tkinter`，没有额外安装包 |

`docker-compose.yml` 只启动 MySQL。YMatrix 不在 Compose 里，需要单独起容器。容器起来后还要在里面执行 `scripts/start_ymatrix.sh`（已复制为容器内 `/opt/start_ymatrix.sh`），否则数据库进程不会监听。

迁表连的是容器内 **5432**，映射本机 **15432**，库 `mxadmin`，用户 `mxadmin` / `changeme`。同一容器里还有 **5433**，MatrixUI（本机 **8240**）连的是这套，看不到 15432 上的表。

`config.yaml` 含密码，已写入 `.gitignore`，仓库里只提交 `config.example.yaml`。示例里 `if_exists` 是 `fail`。本地反复演示时用过 `replace`，只针对可丢弃的 Demo 库。

换远程库时，改 yaml 的 host/port 即可，不必使用上述 Docker。

作业附带的异常演示（会改**目标库**数据，不要对客户库执行）：

```powershell
python -m src.cli inject-mismatch --config config.yaml
python -m src.cli validate --config config.yaml --results-dir results/mismatch
python -m src.cli demo-conn-fail --config config.yaml --port 1
python -m pytest -q
```

---

## 8. 常见问题

**连不上远程库**  
先用 Navicat 从**同一台电脑**测连通。不通就是网络 / 白名单 / 账号问题，改 yaml 解决不了。

**表不存在**  
`migrate.tables` 仍是 Demo 表名，或 `database` 填错。用图形界面「测试源库并列出表」，或在源库 `SHOW TABLES`。

**目标表已存在**  
`if_exists: fail` 会停。确认可以清空再用 `truncate`；确认可以丢弃再用 `replace`。

**类型失败**  
报告里会写不支持的类型。改表结构或从名单里去掉该表，不要指望工具自动丢掉该列。

**网页控制台看不到行**  
YMatrix 自带的 MatrixUI 是运维界面，一般不能当 Excel 查数。以 SQL 客户端连 **yaml 里的目标地址** 为准。

---

## 9. 已知限制

- 无主键表只做行数和 checksum，不做按键抽样。
- 未覆盖 MARS3、mxgate 等生产写入路径。
- 报告中的耗时只反映当次数据量，不能外推客户生产。

方案说明见 `report.md`，关键取舍见 `assessment.md`，AI 使用过程见 `ai_usage.md`。
