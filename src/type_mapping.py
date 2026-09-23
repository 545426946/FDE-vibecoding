from dataclasses import dataclass
from typing import List, Optional, Tuple

from .schema import ColumnSchema, TableSchema


@dataclass
class MappingResult:
    pg_type: str
    warnings: List[str]
    unsupported: bool = False


def _base_type(column: ColumnSchema) -> str:
    return column.data_type.lower().strip()


def map_column(column: ColumnSchema) -> MappingResult:
    """显式类型映射。不认识的类型直接判失败，禁止静默乱转。"""
    base = _base_type(column)
    warnings: List[str] = []

    if base in {"tinyint"}:
        # TINYINT(1) 在业务里常被当布尔，但取值可到 127/-128。保真映射到 SMALLINT。
        warnings.append(
            f"{column.name}: TINYINT 映射为 SMALLINT，而不是 BOOLEAN，避免非 0/1 值写入失败"
        )
        return MappingResult("SMALLINT", warnings)

    if base in {"smallint"}:
        pg = "INTEGER" if column.unsigned else "SMALLINT"
        if column.unsigned:
            warnings.append(f"{column.name}: UNSIGNED SMALLINT 提升为 INTEGER，避免溢出")
        return MappingResult(pg, warnings)

    if base in {"mediumint"}:
        warnings.append(f"{column.name}: MEDIUMINT 无直接对应类型，映射为 INTEGER")
        return MappingResult("INTEGER", warnings)

    if base in {"int", "integer"}:
        if column.unsigned:
            warnings.append(f"{column.name}: UNSIGNED INT 映射为 BIGINT，避免 2^31 以上溢出")
            return MappingResult("BIGINT", warnings)
        return MappingResult("INTEGER", warnings)

    if base in {"bigint"}:
        if column.unsigned:
            warnings.append(
                f"{column.name}: UNSIGNED BIGINT 映射为 NUMERIC(20,0)，PostgreSQL BIGINT 不够装"
            )
            return MappingResult("NUMERIC(20,0)", warnings)
        return MappingResult("BIGINT", warnings)

    if base in {"decimal", "numeric"}:
        precision = column.numeric_precision or 10
        scale = column.numeric_scale or 0
        return MappingResult(f"NUMERIC({precision},{scale})", warnings)

    if base in {"float"}:
        warnings.append(f"{column.name}: FLOAT 映射为 REAL，二进制浮点跨库可能有精度差")
        return MappingResult("REAL", warnings)

    if base in {"double"}:
        warnings.append(f"{column.name}: DOUBLE 映射为 DOUBLE PRECISION，校验时按字符串规范化")
        return MappingResult("DOUBLE PRECISION", warnings)

    if base in {"char"}:
        length = column.char_length or 1
        return MappingResult(f"CHAR({length})", warnings)

    if base in {"varchar"}:
        length = column.char_length or 255
        return MappingResult(f"VARCHAR({length})", warnings)

    if base in {"tinytext", "text", "mediumtext", "longtext"}:
        return MappingResult("TEXT", warnings)

    if base == "date":
        return MappingResult("DATE", warnings)

    if base == "datetime":
        warnings.append(
            f"{column.name}: DATETIME 映射为 TIMESTAMP WITHOUT TIME ZONE。"
            "MySQL DATETIME 无时区，目标库不要改成 TIMESTAMPTZ，否则会平移小时"
        )
        return MappingResult("TIMESTAMP", warnings)

    if base == "timestamp":
        warnings.append(
            f"{column.name}: MySQL TIMESTAMP 内部按 UTC 存，这里按 TIMESTAMP WITHOUT TIME ZONE 保字面值，"
            "不自动加时区，避免校验对不上"
        )
        return MappingResult("TIMESTAMP", warnings)

    if base == "time":
        return MappingResult("TIME", warnings)

    if base == "year":
        warnings.append(f"{column.name}: YEAR 映射为 SMALLINT，语义下降")
        return MappingResult("SMALLINT", warnings)

    if base == "enum":
        length = max(column.char_length or 32, 32)
        warnings.append(
            f"{column.name}: ENUM 映射为 VARCHAR({length})，约束被丢掉，目标库不再拒绝非法枚举值"
        )
        return MappingResult(f"VARCHAR({length})", warnings)

    if base == "json":
        warnings.append(f"{column.name}: JSON 映射为 JSONB，空白和 key 顺序可能变化，checksum 需规范化")
        return MappingResult("JSONB", warnings)

    if base in {"blob", "tinyblob", "mediumblob", "longblob", "binary", "varbinary", "bit", "set", "geometry"}:
        return MappingResult(
            "",
            [f"{column.name}: MySQL 类型 {column.column_type} 暂不支持自动迁移"],
            unsupported=True,
        )

    return MappingResult(
        "",
        [f"{column.name}: 未配置映射规则的类型 {column.column_type}"],
        unsupported=True,
    )


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def qualified_table(schema: str, table: str) -> str:
    return f"{quote_ident(schema)}.{quote_ident(table)}"


def generate_create_table(
    table: TableSchema,
    target_schema: str,
    dialect: str = "ymatrix",
) -> Tuple[str, List[str], List[str]]:
    """返回 (DDL, warnings, unsupported_reasons)。遇到不支持类型时 DDL 为空。"""
    warnings: List[str] = []
    mapped_cols = []
    for col in table.columns:
        result = map_column(col)
        warnings.extend(result.warnings)
        if result.unsupported:
            return "", warnings, result.warnings
        null_sql = "NULL" if col.nullable else "NOT NULL"
        mapped_cols.append(f"    {quote_ident(col.name)} {result.pg_type} {null_sql}")

    pk_sql = ""
    if table.primary_key:
        pk_cols = ", ".join(quote_ident(c) for c in table.primary_key)
        pk_sql = f",\n    PRIMARY KEY ({pk_cols})"

    dist_sql = ";"
    if dialect == "ymatrix":
        if table.primary_key:
            dist_sql = f"\nDISTRIBUTED BY ({quote_ident(table.primary_key[0])});"
            if len(table.primary_key) > 1:
                warnings.append(
                    f"{table.name}: 复合主键只按第一列 {table.primary_key[0]} 分布，存在倾斜风险"
                )
        else:
            dist_sql = "\nDISTRIBUTED RANDOMLY;"
            warnings.append(f"{table.name}: 无主键，使用 DISTRIBUTED RANDOMLY，更新和倾斜都更难控")

    ddl = (
        f"CREATE TABLE {qualified_table(target_schema, table.name)} (\n"
        + ",\n".join(mapped_cols)
        + pk_sql
        + "\n)"
        + dist_sql
        + "\n"
    )
    return ddl, warnings, []
