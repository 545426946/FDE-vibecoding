-- 业务表示例 + 边界表。数据固定，便于 checksum 回归。
-- 可重复执行：先删表再建表灌数。无外键，删除顺序任意。
SET NAMES utf8mb4;
SET time_zone = '+08:00';

DROP TABLE IF EXISTS order_items, payments, orders, products, users,
  edge_nulls, edge_empty, edge_types;

CREATE TABLE users (
  id INT NOT NULL PRIMARY KEY,
  name VARCHAR(64) NOT NULL,
  email VARCHAR(128) NULL,
  bio TEXT NULL,
  created_at DATETIME NOT NULL,
  updated_at TIMESTAMP NULL DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE products (
  id BIGINT NOT NULL PRIMARY KEY,
  sku VARCHAR(32) NOT NULL,
  name VARCHAR(128) NOT NULL,
  description TEXT NULL,
  price DECIMAL(10,2) NOT NULL,
  cost DECIMAL(18,6) NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE orders (
  id INT NOT NULL PRIMARY KEY,
  user_id INT NOT NULL,
  status VARCHAR(16) NOT NULL,
  amount DECIMAL(12,2) NOT NULL,
  ordered_at DATETIME NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE order_items (
  id INT NOT NULL PRIMARY KEY,
  order_id INT NOT NULL,
  product_id BIGINT NOT NULL,
  qty INT NOT NULL,
  unit_price DECIMAL(10,2) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE payments (
  id INT NOT NULL PRIMARY KEY,
  order_id INT NOT NULL,
  paid_amount DECIMAL(12,2) NOT NULL,
  paid_at TIMESTAMP NOT NULL,
  channel VARCHAR(32) NOT NULL,
  remark TEXT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 空值 / 空串 / 中文 / 特殊字符
CREATE TABLE edge_nulls (
  id INT NOT NULL PRIMARY KEY,
  title VARCHAR(64) NULL,
  note TEXT NULL,
  amount DECIMAL(10,2) NULL,
  happened_at DATETIME NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 空表：0 行也必须能迁、能校验
CREATE TABLE edge_empty (
  id INT NOT NULL PRIMARY KEY,
  payload VARCHAR(32) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 类型边界：精度、unsigned、ENUM（会告警后按 VARCHAR 迁）
CREATE TABLE edge_types (
  id INT UNSIGNED NOT NULL PRIMARY KEY,
  tiny_flag TINYINT NOT NULL,
  enum_status ENUM('active', 'disabled', 'unknown') NOT NULL,
  price DECIMAL(10,2) NOT NULL,
  ratio DECIMAL(18,6) NOT NULL,
  event_time DATETIME(0) NOT NULL,
  ts_col TIMESTAMP NOT NULL,
  short_name VARCHAR(1) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO users (id, name, email, bio, created_at, updated_at) VALUES
(1, 'Alice', 'alice@example.com', '普通用户', '2026-01-01 10:00:00', '2026-01-02 10:00:00'),
(2, 'Bob', NULL, NULL, '2026-01-03 08:15:00', NULL),
(3, '陈三', 'chen@example.com', '含中文与标点，。', '2026-02-01 00:00:00', '2026-02-01 00:00:01'),
(4, 'Dave', 'dave@example.com', '', '2026-03-01 12:30:00', '2026-03-01 12:30:00'),
(5, 'Eve', 'eve@example.com', 'line1\nline2', '2026-04-01 09:00:00', '2026-04-02 09:00:00');

INSERT INTO products (id, sku, name, description, price, cost) VALUES
(10001, 'SKU-A', '入门套件', '基础款', 99.90, 40.123456),
(10002, 'SKU-B', '专业套件', NULL, 1288.00, 700.000000),
(10003, 'SKU-C', '配件-中文', '逗号,引号"测试', 0.01, NULL),
(10004, 'SKU-D', '免费样品', '', 0.00, 0.000000);

INSERT INTO orders (id, user_id, status, amount, ordered_at) VALUES
(201, 1, 'paid', 99.90, '2026-05-01 11:00:00'),
(202, 1, 'paid', 1288.00, '2026-05-02 11:00:00'),
(203, 3, 'pending', 0.01, '2026-05-03 18:40:00'),
(204, 4, 'cancelled', 0.00, '2026-05-04 08:00:00'),
(205, 5, 'paid', 1387.91, '2026-05-05 20:20:20');

INSERT INTO order_items (id, order_id, product_id, qty, unit_price) VALUES
(1, 201, 10001, 1, 99.90),
(2, 202, 10002, 1, 1288.00),
(3, 203, 10003, 1, 0.01),
(4, 205, 10001, 1, 99.90),
(5, 205, 10002, 1, 1288.01);

INSERT INTO payments (id, order_id, paid_amount, paid_at, channel, remark) VALUES
(1, 201, 99.90, '2026-05-01 11:01:00', 'alipay', NULL),
(2, 202, 1288.00, '2026-05-02 11:02:00', 'wechat', '足额'),
(3, 205, 1387.91, '2026-05-05 20:21:00', 'card', '含运费');

INSERT INTO edge_nulls (id, title, note, amount, happened_at) VALUES
(1, NULL, NULL, NULL, NULL),
(2, '', '', 0.00, '2026-06-01 00:00:00'),
(3, '中文标题', '包含|竖线,逗号和"引号"', 12.30, '2026-06-02 23:59:59'),
(4, '   ', '仅空格标题在另一列', -1.00, NULL);

INSERT INTO edge_types (id, tiny_flag, enum_status, price, ratio, event_time, ts_col, short_name) VALUES
(1, 0, 'active', 1.50, 0.100000, '2026-07-01 00:00:00', '2026-07-01 00:00:00', 'A'),
(2, 1, 'disabled', 99.99, 12.345678, '2026-07-02 12:00:00', '2026-07-02 12:00:00', 'B'),
(3, 127, 'unknown', 0.00, 0.000001, '2026-07-03 23:59:59', '2026-07-03 23:59:59', 'Z');
