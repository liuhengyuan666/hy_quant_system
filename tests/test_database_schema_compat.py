from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from data_storage.database import _ensure_signal_record_schema_compatibility


class _FakeConnection:
    def __init__(self):
        self.statements: list[str] = []

    def execute(self, statement):
        self.statements.append(str(statement))


class _FakeBegin:
    def __init__(self, connection: _FakeConnection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeInspector:
    def get_table_names(self):
        return ["signal_record"]

    def get_columns(self, table_name: str):
        self._assert_table(table_name)
        return [
            {"name": "id"},
            {"name": "date"},
            {"name": "symbol"},
            {"name": "strategy"},
            {"name": "signal"},
            {"name": "score"},
            {"name": "meta"},
            {"name": "created_at"},
        ]

    def get_unique_constraints(self, table_name: str):
        self._assert_table(table_name)
        return [
            {
                "name": "uq_signal_record_date_symbol_strategy",
                "column_names": ["date", "symbol", "strategy"],
            }
        ]

    def get_indexes(self, table_name: str):
        self._assert_table(table_name)
        return [
            {
                "name": "ix_signal_record_date_symbol",
                "column_names": ["date", "symbol"],
                "unique": False,
            }
        ]

    @staticmethod
    def _assert_table(table_name: str):
        if table_name != "signal_record":
            raise AssertionError(f"unexpected table: {table_name}")


class DatabaseSchemaCompatTests(unittest.TestCase):
    @patch("data_storage.database.inspect")
    def test_signal_record_compatibility_adds_columns_and_indexes(self, mock_inspect):
        connection = _FakeConnection()
        engine = SimpleNamespace(
            dialect=SimpleNamespace(name="postgresql"),
            begin=lambda: _FakeBegin(connection),
        )
        mock_inspect.return_value = _FakeInspector()

        _ensure_signal_record_schema_compatibility(engine)

        sql = "\n".join(connection.statements)
        self.assertIn("ALTER TABLE signal_record ADD COLUMN mode VARCHAR(16)", sql)
        self.assertIn("ALTER TABLE signal_record ADD COLUMN bar_frequency VARCHAR(8)", sql)
        self.assertIn("UPDATE signal_record SET mode = 'eod' WHERE mode IS NULL", sql)
        self.assertIn("DROP CONSTRAINT IF EXISTS \"uq_signal_record_date_symbol_strategy\"", sql)
        self.assertIn("CREATE UNIQUE INDEX IF NOT EXISTS ux_signal_record_scope", sql)
        self.assertIn("CREATE INDEX IF NOT EXISTS ix_signal_record_scope", sql)


if __name__ == "__main__":
    unittest.main()
