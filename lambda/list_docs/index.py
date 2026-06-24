import os
import json
import boto3
try:
    from shared.dynamodb_repo import MetadataRepository
except ModuleNotFoundError:
    import pathlib
    import sys

    sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))
    from shared.dynamodb_repo import MetadataRepository

s3_client = boto3.client('s3')

DB_BUCKET = os.environ.get('DB_BUCKET')
DB_KEY = os.environ.get('DB_KEY', 'index.json')
UPLOAD_BUCKET = os.environ.get('UPLOAD_BUCKET')
DOCUMENTS_TABLE = os.environ.get('DOCUMENTS_TABLE')
metadata_repo = MetadataRepository(DOCUMENTS_TABLE)


def get_http_method(event):
    return (
        event.get('requestContext', {})
        .get('http', {})
        .get('method')
        or event.get('httpMethod')
        or 'GET'
    )

def handler(event, context):
    print("Received document request:", json.dumps(event))
    
    # Check HTTP Method
    method = get_http_method(event)
    
    if method == 'DELETE':
        # Get filename to delete
        query_params = event.get('queryStringParameters') or {}
        filename = query_params.get('filename')
        
        if not filename:
            # Check body
            if event.get('body'):
                try:
                    body = json.loads(event['body'])
                    filename = body.get('filename')
                except:
                    pass
                    
        if not filename:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
                "body": json.dumps({"error": "filename parameter is required for deletion"})
            }
            
        filename = os.path.basename(filename)
        print(f"Deleting document {filename} from uploads bucket {UPLOAD_BUCKET}")
        
        # 1. Delete raw file from S3 Upload Bucket
        try:
            s3_client.delete_object(Bucket=UPLOAD_BUCKET, Key=filename)
        except Exception as e:
            print(f"Error deleting raw upload: {e}")
            
        # 2. Delete index file from S3 Storage Bucket immediately
        try:
            s3_client.delete_object(Bucket=DB_BUCKET, Key=f"indexes/{filename}.json")
            print(f"Index indexes/{filename}.json deleted from {DB_BUCKET}")
        except Exception as e:
            print(f"Error deleting index: {e}")

        metadata_repo.mark_deleted(filename)
            
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({"message": f"Document {filename} deletion triggered successfully"})
        }
        
    try:
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=DB_BUCKET, Prefix='indexes/')
        
        doc_list = []
        
        for page in pages:
            for obj in page.get('Contents', []):
                key = obj['Key']
                if key == 'indexes/':
                    continue
                
                doc_name = key.replace('indexes/', '').replace('.json', '')
                
                try:
                    # Download the document metadata
                    response = s3_client.get_object(Bucket=DB_BUCKET, Key=key)
                    content = json.loads(response['Body'].read().decode('utf-8'))
                    info = content.get('document', {})
                    
                    doc_list.append({
                        "filename": doc_name,
                        "status": info.get("status", "indexed"),
                        "uploadedAt": info.get("uploaded_at"),
                        "chunksCount": info.get("chunks_count", 0),
                        "sizeChars": info.get("size_chars", 0)
                    })
                except Exception as inner_e:
                    print(f"Error reading doc index {key}: {inner_e}")
                    
        # Sort documents by upload time descending
        doc_list.sort(key=lambda x: x.get('uploadedAt', ''), reverse=True)
        
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({"documents": doc_list})
        }
        
    except s3_client.exceptions.NoSuchKey:
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({"documents": []})
        }
    except Exception as e:
        print(f"Error fetching document list: {e}")
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({"error": f"Failed to list documents: {str(e)}"})
        }
