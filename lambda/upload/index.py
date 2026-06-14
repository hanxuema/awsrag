import os
import json
import boto3
from botocore.config import Config

# Initialize S3 client with signature v4 configuration
s3_client = boto3.client(
    's3',
    config=Config(signature_version='s3v4')
)

UPLOAD_BUCKET = os.environ.get('UPLOAD_BUCKET')

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
    
    if not filename:
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": "filename parameter is required"})
        }
        
    # Standardize filename to prevent path traversal
    safe_filename = os.path.basename(filename)
    
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
