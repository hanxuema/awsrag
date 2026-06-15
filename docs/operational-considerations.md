# Operational & Production Considerations

This document details the operational, observability, security, and reliability considerations for maintaining the Serverless RAG system in a production environment.

---

## 1. Observability: Logging & Monitoring

For production grade readiness, we transition from default print logs to structured telemetry:

*   **Structured Logging**: Implement JSON structured logs in all Lambda handlers to include metadata such as `request_id`, `function_name`, `error_type`, and `duration_ms`. This enables writing advanced **CloudWatch Logs Insights** queries.
*   **Custom CloudWatch Metrics**: Emit custom metrics via **CloudWatch Embedded Metric Format (EMF)**:
    *   `EmbeddingLatency`: Time taken to call Bedrock Titan Embeddings.
    *   `InferenceLatency`: Time taken for Bedrock LLM generation.
    *   `IndexLoadTime`: Time taken to download and load JSON index files from S3.
    *   `SearchAccuracy`: Similarity scores of retrieved top chunks (to identify context drift).
*   **Distributed Tracing**: Enable **AWS X-Ray** on API Gateway and Lambda functions to visualize latency bottlenecks across S3, Bedrock, and internal processing.

---

## 2. Error Handling & Resilience

*   **Transient Dependency Failures**: Calls to Amazon Bedrock or S3 can experience transient network issues. We implement **exponential backoff with jitter** for all AWS SDK client calls using standard boto3 config tuning:
    ```python
    from botocore.config import Config
    config = Config(
        retries = {
            'max_attempts': 5,
            'mode': 'standard' # Automatically handles exponential backoff/jitter
        }
    )
    ```
*   **Bedrock Throttling (HTTP 429)**: Amazon Bedrock enforces Request Rate limits. When throttling occurs, the system should catch the client error, fallback to cached answers where appropriate, or enqueue the request for retry.
*   **Ingestion DLQ (Dead-Letter Queue)**: If the document ingestion Lambda fails (e.g. corrupted PDF file, out of memory, timeout), the failure is routed to an **Amazon SQS Dead-Letter Queue (DLQ)**. This fires a CloudWatch Alarm, notifying operators to manually inspect or reprocess the file.

---

## 3. Security Boundaries & IAM

*   **Least Privilege Access Control**: The Lambda execution role ([lambda_policy](file:///Users/xavier/src/rag/terraform/main.tf#L99-L139)) is strictly limited:
    *   No wildcards (`*`) for S3 permissions; actions are restricted specifically to the uploads and storage bucket ARNs.
    *   `bedrock:InvokeModel` is granted exclusively to trigger Titan Embeddings and LLM models.
*   **S3 Security**:
    *   The raw upload S3 bucket blocks all public ACLs and bucket policies (`block_public_policy = true`).
    *   Data is encrypted at rest using S3 Managed Keys (SSE-S3) by default.
*   **Secrets Management**: There are **no API keys, database passwords, or hardcoded credentials** stored in the repository. AWS SDK credentials are dynamically provided by the Lambda execution role. For external model integrations in the future, we would load secrets at runtime using **AWS Secrets Manager**.

---

## 4. Cost Governance & Alerting

Although idle costs are $0, spikes in usage can generate high Bedrock costs.
*   **AWS Budgets**: Configure an AWS Budget with an email alert threshold (e.g., alert at $5.00/month cumulative cost) to detect runaway recursive API calls or accidental denial of service (DoS) attacks.
*   **API Gateway Rate Limiting**: Configure API Gateway Throttling limits (e.g. 5 requests per second per IP) to prevent malicious actors from exhausting the Bedrock budget.

---

## 5. Failure Scenarios & Mitigations

| Failure Scenario | Impact | Mitigation Strategy |
| :--- | :--- | :--- |
| **Ingestion Lambda Out-of-Memory** | Ingestion of very large documents (e.g., 50MB PDF) crashes the Lambda. | Set a hard limit on upload file size (e.g., max 5MB) in the client, and allocate up to 1024MB memory to the Lambda to speed up parsing. |
| **Bedrock Service Outage** | Users cannot ask questions or get embeddings. | Store query answers in a temporary DynamoDB cache, or fallback gracefully with a user-friendly UI error message. |
| **Index Serialization Drift** | Corrupted S3 index JSON crashes the query parser. | Wrap the `load_db` code in a strict `try-except` block. Skip any unparseable JSON files, log a warning to CloudWatch, and parse remaining valid documents. |
| **State Inconsistency** | Raw file deleted from uploads bucket, but index file remains in storage bucket. | Implement a daily scheduled Lambda cleanup task to reconcile the index list in the storage bucket with the uploads bucket. |
