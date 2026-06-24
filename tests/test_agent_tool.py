import importlib.util
import json
import pathlib
import unittest
from unittest.mock import MagicMock


MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "lambda" / "agent_tool" / "index.py"


def load_module():
    spec = importlib.util.spec_from_file_location("agent_tool_index", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AgentToolTests(unittest.TestCase):
    def test_routes_vector_search_action(self):
        module = load_module()
        module.query_service = MagicMock()
        module.query_service.vector_search.return_value = [{"doc_name": "doc.txt", "text": "match"}]

        response = module.handler(
            {
                "actionGroup": "KnowledgeTools",
                "function": "vector_search",
                "parameters": [{"name": "query", "value": "bedrock"}],
            },
            None,
        )

        body = json.loads(response["response"]["functionResponse"]["responseBody"]["TEXT"]["body"])
        self.assertEqual(body["results"][0]["doc_name"], "doc.txt")
        module.query_service.vector_search.assert_called_once_with("bedrock", top_k=3)


if __name__ == "__main__":
    unittest.main()
