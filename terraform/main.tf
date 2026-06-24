terraform {
  required_version = ">= 1.0.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# 1. Automate Lambda Packaging
resource "null_resource" "package_lambdas" {
  triggers = {
    upload_src          = filemd5("${path.module}/../lambda/upload/index.py")
    query_src           = filemd5("${path.module}/../lambda/query/index.py")
    ingest_src          = filemd5("${path.module}/../lambda/ingest/index.py")
    list_docs_src       = filemd5("${path.module}/../lambda/list_docs/index.py")
    agent_tool_src      = filemd5("${path.module}/../lambda/agent_tool/index.py")
    shared_response_src = filemd5("${path.module}/../lambda/shared/response.py")
    shared_dynamodb_src = filemd5("${path.module}/../lambda/shared/dynamodb_repo.py")
    shared_graph_src    = filemd5("${path.module}/../lambda/shared/graph_repo.py")
    script_src          = filemd5("${path.module}/../scripts/package_lambdas.py")
  }

  provisioner "local-exec" {
    command = "python3 ${path.module}/../scripts/package_lambdas.py"
  }
}

# 2. S3 Storage and Ingestion Buckets
resource "aws_s3_bucket" "upload_bucket" {
  bucket_prefix = "${var.project_name}-uploads-"
  force_destroy = true
  tags          = aws_servicecatalogappregistry_application.rag_app.application_tag
}

resource "aws_s3_bucket_cors_configuration" "upload_cors" {
  bucket = aws_s3_bucket.upload_bucket.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["PUT", "POST", "GET"]
    allowed_origins = ["*"]
    expose_headers  = ["ETag"]
    max_age_seconds = 3000
  }
}

# Storage bucket holds frontend static files and vector DB (index.json)
resource "aws_s3_bucket" "storage_bucket" {
  bucket_prefix = "${var.project_name}-storage-"
  force_destroy = true
  tags          = aws_servicecatalogappregistry_application.rag_app.application_tag
}

# Block public access for raw uploads, but allow public policy for static assets hosting
resource "aws_s3_bucket_public_access_block" "upload_block" {
  bucket                  = aws_s3_bucket.upload_bucket.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_public_access_block" "storage_block" {
  bucket                  = aws_s3_bucket.storage_bucket.id
  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_website_configuration" "website" {
  bucket = aws_s3_bucket.storage_bucket.id

  index_document {
    suffix = "index.html"
  }
}

# DynamoDB keeps document/job metadata out of the vector index files.
resource "aws_dynamodb_table" "documents" {
  name         = "${var.project_name}-documents"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "filename"
  tags         = aws_servicecatalogappregistry_application.rag_app.application_tag

  attribute {
    name = "filename"
    type = "S"
  }
}

resource "aws_dynamodb_table" "jobs" {
  name         = "${var.project_name}-jobs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "jobId"
  tags         = aws_servicecatalogappregistry_application.rag_app.application_tag

  attribute {
    name = "jobId"
    type = "S"
  }
}

resource "aws_dynamodb_table" "audit_events" {
  name         = "${var.project_name}-audit-events"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "eventId"
  tags         = aws_servicecatalogappregistry_application.rag_app.application_tag

  attribute {
    name = "eventId"
    type = "S"
  }
}

resource "aws_sqs_queue" "ingest_dlq" {
  name                      = "${var.project_name}-ingest-dlq"
  message_retention_seconds = 1209600
  tags                      = aws_servicecatalogappregistry_application.rag_app.application_tag
}

resource "aws_sqs_queue" "ingest_queue" {
  name                       = "${var.project_name}-ingest"
  visibility_timeout_seconds = 240
  message_retention_seconds  = 1209600
  tags                       = aws_servicecatalogappregistry_application.rag_app.application_tag

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.ingest_dlq.arn
    maxReceiveCount     = 3
  })
}

resource "aws_sqs_queue_policy" "allow_s3_ingest_events" {
  queue_url = aws_sqs_queue.ingest_queue.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowS3UploadBucketEvents"
        Effect = "Allow"
        Principal = {
          Service = "s3.amazonaws.com"
        }
        Action   = "sqs:SendMessage"
        Resource = aws_sqs_queue.ingest_queue.arn
        Condition = {
          ArnEquals = {
            "aws:SourceArn" = aws_s3_bucket.upload_bucket.arn
          }
        }
      }
    ]
  })
}

