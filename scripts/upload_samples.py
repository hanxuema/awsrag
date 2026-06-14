import os
import boto3

s3 = boto3.client('s3', region_name='us-east-1')
bucket = 'serverless-rag-uploads-20260610110002785400000002'

files = [
    'sample_data/paul_graham_essay.txt',
    'sample_data/bedrock_faq.txt',
    'sample_data/lambda_guidelines.txt'
]

for f in files:
    filename = os.path.basename(f)
    print(f"Uploading {f} to {bucket}/{filename}...")
    s3.upload_file(f, bucket, filename)
print("All sample files successfully uploaded!")
