from __future__ import annotations

import os
import unittest

from psycopg import connect
from psycopg.rows import dict_row
from support_agent_app.application.lifecycle import IncomingSupportRequest
from support_agent_app.database.migrations import apply_migrations
from support_agent_app.database.repositories.support_request_repository import (
    PostgresSupportRepository,
)

DATABASE_URL = os.getenv("DATABASE_URL", "")


@unittest.skipUnless(DATABASE_URL, "DATABASE_URL is required for Postgres integration tests")
class PostgresTestCase(unittest.TestCase):
    database_url = DATABASE_URL

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        apply_migrations(cls.database_url)

    def setUp(self) -> None:
        with connect(self.database_url) as connection:
            connection.execute("truncate table support_requests cascade")
        self.repository = PostgresSupportRepository(self.database_url)

    def accept_request(self, event_id: str = "Ev-test"):
        accepted = self.repository.accept_request(
            IncomingSupportRequest(
                slack_event_id=event_id,
                slack_team_id="T-test",
                slack_channel_id="C-test",
                slack_message_ts="100.001",
                slack_thread_ts="100.001",
                slack_user_id="U-test",
                question_text="A synthetic policy question.",
            )
        )
        self.repository.mark_queued(accepted.request_id)
        return accepted

    def fetchone(self, query: str, parameters=()):
        with connect(self.database_url, row_factory=dict_row) as connection:
            return connection.execute(query, parameters).fetchone()
