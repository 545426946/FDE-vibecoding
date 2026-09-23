from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ColumnSchema:
    name: str
    data_type: str
    column_type: str
    nullable: bool
    char_length: Optional[int] = None
    numeric_precision: Optional[int] = None
    numeric_scale: Optional[int] = None
    datetime_precision: Optional[int] = None
    unsigned: bool = False
    extra: str = ""


@dataclass
class TableSchema:
    schema: str
    name: str
    columns: List[ColumnSchema] = field(default_factory=list)
    primary_key: List[str] = field(default_factory=list)

    def column(self, name: str) -> ColumnSchema:
        for col in self.columns:
            if col.name == name:
                return col
        raise KeyError(name)
