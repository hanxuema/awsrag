import importlib.util
import json
import pathlib
import unittest


MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "lambda" / "ingest" / "index.py"


def load_module():
    spec = importlib.util.spec_from_file_location("ingest_index", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class IngestEventTests(unittest.TestCase):
    def test_extracts_s3_records_from_sqs_wrapped_event(self):
        module = load_module()
        s3_event = {
            "Records": [
                {
                    "eventName": "ObjectCreated:Put",
                    "s3": {"bucket": {"name": "uploads"}, "object": {"key": "doc.txt"}},
                }
            ]
        }
        sqs_event = {"Records": [{"body": json.dumps(s3_event)}]}

        records = module.extract_s3_records(sqs_event)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["s3"]["object"]["key"], "doc.txt")


if __name__ == "__main__":
    unittest.main()
