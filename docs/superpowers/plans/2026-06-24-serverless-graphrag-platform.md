# Serverless GraphRAG Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evolve the existing AWS RAG prototype toward the SEEK role architecture while keeping the default deployment mostly serverless and idle-cost friendly.

**Architecture:** Keep the current S3 + API Gateway + Lambda + Bedrock core. Add SQS-based ingestion decoupling, DynamoDB document/job metadata, a Neo4j-compatible GraphRAG repository abstraction with safe no-op fallback, and a Bedrock-Agent-compatible tool Lambda. Avoid GitHub Actions and avoid always-on ECS in the default path.

**Tech Stack:** AWS Lambda Python 3.12, API Gateway HTTP API, S3, SQS, DynamoDB, Bedrock Runtime, optional Neo4j AuraDB Free/local Neo4j via bolt URI, Terraform local deploy.

---

## File Structure

- Modify `lambda/list_docs/index.py`: fix HTTP API v2 method detection and keep delete/list behavior compatible.
- Modify `lambda/upload/index.py`: add basic filename/content-type validation and DynamoDB metadata write when configured.
- Modify `lambda/ingest/index.py`: support S3 and SQS-wrapped S3 events, write DynamoDB job/document status, emit graph facts through a Neo4j-compatible repository abstraction.
- Modify `lambda/query/index.py`: reuse vector search, include optional graph context, expose reusable query helpers for agent tools.
- Create `lambda/shared/response.py`: shared JSON response helpers.
- Create `lambda/shared/dynamodb_repo.py`: optional DynamoDB metadata repository.
- Create `lambda/shared/graph_repo.py`: optional Neo4j-compatible GraphRAG repository with no-op fallback.
- Create `lambda/agent_tool/index.py`: Bedrock Agent action-group Lambda facade for vector search, graph search, document lookup, and answer generation.
- Modify `scripts/package_lambdas.py`: package shared modules and new Lambda.
- Modify `terraform/main.tf`: add DynamoDB tables, SQS queue/DLQ, event source mapping, agent tool Lambda, IAM permissions, environment variables, and narrow S3 public website policy to static assets only.
- Modify `terraform/variables.tf`: add GraphRAG and metadata config flags.
- Modify `terraform/outputs.tf`: output DynamoDB/SQS names and agent tool function.
- Create `tests/`: Python unittest coverage for method parsing, upload validation, retrieval ranking, event normalization, and agent tool routing.
- Modify `README.md` and docs: describe serverless architecture, deploy confirmation boundary, and realistic monthly cost posture.

## Tasks

### Task 1: Add regression tests for existing behavior and target behavior

**Files:**
- Create `tests/test_list_docs.py`
- Create `tests/test_upload.py`
- Create `tests/test_query.py`
- Create `tests/test_ingest.py`
- Create `tests/test_agent_tool.py`

- [ ] Write tests before production changes.
- [ ] Run `python3 -m unittest discover -s tests -v`.
- [ ] Confirm failures are caused by missing target behavior: HTTP API v2 DELETE, upload validation, SQS event normalization, GraphRAG context, and missing agent tool Lambda.

### Task 2: Add shared serverless support modules

**Files:**
- Create `lambda/shared/response.py`
- Create `lambda/shared/dynamodb_repo.py`
- Create `lambda/shared/graph_repo.py`

- [ ] Implement small dependency-light helpers.
- [ ] Keep Neo4j optional: if `NEO4J_URI` is absent, graph writes/searches return safe no-op results.
- [ ] Run targeted unit tests.

### Task 3: Update Lambda handlers

**Files:**
- Modify `lambda/upload/index.py`
- Modify `lambda/list_docs/index.py`
- Modify `lambda/ingest/index.py`
- Modify `lambda/query/index.py`
- Create `lambda/agent_tool/index.py`

- [ ] Fix HTTP API v2 method detection in document delete.
- [ ] Validate upload filenames and allowed extensions.
- [ ] Support SQS-wrapped S3 ingestion events.
- [ ] Persist document status to DynamoDB when configured.
- [ ] Add graph-derived context to query responses when configured.
- [ ] Add Bedrock Agent tool facade.
- [ ] Run all Python unit tests.

### Task 4: Update packaging and Terraform

**Files:**
- Modify `scripts/package_lambdas.py`
- Modify `terraform/main.tf`
- Modify `terraform/variables.tf`
- Modify `terraform/outputs.tf`

- [ ] Package shared modules into every Lambda ZIP.
- [ ] Add DynamoDB tables for documents, jobs, and audit events.
- [ ] Add SQS queue and DLQ between S3 and ingestion Lambda.
- [ ] Add event source mapping from SQS to ingestion Lambda.
- [ ] Add Agent tool Lambda and API route for local/manual testing.
- [ ] Restrict public S3 website bucket policy to frontend assets only.
- [ ] Run `terraform -chdir=terraform fmt` and `terraform -chdir=terraform validate` locally only.

### Task 5: Update documentation and cost model

**Files:**
- Modify `README.md`
- Modify `docs/architecture.md`
- Modify `docs/design-decisions.md`

- [ ] Document the new default serverless architecture.
- [ ] Document optional Neo4j AuraDB Free/local Neo4j setup.
- [ ] State that deployment must be run manually via local Terraform.
- [ ] State that AWS deploy/apply is not run by Codex without confirmation.
- [ ] Include realistic monthly costs: idle near $0-$1, light demo ~$1-$5, active demo ~$5-$20 excluding optional Neo4j Professional.

## Verification

- [ ] `python3 -m unittest discover -s tests -v`
- [ ] `python3 scripts/package_lambdas.py` if dependencies are already available or network is approved for pip.
- [ ] `terraform -chdir=terraform fmt`
- [ ] `terraform -chdir=terraform validate`
- [ ] Stop before `terraform apply`; ask the user for deploy confirmation.
