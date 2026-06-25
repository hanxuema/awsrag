import os
import boto3

region = os.environ.get('AWS_REGION', 'ap-southeast-2')
bucket = os.environ['STORAGE_BUCKET']
s3 = boto3.client('s3', region_name=region)

print("Uploading frontend/app.js...")
s3.upload_file(
    'frontend/app.js', 
    bucket, 
    'app.js', 
    ExtraArgs={'ContentType': 'application/javascript'}
)
print("Uploaded app.js successfully!")
