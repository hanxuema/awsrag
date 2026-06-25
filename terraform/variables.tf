variable "aws_region" {
  type        = string
  description = "AWS region to deploy the resources in"
  default     = "ap-southeast-2"
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

variable "neo4j_uri" {
  type        = string
  description = "Optional Neo4j-compatible bolt URI for GraphRAG. Leave empty for no-op graph mode."
  default     = ""
}

variable "neo4j_username" {
  type        = string
  description = "Optional Neo4j username for GraphRAG."
  default     = ""
}

variable "neo4j_password" {
  type        = string
  description = "Optional Neo4j password for GraphRAG."
  default     = ""
  sensitive   = true
}
