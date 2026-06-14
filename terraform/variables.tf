variable "aws_region" {
  type        = string
  description = "AWS region to deploy the resources in"
  default     = "us-east-1"
}

variable "project_name" {
  type        = string
  description = "Prefix name for all resource groups to keep them unique"
  default     = "serverless-rag"
}

variable "embedding_model_id" {
  type        = string
  description = "Bedrock model ID for generating text embeddings"
  default     = "amazon.titan-embed-text-v2:0"
}

variable "llm_model_id" {
  type        = string
  description = "Bedrock model ID for text generation (Amazon Nova Micro)"
  default     = "amazon.nova-micro-v1:0"
}
