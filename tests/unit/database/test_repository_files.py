"""Missing repository files must fail, not report an empty success.

Both defaults are resolved from the module's own location, which is the
repository root in a checkout and somewhere inside the virtual environment in
the container image. When the directory is absent, globbing it returns nothing,
and "nothing" used to look exactly like "already done".
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from support_agent_app.database.migrations import apply_migrations
from support_agent_app.database.repositories.policy_repository import load_policy_directory


class MissingFilesTests(unittest.TestCase):
    def test_applying_migrations_from_a_missing_directory_fails(self) -> None:
        with TemporaryDirectory() as directory:
            absent = Path(directory) / "migrations"
            with self.assertRaises(FileNotFoundError):
                # The database is never reached: the directory is checked first,
                # so this needs no connection.
                apply_migrations("postgresql://unused/unused", absent)

    def test_loading_policies_from_a_missing_directory_fails(self) -> None:
        with TemporaryDirectory() as directory:
            absent = Path(directory) / "policies"
            with self.assertRaises(FileNotFoundError):
                load_policy_directory(absent)

    def test_an_empty_policy_directory_is_still_empty(self) -> None:
        """A directory that exists and holds nothing is a different fact."""

        with TemporaryDirectory() as directory:
            self.assertEqual(load_policy_directory(Path(directory)), [])
