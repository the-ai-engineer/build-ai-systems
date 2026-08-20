"""Settings must load from anywhere in the tree, not only the repository root."""

from __future__ import annotations

import os
import tomllib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from pydantic_settings import SettingsConfigDict
from support_agent_app.settings import (
    CONFIG_FILE,
    ENV_FILES,
    PROJECT_ROOT,
    MissingConfiguration,
    ModelProviderSettings,
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

    def test_config_toml_contains_safe_defaults_and_no_secrets(self) -> None:
        self.assertEqual(CONFIG_FILE, PROJECT_ROOT / "config.toml")
        with CONFIG_FILE.open("rb") as source:
            configured = tomllib.load(source)

        self.assertEqual(configured["model_name"], "google-cloud:gemini-3.5-flash")
        self.assertEqual(configured["worker_task_auth"], "google-oidc")
        self.assertEqual(configured["task_queue_backend"], "local")
        self.assertTrue(
            {"database_url", "slack_bot_token", "slack_signing_secret"}.isdisjoint(configured)
        )

    def test_constructor_environment_and_dotenv_override_toml_in_that_order(self) -> None:
        with TemporaryDirectory() as directory:
            local_env = Path(directory) / ".env"
            local_env.write_text("SUPPORT_AGENT_MODEL=from-dotenv\n", encoding="utf-8")
            original_directory = Path.cwd()
            try:
                os.chdir(directory)
                with mock.patch.dict(os.environ, {}, clear=True):
                    self.assertEqual(ModelProviderSettings.load().model_name, "from-dotenv")

                    with mock.patch.dict(os.environ, {"SUPPORT_AGENT_MODEL": "from-environment"}):
                        self.assertEqual(
                            ModelProviderSettings.load().model_name,
                            "from-environment",
                        )
                        self.assertEqual(
                            ModelProviderSettings(
                                model_name="from-constructor",
                                google_cloud_location="from-constructor",
                            ).model_name,
                            "from-constructor",
                        )
            finally:
                os.chdir(original_directory)

        class TomlOnly(ModelProviderSettings):
            model_config = SettingsConfigDict(
                env_file=Path("/nonexistent/.env"),
                extra="ignore",
                populate_by_name=True,
                protected_namespaces=(),
                toml_file=CONFIG_FILE,
            )

        with mock.patch.dict(os.environ, {}, clear=True):
            configured = TomlOnly.load()
        self.assertEqual(configured.model_name, "google-cloud:gemini-3.5-flash")

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
        self.assertIn("config.toml", message)


if __name__ == "__main__":
    unittest.main()
