"""向源库追加一批可重复生成的数据，用来演示行数变大后的校验。"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta

import pymysql
import yaml


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--users", type=int, default=200)
    args = parser.parse_args()
    with open(args.config, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    source = cfg["source"]
    conn = pymysql.connect(
        host=source["host"],
        port=source["port"],
        user=source["user"],
        password=source["password"],
        database=source["database"],
        charset=source.get("charset", "utf8mb4"),
        autocommit=True,
    )
    start = datetime(2026, 8, 1, 0, 0, 0)
    with conn.cursor() as cur:
        cur.execute("SELECT COALESCE(MAX(id), 0) FROM users")
        base = int(cur.fetchone()[0])
        rows = []
        for i in range(1, args.users + 1):
            user_id = base + i
            rows.append(
                (
                    user_id,
                    f"user_{user_id}",
                    f"user_{user_id}@example.com",
                    None,
                    start + timedelta(minutes=i),
                    None,
                )
            )
        cur.executemany(
            "INSERT INTO users (id, name, email, bio, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            rows,
        )
    print(f"已追加 {args.users} 个用户，id 从 {base + 1} 开始")
    conn.close()


if __name__ == "__main__":
    main()
