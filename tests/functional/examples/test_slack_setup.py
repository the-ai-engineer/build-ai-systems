import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BOOTSTRAP_MANIFEST = ROOT / "slack" / "manifest.bootstrap.json"
DEPLOYED_MANIFEST = ROOT / "slack" / "manifest.json"
HUMAN_REVIEW_FALLBACK = (
    "I couldn’t find a reliable answer in the policy documents. Please ask a member of the HR team."
)
REMOVED_SUPPORT_GROUP_SETTING = "_".join(("SLACK", "HR", "USER", "GROUP", "ID"))
REMOVED_SUPPORT_GROUP_PHRASE = " ".join(("configured", "HR", "support", "user", "group"))
V1_CONTRACT_PATHS = (
    ROOT / "AGENTS.md",
    ROOT / "README.md",
    ROOT / "brief.md",
    ROOT / "docs" / "final-agent-spec.md",
    ROOT / "docs" / "resources" / "configure-slack-app-with-codex-prompt.md",
    ROOT / "docs" / "resources" / "deploy-with-codex-prompt.md",
    ROOT / "docs" / "slack-setup.md",
    ROOT / "docs" / "slack-knowledge-agent" / "brief.md",
    ROOT / "MEMORY.md",
)
FIXED_FALLBACK_PATHS = (
    ROOT / "brief.md",
    ROOT / "docs" / "final-agent-spec.md",
    ROOT / "docs" / "resources" / "deploy-with-codex-prompt.md",
    ROOT / "docs" / "slack-knowledge-agent" / "brief.md",
    ROOT / "MEMORY.md",
)


class SlackSetupTests(unittest.TestCase):
    def load_manifest(self, path: Path) -> dict:
        return json.loads(path.read_text())

    def assert_minimal_course_app(self, manifest: dict) -> None:
        self.assertEqual(manifest["display_information"]["name"], "HR Policy Assistant")
        self.assertEqual(
            manifest["oauth_config"]["scopes"]["bot"],
            ["app_mentions:read", "chat:write", "reactions:write"],
        )
        self.assertNotIn("user", manifest["oauth_config"]["scopes"])
        self.assertFalse(manifest["features"]["app_home"]["messages_tab_enabled"])
        self.assertNotIn("slash_commands", manifest["features"])
        self.assertFalse(manifest["settings"]["incoming_webhooks"]["incoming_webhooks_enabled"])
        self.assertFalse(manifest["settings"]["interactivity"]["is_enabled"])
        self.assertFalse(manifest["settings"]["org_deploy_enabled"])
        self.assertFalse(manifest["settings"]["socket_mode_enabled"])
        self.assertFalse(manifest["settings"]["is_mcp_enabled"])

    def test_bootstrap_manifest_has_no_event_delivery(self) -> None:
        manifest = self.load_manifest(BOOTSTRAP_MANIFEST)

        self.assert_minimal_course_app(manifest)
        self.assertNotIn("event_subscriptions", manifest["settings"])

    def test_deployment_manifest_subscribes_only_to_app_mentions(self) -> None:
        manifest = self.load_manifest(DEPLOYED_MANIFEST)

        self.assert_minimal_course_app(manifest)
        subscriptions = manifest["settings"]["event_subscriptions"]
        self.assertEqual(subscriptions["bot_events"], ["app_mention"])
        self.assertEqual(
            subscriptions["request_url"],
            "https://replace-after-deployment.invalid/slack/events",
        )
        self.assertNotIn("user_events", subscriptions)

    def test_manifests_differ_only_by_event_subscriptions(self) -> None:
        bootstrap = self.load_manifest(BOOTSTRAP_MANIFEST)
        deployed = self.load_manifest(DEPLOYED_MANIFEST)

        deployed["settings"].pop("event_subscriptions")
        self.assertEqual(deployed, bootstrap)

    def test_v1_contract_has_no_support_user_group_configuration(self) -> None:
        for path in V1_CONTRACT_PATHS:
            with self.subTest(path=path.relative_to(ROOT)):
                contents = path.read_text()
                self.assertNotIn(REMOVED_SUPPORT_GROUP_SETTING, contents)
                self.assertNotIn(REMOVED_SUPPORT_GROUP_PHRASE, contents)

    def test_human_review_contract_uses_fixed_fallback(self) -> None:
        for path in FIXED_FALLBACK_PATHS:
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertIn(HUMAN_REVIEW_FALLBACK, path.read_text())


if __name__ == "__main__":
    unittest.main()
