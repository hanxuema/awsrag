import os
import json
import boto3
try:
    from shared.graph_repo import GraphRepository
except ModuleNotFoundError:
    import pathlib
    import sys

    sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))
    from shared.graph_repo import GraphRepository

# Initialize clients
s3_client = boto3.client('s3')
bedrock_client = boto3.client('bedrock-runtime')

# Environment variables
DB_BUCKET = os.environ.get('DB_BUCKET')
DB_KEY = os.environ.get('DB_KEY', 'index.json')
EMBEDDING_MODEL_ID = os.environ.get('EMBEDDING_MODEL_ID', 'amazon.titan-embed-text-v2:0')
LLM_MODEL_ID = os.environ.get('LLM_MODEL_ID', 'anthropic.claude-3-haiku-20240307-v1:0')
graph_repo = GraphRepository()

# Global cache variables
cached_db = None
cached_db_etag = None

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
        print(f"Error generating query embedding: {e}")
        # Fallback to Titan V1
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
            print(f"Fallback query embedding failed: {e2}")
            raise e

# Global cache of document indexes: { key: { "etag": "...", "chunks": [...] } }
cached_indexes = {}

def load_db():
    global cached_indexes
    try:
        print("Listing document indexes in S3...")
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=DB_BUCKET, Prefix='indexes/')
        
        active_keys = set()
        chunks_aggregate = []
        documents_aggregate = {}
        
        # We will download modified/new indexes. For performance, we can do it in parallel or in loop.
        # Since standard Lambda handles parallel execution, a loop with in-memory caching is fast.
        for page in pages:
            for obj in page.get('Contents', []):
                key = obj['Key']
                # Skip the prefix folder placeholder itself if it exists
                if key == 'indexes/':
                    continue
                    
                active_keys.add(key)
                etag = obj.get('ETag')
                doc_name = key.replace('indexes/', '').replace('.json', '')
                
                # Check if we have this key in cache and it hasn't changed
                if key in cached_indexes and cached_indexes[key]['etag'] == etag:
                    # Cache hit!
                    entry = cached_indexes[key]
                else:
                    # Cache miss: Download and parse index file
                    print(f"Cache miss for {key}. Downloading index...")
                    response = s3_client.get_object(Bucket=DB_BUCKET, Key=key)
                    content = json.loads(response['Body'].read().decode('utf-8'))
                    
                    entry = {
                        "etag": etag,
                        "document": content.get("document", {}),
                        "chunks": content.get("chunks", [])
                    }
                    # Save to global cache
                    cached_indexes[key] = entry
                
                # Append chunks to aggregation list
                chunks_aggregate.extend(entry['chunks'])
                documents_aggregate[doc_name] = entry['document']
                
        # Clean up cache for any documents that were deleted from S3
        keys_to_remove = [k for k in cached_indexes if k not in active_keys]
        for k in keys_to_remove:
            print(f"Evicting deleted index from cache: {k}")
            del cached_indexes[k]
            
        print(f"Loaded database index: {len(documents_aggregate)} documents, {len(chunks_aggregate)} chunks.")
        return {"documents": documents_aggregate, "chunks": chunks_aggregate}
        
    except Exception as e:
        print(f"Error loading database index: {e}")
        # Fallback: consolidate whatever is in cache
        chunks_aggregate = []
        documents_aggregate = {}
        for key, entry in cached_indexes.items():
            doc_name = key.replace('indexes/', '').replace('.json', '')
            chunks_aggregate.extend(entry['chunks'])
            documents_aggregate[doc_name] = entry['document']
        return {"documents": documents_aggregate, "chunks": chunks_aggregate}

def dot_product(v1, v2):
    return sum(x * y for x, y in zip(v1, v2))

def search_vectors(query_vector, db_chunks, top_k=3):
    results = []
    for chunk in db_chunks:
        # Compute dot product (equals cosine similarity since embeddings are normalized to length 1)
        sim = dot_product(query_vector, chunk['embedding'])
        results.append({
            "doc_name": chunk['doc_name'],
            "chunk_id": chunk['chunk_id'],
            "text": chunk['text'],
            "similarity": sim
        })
    # Sort by similarity descending
    results.sort(key=lambda x: x['similarity'], reverse=True)
    return results[:top_k]


def vector_search(query, top_k=3):
    query_vector = get_embedding(query)
    db = load_db()
    return search_vectors(query_vector, db.get('chunks', []), top_k=top_k)


