import importlib.util
import pathlib
import unittest
from unittest.mock import MagicMock


MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "lambda" / "query" / "index.py"


def load_module():
    spec = importlib.util.spec_from_file_location("query_index", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class QueryGraphContextTests(unittest.TestCase):
    def test_build_prompt_includes_graph_context_when_available(self):
        module = load_module()
        chunks = [{"doc_name": "doc.txt", "similarity": 0.9, "text": "Vector fact."}]
        graph_result = {
            "facts": [
                {"subject": "Policy", "relationship": "REQUIRES", "object": "Approval", "source": "doc.txt"}
            ]
        }

        prompt = module.build_grounded_prompt("What is required?", chunks, graph_result)

        self.assertIn("Graph Context", prompt)
        self.assertIn("Policy REQUIRES Approval", prompt)
        self.assertIn("Vector fact.", prompt)


if __name__ == "__main__":
    unittest.main()
