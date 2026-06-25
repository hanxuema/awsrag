import os
import pathlib
import sys
import unittest
from unittest.mock import MagicMock, patch


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lambda"))

from shared.graph_repo import GraphRepository


class GraphRepositoryTests(unittest.TestCase):
    def test_session_uses_configured_database(self):
        driver = MagicMock()
        session = MagicMock()
        session.__enter__.return_value = MagicMock()
        driver.session.return_value = session

        repo = GraphRepository(uri="neo4j+s://example.databases.neo4j.io", username="neo4j", password="secret", database="neo4j")
        repo._driver = driver

        repo.search_facts("policy")

        driver.session.assert_called_once_with(database="neo4j")

    def test_database_can_come_from_environment(self):
        with patch.dict(os.environ, {"NEO4J_DATABASE": "neo4j"}):
            repo = GraphRepository(uri="neo4j+s://example.databases.neo4j.io")

        self.assertEqual(repo.database, "neo4j")


if __name__ == "__main__":
    unittest.main()
