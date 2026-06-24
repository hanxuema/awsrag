import os
import json
import boto3
from botocore.config import Config
try:
    from shared.dynamodb_repo import MetadataRepository
    from shared.response import json_response
except ModuleNotFoundError:
    import pathlib
    import sys

    sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))
    from shared.dynamodb_repo import MetadataRepository
    from shared.response import json_response

# Initialize S3 client with signature v4 configuration
s3_client = boto3.client(
    's3',
    config=Config(signature_version='s3v4')
)

UPLOAD_BUCKET = os.environ.get('UPLOAD_BUCKET')
DOCUMENTS_TABLE = os.environ.get('DOCUMENTS_TABLE')
JOBS_TABLE = os.environ.get('JOBS_TABLE')
AUDIT_TABLE = os.environ.get('AUDIT_TABLE')
ALLOWED_EXTENSIONS = {'.txt', '.md', '.html', '.json', '.pdf'}
ALLOWED_CONTENT_TYPES = {
    'text/plain',
    'text/markdown',
    'text/html',
    'application/json',
    'application/pdf',
    'application/octet-stream',
}
metadata_repo = MetadataRepository(DOCUMENTS_TABLE, JOBS_TABLE, AUDIT_TABLE)


def validate_upload(filename, content_type):
    safe_filename = os.path.basename(filename or '').strip()
    if not safe_filename:
        return None, "filename parameter is required"
    _, ext = os.path.splitext(safe_filename)
    if ext.lower() not in ALLOWED_EXTENSIONS:
        return None, f"Unsupported file type: {ext or 'missing extension'}"
    if content_type and content_type not in ALLOWED_CONTENT_TYPES:
        return None, f"Unsupported content type: {content_type}"
    return safe_filename, None

def handler(event, context):
    print("Received upload-url request:", json.dumps(event))
    
    # Parse API Gateway request body
    body = {}
    if event.get('body'):
        try:
            body = json.loads(event['body'])
        except Exception as e:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"error": "Invalid JSON in request body"})
            }
            
    filename = body.get('filename', '').strip()
    content_type = body.get('contentType', 'application/octet-stream').strip()

    safe_filename, validation_error = validate_upload(filename, content_type)
    if validation_error:
        return json_response(400, {"error": validation_error})
    
    try:
        # Generate the presigned URL for S3 PUT object
        presigned_url = s3_client.generate_presigned_url(
            ClientMethod='put_object',
            Params={
                'Bucket': UPLOAD_BUCKET,
                'Key': safe_filename,
                'ContentType': content_type
            },
            ExpiresIn=300 # URL valid for 5 minutes
        )

        metadata_repo.mark_upload_requested(safe_filename, content_type, UPLOAD_BUCKET)
        
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({
                "uploadUrl": presigned_url,
                "key": safe_filename
            })
        }
    except Exception as e:
        print(f"Error generating presigned URL: {e}")
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({"error": f"Failed to generate upload URL: {str(e)}"})
        }
