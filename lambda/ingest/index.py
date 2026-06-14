import os
import json
import urllib.parse
import boto3
from datetime import datetime

# Initialize clients
s3_client = boto3.client('s3')
bedrock_client = boto3.client('bedrock-runtime')

# Environment variables
DB_BUCKET = os.environ.get('DB_BUCKET')
DB_KEY = os.environ.get('DB_KEY', 'index.json')
EMBEDDING_MODEL_ID = os.environ.get('EMBEDDING_MODEL_ID', 'amazon.titan-embed-text-v2:0')

def get_text_from_pdf(file_path):
    try:
        from pypdf import PdfReader
        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text
    except Exception as e:
        print(f"Error reading PDF: {e}")
        raise e

def chunk_text(text, chunk_size=600, overlap=120):
    # Normalize line endings
    text = text.replace('\r\n', '\n')
    
    # Split into paragraphs by double newlines
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    
    chunks = []
    for para in paragraphs:
        if len(para) <= chunk_size:
            chunks.append(para)
        else:
            # Paragraph is too long, split into sentences
            import re
            sentences = re.split(r'(?<=[.!?])\s+', para)
            
            current_chunk = ""
            for sentence in sentences:
                if len(current_chunk) + len(sentence) + 1 <= chunk_size:
                    current_chunk = f"{current_chunk} {sentence}".strip()
                else:
                    if current_chunk:
                        chunks.append(current_chunk)
                    
                    if len(sentence) > chunk_size:
                        # Single sentence is too long, split by characters
                        start = 0
                        while start < len(sentence):
                            chunks.append(sentence[start:start+chunk_size])
                            start += chunk_size - overlap
                        current_chunk = ""
                    else:
                        current_chunk = sentence
            if current_chunk:
                chunks.append(current_chunk)
    return chunks

def get_embedding(text):
    try:
        body = json.dumps({
            "inputText": text,
            "dimensions": 512,
            "normalize": True
        })
        response = bedrock_client.invoke_model(
            modelId=EMBEDDING_MODEL_ID,
            contentType='application/json',
            accept='application/json',
            body=body
        )
        response_body = json.loads(response.get('body').read())
        return response_body.get('embedding')
    except Exception as e:
        print(f"Error generating embedding for text '{text[:30]}...': {e}")
        # Fallback to Titan V1 structure if V2 fails (no dimensions param)
        try:
            body = json.dumps({"inputText": text})
            response = bedrock_client.invoke_model(
                modelId='amazon.titan-embed-text-v1',
                contentType='application/json',
                accept='application/json',
                body=body
            )
            response_body = json.loads(response.get('body').read())
            return response_body.get('embedding')
        except Exception as e2:
            print(f"Fallback to Titan V1 failed: {e2}")
            raise e

def save_doc_index(doc_name, metadata, chunks):
    try:
        doc_index = {
            "document": metadata,
            "chunks": chunks
        }
        # Save to a unique key per document
        index_key = f"indexes/{doc_name}.json"
        s3_client.put_object(
            Bucket=DB_BUCKET,
            Key=index_key,
            Body=json.dumps(doc_index, indent=2),
            ContentType='application/json'
        )
        print(f"Document index successfully written to S3: {index_key}")
    except Exception as e:
        print(f"Error saving document index to S3: {e}")
        raise e

def handler(event, context):
    print("Received event:", json.dumps(event))
    
    # Process S3 Event
    for record in event.get('Records', []):
        src_bucket = record['s3']['bucket']['name']
        src_key = urllib.parse.unquote_plus(record['s3']['object']['key'])
        event_name = record.get('eventName', '')
        
        # Don't trigger on files written to the index folder or UI assets
        if src_key.startswith('indexes/') or src_key.startswith('frontend/') or src_key == 'index.json':
            continue
            
        doc_name = os.path.basename(src_key)
            
        # Handle S3 deletion event
        if 'ObjectRemoved' in event_name:
            print(f"File deletion detected: {doc_name} from bucket {src_bucket}")
            index_key = f"indexes/{doc_name}.json"
            try:
                s3_client.delete_object(Bucket=DB_BUCKET, Key=index_key)
                print(f"Successfully deleted document index: {index_key}")
            except Exception as e:
                print(f"Error deleting index file: {e}")
            continue
            
        print(f"Processing file {src_key} from bucket {src_bucket}")
        
        # Download file to Lambda /tmp
        local_filename = os.path.join('/tmp', doc_name)
        s3_client.download_file(src_bucket, src_key, local_filename)
        
        file_ext = os.path.splitext(src_key)[1].lower()
        extracted_text = ""
        
        # Extract text based on file format
        if file_ext == '.pdf':
            extracted_text = get_text_from_pdf(local_filename)
        elif file_ext in ['.txt', '.md', '.html', '.json']:
            with open(local_filename, 'r', encoding='utf-8', errors='ignore') as f:
                extracted_text = f.read()
        else:
            print(f"Unsupported file format: {file_ext}")
            continue

        print(f"Extracted {len(extracted_text)} characters of text.")
        
        # Chunk text
        text_chunks = chunk_text(extracted_text)
        print(f"Split document into {len(text_chunks)} chunks.")
        
        doc_name = os.path.basename(src_key)
        
        # Process chunks and get embeddings
        new_chunks = []
        for idx, chunk in enumerate(text_chunks):
            embedding = get_embedding(chunk)
            new_chunks.append({
                "doc_name": doc_name,
                "chunk_id": f"{doc_name}_{idx}",
                "text": chunk,
                "embedding": embedding
            })
        
        # Prepare metadata and save unique index file
        metadata = {
            "status": "indexed",
            "uploaded_at": datetime.utcnow().isoformat() + "Z",
            "chunks_count": len(text_chunks),
            "size_chars": len(extracted_text)
        }
        
        save_doc_index(doc_name, metadata, new_chunks)
        print(f"Successfully finished ingestion of {doc_name}")
        
    return {
        "statusCode": 200,
        "body": json.dumps({"message": "Processing completed"})
    }
