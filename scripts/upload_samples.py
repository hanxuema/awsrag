import os
import boto3

region = os.environ.get('AWS_REGION', 'ap-southeast-2')
bucket = os.environ['UPLOAD_BUCKET']
s3 = boto3.client('s3', region_name=region)

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