# 3. IAM Execution Role for Lambdas
resource "aws_iam_role" "lambda_role" {
  name = "${var.project_name}-lambda-role"
  tags = aws_servicecatalogappregistry_application.rag_app.application_tag

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_policy" "lambda_policy" {
  name        = "${var.project_name}-lambda-policy"
  description = "Execution policy for RAG lambda functions"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.upload_bucket.arn,
          "${aws_s3_bucket.upload_bucket.arn}/*",
          aws_s3_bucket.storage_bucket.arn,
          "${aws_s3_bucket.storage_bucket.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
          "sqs:ChangeMessageVisibility"
        ]
        Resource = [
          aws_sqs_queue.ingest_queue.arn,
          aws_sqs_queue.ingest_dlq.arn
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          aws_dynamodb_table.documents.arn,
          aws_dynamodb_table.jobs.arn,
          aws_dynamodb_table.audit_events.arn
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_role_attachment" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = aws_iam_policy.lambda_policy.arn
}

# 4. AWS Lambda Functions
resource "aws_lambda_function" "upload_url" {
  filename         = "${path.module}/build/upload.zip"
  source_code_hash = filebase64sha256("${path.module}/build/upload.zip")
  function_name    = "${var.project_name}-upload-url"
  role             = aws_iam_role.lambda_role.arn
  handler          = "index.handler"
  runtime          = "python3.12"
  timeout          = 30
  memory_size      = 128
  depends_on       = [null_resource.package_lambdas]
  tags             = aws_servicecatalogappregistry_application.rag_app.application_tag

  environment {
    variables = {
      UPLOAD_BUCKET   = aws_s3_bucket.upload_bucket.id
      DOCUMENTS_TABLE = aws_dynamodb_table.documents.name
      JOBS_TABLE      = aws_dynamodb_table.jobs.name
      AUDIT_TABLE     = aws_dynamodb_table.audit_events.name
    }
  }
}

resource "aws_lambda_function" "list_docs" {
  filename         = "${path.module}/build/list_docs.zip"
  source_code_hash = filebase64sha256("${path.module}/build/list_docs.zip")
  function_name    = "${var.project_name}-list-docs"
  role             = aws_iam_role.lambda_role.arn
  handler          = "index.handler"
  runtime          = "python3.12"
  timeout          = 30
  memory_size      = 128
  depends_on       = [null_resource.package_lambdas]
  tags             = aws_servicecatalogappregistry_application.rag_app.application_tag

  environment {
    variables = {
      DB_BUCKET       = aws_s3_bucket.storage_bucket.id
      DB_KEY          = "index.json"
      UPLOAD_BUCKET   = aws_s3_bucket.upload_bucket.id
      DOCUMENTS_TABLE = aws_dynamodb_table.documents.name
    }
  }
}

resource "aws_lambda_function" "query" {
  filename         = "${path.module}/build/query.zip"
  source_code_hash = filebase64sha256("${path.module}/build/query.zip")
  function_name    = "${var.project_name}-query"
  role             = aws_iam_role.lambda_role.arn
  handler          = "index.handler"
  runtime          = "python3.12"
  timeout          = 60
  memory_size      = 256
  depends_on       = [null_resource.package_lambdas]
  tags             = aws_servicecatalogappregistry_application.rag_app.application_tag

  environment {
    variables = {
      DB_BUCKET          = aws_s3_bucket.storage_bucket.id
      DB_KEY             = "index.json"
      EMBEDDING_MODEL_ID = var.embedding_model_id
      LLM_MODEL_ID       = var.llm_model_id
      NEO4J_URI          = var.neo4j_uri
      NEO4J_USERNAME     = var.neo4j_username
      NEO4J_PASSWORD     = var.neo4j_password
    }
  }
}

