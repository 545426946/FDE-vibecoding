import pytest

from src.config import parse_table_arg, require_selected_tables


def test_parse_table_arg_multi_and_dedupe():
    assert parse_table_arg("users, orders,users") == ["users", "orders"]
    assert parse_table_arg("a; b\nc") == ["a", "b", "c"]


def test_require_selected_tables_rejects_empty():
    with pytest.raises(ValueError, match="不会默认迁移"):
        require_selected_tables([])
    with pytest.raises(ValueError, match="不会默认迁移"):
        require_selected_tables(["  ", ""])
    assert require_selected_tables(["users", "orders"]) == ["users", "orders"]
