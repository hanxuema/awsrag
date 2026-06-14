import boto3

s3 = boto3.client('s3', region_name='us-east-1')
bucket = 'serverless-rag-storage-20260610110002785400000001'

print("Uploading frontend/app.js...")
s3.upload_file(
    'frontend/app.js', 
    bucket, 
    'app.js', 
    ExtraArgs={'ContentType': 'application/javascript'}
)
print("Uploaded app.js successfully!")