resource "aws_lambda_function" "ingest" {
  filename         = "${path.module}/build/ingest.zip"
  source_code_hash = filebase64sha256("${path.module}/build/ingest.zip")
  function_name    = "${var.project_name}-ingest"
  role             = aws_iam_role.lambda_role.arn
  handler          = "index.handler"
  runtime          = "python3.12"
  timeout          = 180
  memory_size      = 512
  depends_on       = [null_resource.package_lambdas]
  tags             = aws_servicecatalogappregistry_application.rag_app.application_tag

  environment {
    variables = {
      DB_BUCKET          = aws_s3_bucket.storage_bucket.id
      DB_KEY             = "index.json"
      EMBEDDING_MODEL_ID = var.embedding_model_id
      DOCUMENTS_TABLE    = aws_dynamodb_table.documents.name
      JOBS_TABLE         = aws_dynamodb_table.jobs.name
      AUDIT_TABLE        = aws_dynamodb_table.audit_events.name
      NEO4J_URI          = var.neo4j_uri
      NEO4J_USERNAME     = var.neo4j_username
      NEO4J_PASSWORD     = var.neo4j_password
    }
  }
}

resource "aws_lambda_function" "agent_tool" {
  filename         = "${path.module}/build/agent_tool.zip"
  source_code_hash = filebase64sha256("${path.module}/build/agent_tool.zip")
  function_name    = "${var.project_name}-agent-tool"
  role             = aws_iam_role.lambda_role.arn
  handler          = "index.handler"
  runtime          = "python3.12"
  timeout          = 60
  memory_size      = 256
  depends_on       = [null_resource.package_lambdas]
  tags             = aws_servicecatalogappregistry_application.rag_app.application_tag

  environment {
    variables = {
      DB_BUCKET          = aws_s3_bucket.storage_bucket.id
      DB_KEY             = "index.json"
      EMBEDDING_MODEL_ID = var.embedding_model_id
      LLM_MODEL_ID       = var.llm_model_id
      NEO4J_URI          = var.neo4j_uri
      NEO4J_USERNAME     = var.neo4j_username
      NEO4J_PASSWORD     = var.neo4j_password
    }
  }
}

# 5. S3 Upload Notification Event for Ingest
resource "aws_s3_bucket_notification" "upload_notification" {
  bucket = aws_s3_bucket.upload_bucket.id

  queue {
    queue_arn = aws_sqs_queue.ingest_queue.arn
    events    = ["s3:ObjectCreated:*", "s3:ObjectRemoved:*"]
  }

  depends_on = [aws_sqs_queue_policy.allow_s3_ingest_events]
}

resource "aws_lambda_event_source_mapping" "ingest_from_sqs" {
  event_source_arn = aws_sqs_queue.ingest_queue.arn
  function_name    = aws_lambda_function.ingest.arn
  batch_size       = 5
}

# 6. API Gateway Configuration
resource "aws_apigatewayv2_api" "http_api" {
  name          = "${var.project_name}-api"
  protocol_type = "HTTP"
  tags          = aws_servicecatalogappregistry_application.rag_app.application_tag

  cors_configuration {
    allow_headers = ["*"]
    allow_methods = ["*"]
    allow_origins = ["*"]
    max_age       = 300
  }
}

resource "aws_apigatewayv2_stage" "api_stage" {
  api_id      = aws_apigatewayv2_api.http_api.id
  name        = "$default"
  auto_deploy = true
}

# Integrations
resource "aws_apigatewayv2_integration" "upload_url" {
  api_id             = aws_apigatewayv2_api.http_api.id
  integration_type   = "AWS_PROXY"
  integration_method = "POST"
  integration_uri    = aws_lambda_function.upload_url.invoke_arn
}

resource "aws_apigatewayv2_integration" "list_docs" {
  api_id             = aws_apigatewayv2_api.http_api.id
  integration_type   = "AWS_PROXY"
  integration_method = "POST"
  integration_uri    = aws_lambda_function.list_docs.invoke_arn
}

resource "aws_apigatewayv2_integration" "query" {
  api_id             = aws_apigatewayv2_api.http_api.id
  integration_type   = "AWS_PROXY"
  integration_method = "POST"
  integration_uri    = aws_lambda_function.query.invoke_arn
}

