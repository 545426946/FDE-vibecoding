"""简易图形界面：填写源库 / 目标库，勾选表后迁移并校验。"""
from __future__ import annotations

import sys

if sys.version_info < (3, 10):
    sys.stderr.write(
        "当前 Python 是 %s，本工具需要 3.10+（推荐 3.12）。\n"
        "不要用系统自带的 python（例如 Python37）。请在项目目录执行：\n"
        "  .\\.venv\\Scripts\\Activate.ps1\n"
        "  python -m src.gui\n"
        "或直接：\n"
        "  .\\.venv\\Scripts\\python.exe -m src.gui\n"
        % sys.version.split()[0]
    )
    sys.exit(1)

import logging
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import yaml

from .config import load_config, require_selected_tables, save_config
from .db import connect_mysql, connect_target, list_mysql_tables
from .logging_setup import setup_logging
from .pipeline import inspect_all, migrate_tables, validate_tables
from .reporter import write_reports

CONFIG_PATH = Path("config.yaml")
EXAMPLE_PATH = Path("config.example.yaml")


class TextHandler(logging.Handler):
    def __init__(self, widget: tk.Text) -> None:
        super().__init__()
        self.widget = widget

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record) + "\n"
        self.widget.after(0, lambda m=msg: self._append(m))

    def _append(self, msg: str) -> None:
        self.widget.configure(state="normal")
        self.widget.insert("end", msg)
        self.widget.see("end")
        self.widget.configure(state="disabled")


class MigrateApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("mysql2ymatrix — 迁移配置")
        root.geometry("980x720")
        self.busy = False
        self.source_vars: dict[str, tk.StringVar] = {}
        self.target_vars: dict[str, tk.StringVar] = {}
        self.if_exists = tk.StringVar(value="fail")
        self.table_vars: dict[str, tk.BooleanVar] = {}
        self.table_rows: list[tuple[str, tk.BooleanVar, ttk.Checkbutton]] = []
        self.filter_var = tk.StringVar()
        self.selected_label = None
        self.preset_tables: list[str] = []

        data = self._load_initial()
        self._build(data)
        self._log(
            "先测源库并列出全部表，再勾选要迁的表（可多选）。未勾选的表不会迁移，不会整库搬运。"
        )

    def _load_initial(self) -> dict:
        path = CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_PATH
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}

    def _entry_row(self, parent, row: int, label: str, var: tk.StringVar, show: str = "") -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=3)
        ttk.Entry(parent, textvariable=var, show=show, width=28).grid(
            row=row, column=1, sticky="ew", padx=6, pady=3
        )

    def _conn_frame(self, parent, title: str, section: dict, fields: list[tuple[str, str]], store: dict) -> ttk.LabelFrame:
        box = ttk.LabelFrame(parent, text=title, padding=8)
        box.columnconfigure(1, weight=1)
        for i, (key, label) in enumerate(fields):
            value = section.get(key, "")
            var = tk.StringVar(value=str(value))
            store[key] = var
            self._entry_row(box, i, label, var, show="*" if key == "password" else "")
        return box

    def _build(self, data: dict) -> None:
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill="both", expand=True)
        top.columnconfigure(0, weight=1)
        top.columnconfigure(1, weight=1)
        top.rowconfigure(2, weight=1)

        source = self._conn_frame(
            top,
            "源库 MySQL（只读：SELECT / information_schema）",
            data.get("source") or {},
            [
                ("host", "主机"),
                ("port", "端口"),
                ("user", "用户"),
                ("password", "密码"),
                ("database", "数据库"),
            ],
            self.source_vars,
        )
        source.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=(0, 8))

        target = self._conn_frame(
            top,
            "目标库 YMatrix / PostgreSQL",
            data.get("target") or {},
            [
                ("host", "主机"),
                ("port", "端口"),
                ("user", "用户"),
                ("password", "密码"),
                ("database", "数据库"),
                ("schema", "schema"),
            ],
            self.target_vars,
        )
        extra = ttk.Frame(target)
        extra.grid(row=6, column=0, columnspan=2, sticky="ew", pady=4)
        ttk.Label(extra, text="方言").pack(side="left")
        self.dialect = tk.StringVar(value=(data.get("target") or {}).get("dialect", "ymatrix"))
        ttk.Combobox(extra, textvariable=self.dialect, values=("ymatrix", "postgresql"), width=12, state="readonly").pack(
            side="left", padx=6
        )
        ttk.Label(extra, text="运行时").pack(side="left")
        self.runtime = tk.StringVar(value=(data.get("target") or {}).get("runtime", "ymatrix"))
        ttk.Combobox(extra, textvariable=self.runtime, values=("ymatrix", "postgresql"), width=12, state="readonly").pack(
            side="left", padx=6
        )
        target.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=(0, 8))

        mid = ttk.Frame(top)
        mid.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ttk.Label(mid, text="目标已存在").pack(side="left")
        ttk.Combobox(
            mid,
            textvariable=self.if_exists,
            values=("fail", "truncate", "replace"),
            width=12,
            state="readonly",
        ).pack(side="left", padx=6)
        self.if_exists.set((data.get("migrate") or {}).get("if_exists", "fail"))
        ttk.Label(mid, text="fail=已有表则失败；truncate=清空再导入；replace=删表再建（勿用于客户库）").pack(
            side="left", padx=8
        )

        tables = ttk.LabelFrame(
            top,
            text="要迁移的表（列出源库全部表后多选；未勾选的不会迁）",
            padding=8,
        )
        tables.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(0, 8))
        tables.rowconfigure(1, weight=1)
        tables.columnconfigure(0, weight=1)

        toolbar = ttk.Frame(tables)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        ttk.Label(toolbar, text="筛选").pack(side="left")
        filt = ttk.Entry(toolbar, textvariable=self.filter_var, width=22)
        filt.pack(side="left", padx=6)
        self.filter_var.trace_add("write", lambda *_: self._apply_filter())
        ttk.Button(toolbar, text="全选", command=lambda: self._set_all(True)).pack(side="left", padx=2)
        ttk.Button(toolbar, text="全不选", command=lambda: self._set_all(False)).pack(side="left", padx=2)
        ttk.Button(toolbar, text="反选", command=self._invert).pack(side="left", padx=2)
        self.selected_label = ttk.Label(toolbar, text="已选 0 张")
        self.selected_label.pack(side="left", padx=12)

        canvas = tk.Canvas(tables, height=160, highlightthickness=0)
        scroll = ttk.Scrollbar(tables, orient="vertical", command=canvas.yview)
        self.table_inner = ttk.Frame(canvas)
        self.table_inner.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.table_inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.grid(row=1, column=0, sticky="nsew")
        scroll.grid(row=1, column=1, sticky="ns")
        canvas.bind("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))
        preset = (data.get("migrate") or {}).get("tables") or []
        self.preset_tables = list(preset)
        if preset:
            self._render_tables(preset, selected=set(preset))

        btns = ttk.Frame(top)
        btns.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        for text, cmd in [
            ("测试源库并列出表", self.on_list_tables),
            ("测试目标库", self.on_test_target),
            ("保存到 config.yaml", self.on_save),
            ("预览表结构", self.on_inspect),
            ("迁移并校验", self.on_run_all),
        ]:
            ttk.Button(btns, text=text, command=cmd).pack(side="left", padx=4)

        log_box = ttk.LabelFrame(top, text="日志", padding=6)
        log_box.grid(row=4, column=0, columnspan=2, sticky="nsew")
        top.rowconfigure(4, weight=1)
        self.log_text = tk.Text(log_box, height=12, state="disabled", wrap="word")
        self.log_text.pack(fill="both", expand=True)
        handler = TextHandler(self.log_text)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)

    def _log(self, msg: str) -> None:
        logging.getLogger(__name__).info(msg)

    def _refresh_selected_label(self) -> None:
        n = len(self._selected_tables())
        total = len(self.table_vars)
        if self.selected_label is not None:
            self.selected_label.configure(text=f"已选 {n} / {total} 张")

    def _apply_filter(self) -> None:
        kw = (self.filter_var.get() or "").strip().lower()
        for name, _var, widget in self.table_rows:
            if not kw or kw in name.lower():
                widget.pack(anchor="w")
            else:
                widget.pack_forget()

    def _set_all(self, value: bool) -> None:
        kw = (self.filter_var.get() or "").strip().lower()
        for name, var, _widget in self.table_rows:
            if not kw or kw in name.lower():
                var.set(value)
        self._refresh_selected_label()

    def _invert(self) -> None:
        kw = (self.filter_var.get() or "").strip().lower()
        for name, var, _widget in self.table_rows:
            if not kw or kw in name.lower():
                var.set(not var.get())
        self._refresh_selected_label()

    def _render_tables(self, names: list[str], selected: set[str] | None = None) -> None:
        for child in self.table_inner.winfo_children():
            child.destroy()
        self.table_vars = {}
        self.table_rows = []
        chosen = selected or set()
        for name in names:
            var = tk.BooleanVar(value=name in chosen)
            var.trace_add("write", lambda *_: self._refresh_selected_label())
            box = ttk.Checkbutton(self.table_inner, text=name, variable=var)
            box.pack(anchor="w")
            self.table_vars[name] = var
            self.table_rows.append((name, var, box))
        self._apply_filter()
        self._refresh_selected_label()

    def _source_cfg_dict(self) -> dict:
        src = {k: v.get().strip() for k, v in self.source_vars.items()}
        src["port"] = int(src["port"])
        src["charset"] = "utf8mb4"
        src["connect_timeout"] = 5
        return src

    def _target_cfg_dict(self) -> dict:
        tgt = {k: v.get().strip() for k, v in self.target_vars.items()}
        tgt["port"] = int(tgt["port"])
        tgt["dialect"] = self.dialect.get()
        tgt["runtime"] = self.runtime.get()
        tgt["connect_timeout"] = 10
        return tgt

    def _selected_tables(self) -> list[str]:
        return [name for name, var in self.table_vars.items() if var.get()]

    def _payload(self) -> dict:
        tables = require_selected_tables(self._selected_tables())
        return {
            "source": self._source_cfg_dict(),
            "target": self._target_cfg_dict(),
            "migrate": {
                "tables": tables,
                "if_exists": self.if_exists.get(),
                "csv_dir": "./data/export",
                "retries": 3,
                "retry_backoff_seconds": 0.5,
                "continue_on_error": True,
            },
            "validate": {"sample_size": 20, "checksum_chunk_size": 1000},
            "output": {"results_dir": "./results", "log_level": "INFO"},
        }

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy

    def _bg(self, fn) -> None:
        if self.busy:
            messagebox.showinfo("请等待", "当前任务还在执行")
            return
        self._set_busy(True)

        def runner() -> None:
            try:
                fn()
            except Exception as exc:  # noqa: BLE001
                logging.getLogger(__name__).exception("操作失败")
                self.root.after(0, lambda: messagebox.showerror("失败", str(exc)))
            finally:
                self.root.after(0, lambda: self._set_busy(False))

        threading.Thread(target=runner, daemon=True).start()

    def on_list_tables(self) -> None:
        def job() -> None:
            from .config import SourceConfig

            src = SourceConfig(**self._source_cfg_dict())
            conn = connect_mysql(src, retries=2, backoff=0.4, logger=logging.getLogger(__name__))
            try:
                names = list_mysql_tables(conn, src.database)
            finally:
                conn.close()
            if not names:
                raise RuntimeError(f"库 {src.database} 里没有用户表")
            prev = {n for n, v in self.table_vars.items() if v.get()}
            if not prev:
                prev = set(self.preset_tables)
            # 源库多出来的表默认不勾选，避免误迁全库
            self.root.after(0, lambda n=names, p=prev: self._render_tables(n, selected=p))
            extra = [n for n in names if n not in prev]
            self._log(
                f"源库连通，共 {len(names)} 张表；已勾选 {len(prev & set(names))} 张。"
                f"未勾选的 {len(extra)} 张不会迁移。"
            )

        self._bg(job)

    def on_test_target(self) -> None:
        def job() -> None:
            from .config import TargetConfig

            tgt = TargetConfig(**self._target_cfg_dict())
            conn = connect_target(tgt, retries=2, backoff=0.4, logger=logging.getLogger(__name__))
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT current_database(), version()")
                    db, ver = cur.fetchone()
                self._log(f"目标库连通：{db} / {ver}")
            finally:
                conn.close()

        self._bg(job)

    def on_save(self) -> None:
        try:
            save_config(str(CONFIG_PATH), self._payload())
            self._log(f"已写入 {CONFIG_PATH.resolve()}")
            messagebox.showinfo("已保存", f"配置已写入 {CONFIG_PATH}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("保存失败", str(exc))

    def _write_and_load(self):
        save_config(str(CONFIG_PATH), self._payload())
        cfg = load_config(str(CONFIG_PATH))
        setup_logging(cfg.output.results_dir, cfg.output.log_level)
        return cfg

    def on_inspect(self) -> None:
        def job() -> None:
            cfg = self._write_and_load()
            tables = inspect_all(cfg)
            lines = [f"{t.name}  pk={t.primary_key or '-'}  cols={len(t.columns)}" for t in tables]
            self._log("表结构：\n" + "\n".join(lines))

        self._bg(job)

    def on_run_all(self) -> None:
        try:
            picked = require_selected_tables(self._selected_tables())
        except ValueError as exc:
            messagebox.showerror("未选表", str(exc))
            return
        preview = "\n".join(picked[:30])
        if len(picked) > 30:
            preview += f"\n... 共 {len(picked)} 张"
        if not messagebox.askyesno(
            "确认只迁选中的表",
            f"将只迁移下面 {len(picked)} 张表，源库其余表不会动：\n\n{preview}",
        ):
            return
        if self.if_exists.get() == "replace":
            if not messagebox.askyesno(
                "确认 replace",
                "replace 会 DROP 目标同名表。客户库或生产库不要用。仍要继续吗？",
            ):
                return

        def job() -> None:
            cfg = self._write_and_load()
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
                    "notes": (
                        f"图形界面：仅迁移 {len(cfg.migrate.tables)} 张指定表 "
                        f"({', '.join(cfg.migrate.tables)})"
                    ),
                },
            )
            failed = any(r.status != "success" for r in migrate_results) or any(
                not c.passed for c in checks
            )
            report = Path(cfg.output.results_dir) / "report.md"
            if failed:
                self._log(f"迁移或校验未全部通过，见 {report}")
                self.root.after(0, lambda: messagebox.showwarning("未通过", f"请查看 {report}"))
            else:
                self._log(f"迁移校验通过，报告 {report}")
                self.root.after(0, lambda: messagebox.showinfo("完成", f"已通过，报告：{report}"))

        self._bg(job)


def main() -> None:
    root = tk.Tk()
    MigrateApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
