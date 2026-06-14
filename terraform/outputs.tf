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
