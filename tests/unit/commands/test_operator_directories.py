"""The operator commands must run against files that are not beside the code.

In a checkout the schema and the policy set sit at the repository root and the
defaults find them. In the container image they are copied to a fixed path that
no relative resolution reaches, so the Cloud Run jobs name the directory. These
tests are about that argument arriving where it is used: a command that quietly
fell back to its default would fail inside the image with a path a reader has
no reason to expect.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from support_agent_app.commands import apply_migrations as apply_migrations_command
from support_agent_app.commands import seed_policies as seed_policies_command

IMAGE_MIGRATIONS = Path("/srv/migrations")
IMAGE_POLICIES = Path("/srv/policies")
DATABASE_URL = "postgresql://unused/unused"


class ApplyMigrationsArgumentTests(unittest.TestCase):
    def test_the_named_directory_is_the_one_applied(self) -> None:
        with patch.object(apply_migrations_command, "apply_migrations") as applied:
            with patch(
                "sys.argv",
                [
                    "apply-migrations",
                    "--database-url",
                    DATABASE_URL,
                    "--migrations-dir",
                    "/srv/migrations",
                ],
            ):
                apply_migrations_command.main()
        applied.assert_called_once_with(DATABASE_URL, IMAGE_MIGRATIONS)

    def test_the_default_is_the_repository_directory(self) -> None:
        with patch.object(apply_migrations_command, "apply_migrations") as applied:
            with patch("sys.argv", ["apply-migrations", "--database-url", DATABASE_URL]):
                apply_migrations_command.main()
        _, directory = applied.call_args.args
        self.assertTrue((directory / "001_support_documents.sql").is_file())


class SeedPoliciesArgumentTests(unittest.TestCase):
    def test_both_named_directories_reach_the_work(self) -> None:
        with patch.object(seed_policies_command, "seed_policy_documents", return_value=3) as seeded:
            with patch(
                "sys.argv",
                [
                    "seed-policies",
                    "--database-url",
                    DATABASE_URL,
                    "--migrations-dir",
                    "/srv/migrations",
                    "--policies-dir",
                    "/srv/policies",
                ],
            ):
                seed_policies_command.main()
        seeded.assert_called_once_with(
            DATABASE_URL,
            policies_directory=IMAGE_POLICIES,
            migrations_directory=IMAGE_MIGRATIONS,
        )

    def test_seeding_checks_the_named_migrations_directory_before_connecting(self) -> None:
        """A wrong path is a failure with that path in it, not an empty success."""

        with TemporaryDirectory() as directory:
            absent = Path(directory) / "migrations"
            with self.assertRaises(FileNotFoundError) as raised:
                seed_policies_command.seed_policy_documents(
                    DATABASE_URL,
                    policies_directory=Path(directory),
                    migrations_directory=absent,
                )
        self.assertIn(str(absent), str(raised.exception))


if __name__ == "__main__":
    unittest.main()
