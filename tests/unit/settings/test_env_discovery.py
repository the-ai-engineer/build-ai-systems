"""Settings must load from anywhere in the tree, not only the repository root."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

from pydantic_settings import SettingsConfigDict
from support_agent_app.settings import (
    ENV_FILES,
    PROJECT_ROOT,
    MissingConfiguration,
    WorkerSettings,
)


class EnvDiscoveryTests(unittest.TestCase):
    def test_the_env_file_is_anchored_to_the_project_root(self) -> None:
        """A relative ".env" only resolves when the command runs from the root.

        `uv run seed-policies` does not change directory, so a student running it
        from anywhere else silently got no configuration at all.
        """
        self.assertTrue(PROJECT_ROOT.is_absolute())
        self.assertTrue((PROJECT_ROOT / "pyproject.toml").exists())
        self.assertIn(PROJECT_ROOT / ".env", ENV_FILES)

    def test_a_directory_local_env_file_still_wins(self) -> None:
        """The root file is a shared default, not an override."""
        root_index = ENV_FILES.index(PROJECT_ROOT / ".env")
        local_index = ENV_FILES.index(Path(".env"))
        self.assertLess(root_index, local_index, "later env files take precedence")

    def test_missing_configuration_names_the_variable(self) -> None:
        """A missing value should read as a sentence, not a pydantic stack trace."""

        class Isolated(WorkerSettings):
            model_config = SettingsConfigDict(
                env_file=Path("/nonexistent/.env"),
                extra="ignore",
                protected_namespaces=(),
            )

        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(MissingConfiguration) as caught:
                Isolated.load()

        message = str(caught.exception)
        self.assertIn("DATABASE_URL", message)
        self.assertIn(".env.example", message)


if __name__ == "__main__":
    unittest.main()