def format_graph_context(graph_result):
    facts = (graph_result or {}).get("facts", [])
    if not facts:
        return ""
    lines = []
    for fact in facts:
        source = fact.get("source")
        suffix = f" (source: {source})" if source else ""
        lines.append(f"- {fact.get('subject')} {fact.get('relationship')} {fact.get('object')}{suffix}")
    return "\n".join(lines)


def build_grounded_prompt(query, matched_chunks, graph_result=None):
    context_str = ""
    for match in matched_chunks:
        context_str += f"\n--- DOCUMENT SOURCE: {match['doc_name']} (Similarity: {match['similarity']:.3f}) ---\n"
        context_str += f"{match['text']}\n"

    graph_context = format_graph_context(graph_result)
    graph_section = f"\nGraph Context:\n{graph_context}\n" if graph_context else ""

    return (
        "You are an expert AI assistant that answers questions based solely on the provided context documents.\n"
        "Your task is to answer the user's question accurately using only the information presented in the context documents and graph context.\n\n"
        "Rules:\n"
        "1. Answer the question using the statements, claims, and facts found in the context documents. Treat all statements in the context as absolute truth. Do not assume, extrapolate, or challenge/doubt the claims in the documents.\n"
        "2. Only if the context documents and graph context do not contain any relevant information or statements to answer the question, state: 'I cannot find the answer in the provided context.' and do not attempt to answer using external knowledge.\n"
        "3. Be concise and structured in your answer.\n"
        "4. Cite the source files (e.g., 'bedrock_faq.txt') if appropriate when answering.\n\n"
        f"Context Documents:\n{context_str}\n"
        f"{graph_section}\n"
        f"User Question: {query}\n\n"
        "Answer:"
    )

def call_llm(prompt, temperature=0.3):
    try:
        print(f"Invoking LLM Model: {LLM_MODEL_ID}")
        
        # Determine payload structure based on model family
        if "nova" in LLM_MODEL_ID.lower():
            # Amazon Nova Model payload
            body = json.dumps({
                "messages": [
                    {
                        "role": "user",
                        "content": [{"text": prompt}]
                    }
                ],
                "inferenceConfig": {
                    "temperature": temperature
                }
            })
        elif "llama" in LLM_MODEL_ID.lower():
            # Meta Llama Model payload
            body = json.dumps({
                "prompt": prompt,
                "max_gen_len": 1000,
                "temperature": temperature
            })
        else:
            # Anthropic Claude Model payload (default fallback)
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1000,
                "temperature": temperature,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            })
            
        response = bedrock_client.invoke_model(
            modelId=LLM_MODEL_ID,
            contentType='application/json',
            accept='application/json',
            body=body
        )
        
        response_body = json.loads(response.get('body').read())
        
        # Parse response based on model family
        if "nova" in LLM_MODEL_ID.lower():
            return response_body['output']['message']['content'][0]['text']
        elif "llama" in LLM_MODEL_ID.lower():
            return response_body['generation']
        else:
            return response_body['content'][0]['text']
            
    except Exception as e:
        print(f"Error calling Bedrock LLM ({LLM_MODEL_ID}): {e}")
        raise e

def handler(event, context):
    print("Received query event:", json.dumps(event))
    
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
            
    query = body.get('query', '').strip()
    top_k = int(body.get('top_k', 3))
    temperature = float(body.get('temperature', 0.2))
    
    if not query:
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": "Query parameter is required"})
        }

    # 1. Embed query
    query_vector = get_embedding(query)
    
    # 2. Search index
    db = load_db()
    chunks = db.get('chunks', [])
    
    if not chunks:
        # DB is empty
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({
                "answer": "No documents have been indexed yet. Please upload some text, markdown, or PDF files to the knowledge base first.",
                "sources": []
            })
        }
        
    matched_chunks = search_vectors(query_vector, chunks, top_k=top_k)
    
    # 3. Build context prompt
    graph_result = graph_repo.search_facts(query, limit=5)
    system_prompt = build_grounded_prompt(query, matched_chunks, graph_result)
    
    # 4. Invoke Bedrock LLM
    answer = call_llm(system_prompt, temperature=temperature)
    
    # Clean matches for response (remove float arrays from chunk data if they exist, similarity is kept)
    sources = []
    for match in matched_chunks:
        sources.append({
            "doc_name": match['doc_name'],
            "text": match['text'],
            "similarity": float(match['similarity'])
        })
        
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*"
        },
        "body": json.dumps({
            "answer": answer,
            "sources": sources,
            "graph": graph_result
        })
    }
