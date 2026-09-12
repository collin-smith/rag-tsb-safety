# infra

Plain AWS CLI, not Terraform — deliberate for this project's tactical/weekend
scope (a handful of resources: one S3 bucket, one IAM role, one Bedrock
Knowledge Base + S3 Vectors index). The K8s portfolio project uses Terraform
because it's a multi-stage, many-resource build; introducing Terraform state
management here would be disproportionate. Every command below is
reproducible and was actually run to provision this project's AWS resources.

## Account / region

- Account: `805068224035`
- Region: `us-east-1` (Bedrock Knowledge Bases and S3 Vectors both
  confirmed available here — checked 2026-09-11 via `aws bedrock-agent
  create-knowledge-base help` and a live `aws s3vectors list-vector-buckets`
  call)

## Prerequisites confirmed 2026-09-11

- **Bedrock model access** already granted, no console step needed:
  - Embeddings: `amazon.titan-embed-text-v2:0` (test-invoked successfully)
  - Converse-capable: `us.anthropic.claude-haiku-4-5-20251001-v1:0` (a
    cross-region inference profile — the bare model ID rejects on-demand
    throughput; use the `us.` prefixed profile ID instead)

## Resources created

1. **S3 raw-zone bucket**: `rag-tsb-safety-raw-805068224035`
   ```
   aws s3api create-bucket --bucket rag-tsb-safety-raw-805068224035 --region us-east-1
   aws s3api put-public-access-block --bucket rag-tsb-safety-raw-805068224035 \
     --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
   aws s3api put-bucket-tagging --bucket rag-tsb-safety-raw-805068224035 \
     --tagging 'TagSet=[{Key=project,Value=rag-tsb-safety}]'
   ```

2. **KB execution IAM role**: `AmazonBedrockExecutionRoleForKB-rag-tsb-safety`
   (ARN: `arn:aws:iam::805068224035:role/AmazonBedrockExecutionRoleForKB-rag-tsb-safety`)
   ```
   aws iam create-role --role-name AmazonBedrockExecutionRoleForKB-rag-tsb-safety \
     --assume-role-policy-document file://kb-execution-trust-policy.json \
     --description "Bedrock Knowledge Base execution role for rag-tsb-safety portfolio project" \
     --tags Key=project,Value=rag-tsb-safety

   aws iam put-role-policy --role-name AmazonBedrockExecutionRoleForKB-rag-tsb-safety \
     --policy-name kb-execution-permissions \
     --policy-document file://kb-execution-permissions-policy.json
   ```
   Trust policy (`kb-execution-trust-policy.json`) scopes `sts:AssumeRole` to
   `bedrock.amazonaws.com` for this account's Knowledge Base resources only.
   Permissions policy (`kb-execution-permissions-policy.json`) grants:
   read-only S3 access to the raw-zone bucket, `bedrock:InvokeModel` on the
   Titan Embeddings V2 model only, and S3 Vectors read/write scoped to a
   vector bucket named `rag-tsb-safety-vectors` (created in step 7 — the ARN
   is pre-declared here since IAM doesn't require the target resource to
   exist yet).

## Not yet created (step 7)

- S3 Vectors bucket + index (`rag-tsb-safety-vectors`)
- The Bedrock Knowledge Base itself

## Teardown (step 10)

```
aws bedrock-agent delete-knowledge-base --knowledge-base-id <id>
aws s3vectors delete-index --vector-bucket-name rag-tsb-safety-vectors --index-name <name>
aws s3vectors delete-vector-bucket --vector-bucket-name rag-tsb-safety-vectors
aws iam delete-role-policy --role-name AmazonBedrockExecutionRoleForKB-rag-tsb-safety --policy-name kb-execution-permissions
aws iam delete-role --role-name AmazonBedrockExecutionRoleForKB-rag-tsb-safety
aws s3 rm s3://rag-tsb-safety-raw-805068224035 --recursive
aws s3api delete-bucket --bucket rag-tsb-safety-raw-805068224035
```
S3 Vectors has no idle cost, so there's no urgency to delete the vector
store specifically before this — unlike the OpenSearch Serverless scenario
this checklist step originally warned about.
