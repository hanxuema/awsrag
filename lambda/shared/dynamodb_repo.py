from datetime import datetime, timezone

import boto3


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class MetadataRepository:
    def __init__(self, documents_table=None, jobs_table=None, audit_table=None, dynamodb_resource=None):
        self.documents_table_name = documents_table
        self.jobs_table_name = jobs_table
        self.audit_table_name = audit_table
        self._dynamodb = dynamodb_resource or boto3.resource("dynamodb")

    def enabled(self):
        return bool(self.documents_table_name)

    def _table(self, table_name):
        if not table_name:
            return None
        return self._dynamodb.Table(table_name)

    def mark_upload_requested(self, filename, content_type, bucket):
        table = self._table(self.documents_table_name)
        if not table:
            return
        table.put_item(
            Item={
                "filename": filename,
                "status": "upload_requested",
                "contentType": content_type,
                "bucket": bucket,
                "updatedAt": utc_now_iso(),
            }
        )

    def mark_indexing(self, filename, source_bucket):
        table = self._table(self.documents_table_name)
        if not table:
            return
        table.update_item(
            Key={"filename": filename},
            UpdateExpression="SET #status = :status, sourceBucket = :bucket, updatedAt = :updated",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":status": "indexing",
                ":bucket": source_bucket,
                ":updated": utc_now_iso(),
            },
        )

    def mark_indexed(self, filename, chunks_count, size_chars):
        table = self._table(self.documents_table_name)
        if not table:
            return
        table.update_item(
            Key={"filename": filename},
            UpdateExpression="SET #status = :status, chunksCount = :chunks, sizeChars = :size, updatedAt = :updated",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":status": "indexed",
                ":chunks": chunks_count,
                ":size": size_chars,
                ":updated": utc_now_iso(),
            },
        )

    def mark_deleted(self, filename):
        table = self._table(self.documents_table_name)
        if not table:
            return
        table.update_item(
            Key={"filename": filename},
            UpdateExpression="SET #status = :status, updatedAt = :updated",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={":status": "deleted", ":updated": utc_now_iso()},
        )
