import importlib.util
import json
import pathlib
import unittest
from unittest.mock import MagicMock, patch


MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "lambda" / "list_docs" / "index.py"


def load_module():
    spec = importlib.util.spec_from_file_location("list_docs_index", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ListDocsHandlerTests(unittest.TestCase):
    def test_delete_uses_http_api_v2_method(self):
        module = load_module()
        module.DB_BUCKET = "storage"
        module.UPLOAD_BUCKET = "uploads"
        module.s3_client = MagicMock()

        response = module.handler(
            {
                "requestContext": {"http": {"method": "DELETE"}},
                "queryStringParameters": {"filename": "../sample.txt"},
            },
            None,
        )

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertIn("sample.txt", body["message"])
        module.s3_client.delete_object.assert_any_call(Bucket="uploads", Key="sample.txt")
        module.s3_client.delete_object.assert_any_call(Bucket="storage", Key="indexes/sample.txt.json")


if __name__ == "__main__":
    unittest.main()
