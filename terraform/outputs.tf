output "website_url" {
  value       = "http://${aws_s3_bucket.storage_bucket.bucket}.s3-website-${var.aws_region}.amazonaws.com"
  description = "The URL of the S3 static website hosting the RAG UI"
}

output "api_endpoint" {
  value       = aws_apigatewayv2_api.http_api.api_endpoint
  description = "The raw URL of the API Gateway HTTP API"
}

output "upload_bucket_name" {
  value       = aws_s3_bucket.upload_bucket.id
  description = "The name of the S3 bucket where raw files are uploaded"
}

output "storage_bucket_name" {
  value       = aws_s3_bucket.storage_bucket.id
  description = "The name of the S3 bucket storing frontend files and vector index"
}

output "documents_table_name" {
  value       = aws_dynamodb_table.documents.name
  description = "DynamoDB table for document metadata"
}

output "ingest_queue_name" {
  value       = aws_sqs_queue.ingest_queue.name
  description = "SQS queue receiving S3 upload events for ingestion"
}

output "agent_tool_function_name" {
  value       = aws_lambda_function.agent_tool.function_name
  description = "Lambda function compatible with Bedrock Agent action groups"
}