resource "aws_apigatewayv2_integration" "agent_tool" {
  api_id             = aws_apigatewayv2_api.http_api.id
  integration_type   = "AWS_PROXY"
  integration_method = "POST"
  integration_uri    = aws_lambda_function.agent_tool.invoke_arn
}

# Routes
resource "aws_apigatewayv2_route" "upload_url_route" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST /api/upload-url"
  target    = "integrations/${aws_apigatewayv2_integration.upload_url.id}"
}

resource "aws_apigatewayv2_route" "list_docs_route" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "GET /api/documents"
  target    = "integrations/${aws_apigatewayv2_integration.list_docs.id}"
}

resource "aws_apigatewayv2_route" "delete_doc_route" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "DELETE /api/documents"
  target    = "integrations/${aws_apigatewayv2_integration.list_docs.id}"
}

resource "aws_apigatewayv2_route" "query_route" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST /api/chat"
  target    = "integrations/${aws_apigatewayv2_integration.query.id}"
}

resource "aws_apigatewayv2_route" "agent_tool_route" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST /api/agent-tool"
  target    = "integrations/${aws_apigatewayv2_integration.agent_tool.id}"
}

# Permissions for API Gateway to invoke lambdas
resource "aws_lambda_permission" "apigw_upload" {
  statement_id  = "AllowAPIGatewayInvokeUpload"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.upload_url.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}

resource "aws_lambda_permission" "apigw_list" {
  statement_id  = "AllowAPIGatewayInvokeList"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.list_docs.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}

resource "aws_lambda_permission" "apigw_query" {
  statement_id  = "AllowAPIGatewayInvokeQuery"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.query.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}

resource "aws_lambda_permission" "apigw_agent_tool" {
  statement_id  = "AllowAPIGatewayInvokeAgentTool"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.agent_tool.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}

resource "aws_lambda_permission" "bedrock_agent_tool" {
  statement_id  = "AllowBedrockAgentInvokeAgentTool"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.agent_tool.function_name
  principal     = "bedrock.amazonaws.com"
}

# 7. S3 Bucket policy to grant public read access for static website hosting
resource "aws_s3_bucket_policy" "storage_policy" {
  bucket = aws_s3_bucket.storage_bucket.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "PublicReadGetObject"
        Effect    = "Allow"
        Principal = "*"
        Action    = "s3:GetObject"
        Resource = [
          "${aws_s3_bucket.storage_bucket.arn}/index.html",
          "${aws_s3_bucket.storage_bucket.arn}/style.css",
          "${aws_s3_bucket.storage_bucket.arn}/app.js",
          "${aws_s3_bucket.storage_bucket.arn}/config.js"
        ]
      }
    ]
  })
}

# 8. Deploy Frontend Assets directly via S3 objects
resource "aws_s3_object" "frontend_html" {
  bucket       = aws_s3_bucket.storage_bucket.id
  key          = "index.html"
  source       = "${path.module}/../frontend/index.html"
  content_type = "text/html"
  etag         = filemd5("${path.module}/../frontend/index.html")
}

resource "aws_s3_object" "frontend_css" {
  bucket       = aws_s3_bucket.storage_bucket.id
  key          = "style.css"
  source       = "${path.module}/../frontend/style.css"
  content_type = "text/css"
  etag         = filemd5("${path.module}/../frontend/style.css")
}

resource "aws_s3_object" "frontend_js" {
  bucket       = aws_s3_bucket.storage_bucket.id
  key          = "app.js"
  source       = "${path.module}/../frontend/app.js"
  content_type = "application/javascript"
  etag         = filemd5("${path.module}/../frontend/app.js")
}

# Deploy dynamic config file that contains API Gateway endpoint URL
resource "aws_s3_object" "frontend_config" {
  bucket       = aws_s3_bucket.storage_bucket.id
  key          = "config.js"
  content      = "const API_BASE = '${aws_apigatewayv2_api.http_api.api_endpoint}';"
  content_type = "application/javascript"
}

# 9. AWS Service Catalog AppRegistry Application (for AWS "My Applications" Console)
resource "aws_servicecatalogappregistry_application" "rag_app" {
  name        = "${var.project_name}-app"
  description = "AWS Serverless RAG System application"
}
