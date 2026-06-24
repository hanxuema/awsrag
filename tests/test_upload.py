import importlib.util
import json
import pathlib
import unittest
from unittest.mock import MagicMock


MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "lambda" / "upload" / "index.py"


def load_module():
    spec = importlib.util.spec_from_file_location("upload_index", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class UploadHandlerTests(unittest.TestCase):
    def test_rejects_unsupported_extension_before_presign(self):
        module = load_module()
        module.UPLOAD_BUCKET = "uploads"
        module.s3_client = MagicMock()

        response = module.handler(
            {"body": json.dumps({"filename": "malware.exe", "contentType": "application/octet-stream"})},
            None,
        )

        self.assertEqual(response["statusCode"], 400)
        self.assertIn("Unsupported file type", json.loads(response["body"])["error"])
        module.s3_client.generate_presigned_url.assert_not_called()

    def test_presigns_supported_file_and_records_pending_metadata_when_configured(self):
        module = load_module()
        module.UPLOAD_BUCKET = "uploads"
        module.DOCUMENTS_TABLE = "docs"
        module.s3_client = MagicMock()
        module.s3_client.generate_presigned_url.return_value = "https://signed"
        module.metadata_repo = MagicMock()

        response = module.handler(
            {"body": json.dumps({"filename": "../policy.pdf", "contentType": "application/pdf"})},
            None,
        )

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertEqual(body["key"], "policy.pdf")
        self.assertEqual(body["uploadUrl"], "https://signed")
        module.metadata_repo.mark_upload_requested.assert_called_once()


if __name__ == "__main__":
    unittest.main()
