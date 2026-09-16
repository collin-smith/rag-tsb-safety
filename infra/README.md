# infra

Mixed approach, decided 2026-09-11 after actually testing the alternatives
in this environment rather than assuming:

- **S3 raw-zone bucket + IAM role**: plain AWS CLI (below). Created first,
  before the IaC question came up.
- **S3 Vectors bucket/index + Bedrock Knowledge Base + data source**:
  CloudFormation (`knowledge-base.yaml`). Chosen after checking:
  - **Terraform** is installed (`/snap/bin/terraform`) but broken in this
    sandbox: `snap-confine` lacks a required capability under this WSL2
    setup. The K8s portfolio project's `terraform validate`/apply actually
    run in GitHub Actions CI, not locally — so "same pattern as K8s" doesn't
    mean this session could run it here.
  - **CDK** is also broken locally: no `node` binary reachable from this
    bash session (the Windows-side npm/cdk install under `/mnt/c/...` isn't
    on this PATH), and `npx aws-cdk` fails with a misleading WSL1 error.
  - **CloudFormation** works today — it's pure `aws cloudformation` API
    calls, same execution path already proven throughout this project — and
    a schema check (`aws cloudformation describe-type`) confirmed native,
    first-class support for every resource type needed:
    `AWS::S3Vectors::VectorBucket`, `AWS::S3Vectors::Index`, and
    `AWS::Bedrock::KnowledgeBase` with `S3VectorsConfiguration`. No custom
    resources needed.

  Given only ~4-5 resources total for the whole project, this isn't an
  argument that CloudFormation/Terraform "should" be used at this scale in
  general — it's specific to this environment's tooling breakage plus the
  fact that CFN's teardown story (`aws cloudformation delete-stack`) is
  genuinely convenient for the cost-discipline narrative once you're
  writing a template anyway.

Every command below is reproducible and was actually run to provision this
project's AWS resources.

## Account / region

- Account: `805068224035`
- **Active region: `ca-central-1`** (migrated 2026-09-15/16 for data
  residency — see "Migration to ca-central-1" below; `us-east-1` resources
  have been torn down).
- Original region: `us-east-1` (Bedrock Knowledge Bases and S3 Vectors both
  confirmed available here — checked 2026-09-11 via `aws bedrock-agent
  create-knowledge-base help` and a live `aws s3vectors list-vector-buckets`
  call). Kept below for historical/debugging context; no longer live.

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

## Knowledge Base ingestion troubleshooting (2026-09-11/12)

Step 7 (create KB, sync, sanity-check chunk counts) hit a real bug worth
recording since the fix isn't obvious. Final state: **24/24 documents
INDEXED, 266 total chunks, 0 failures** — KB `LVBYRHRW4C`, data source
`OMIIV6SSYC`, index `reports-index`.

**Root cause**: the S3 Vectors index was created without
`MetadataConfiguration.NonFilterableMetadataKeys`. Bedrock KB writes each
chunk's full text into a reserved metadata key (`AMAZON_BEDROCK_TEXT`); if
that key isn't declared non-filterable *at index creation* (immutable
afterward — can't be fixed by updating an existing index), it counts
against a small filterable-metadata size cap and every document write
fails once a chunk's text exceeds it. Confirmed via AWS's own docs
("Using S3 Vectors with Amazon Bedrock Knowledge Bases") after every
document failed regardless of size or chunk count. Fixed in
`knowledge-base.yaml`'s `VectorIndex` resource — see the inline comment
there.

**Red herring that cost real debugging time**: CloudWatch showed severe
`InvocationThrottles` on the Titan Embeddings model during every failed
attempt (hundreds to 2000+/minute against a confirmed hard, non-adjustable
account quota of 60 requests/minute). This looked like the root cause and
prompted a chunk-size increase (300→1,500 tokens) to cut embedding-call
volume — which didn't fix it, because the real bug was downstream of
embedding (the S3 Vectors write). Best working theory: Bedrock's retry
logic, hitting a hard failure on every `PutVectors` call, retried the whole
chunk pipeline including re-embedding, manufacturing an apparent throttling
storm that was actually a symptom, not the cause. Once the metadata fix
landed, a full-corpus `start-ingestion-job` succeeded cleanly in one pass
with no throttling problem at all.

**Diagnostic path that got to the real answer**: manually replicating each
pipeline step by hand (`bedrock-runtime invoke-model` to embed a test
string, then `s3vectors put-vectors` to write it) both succeeded
individually with admin credentials, which ruled out the model and the
vector store as broken in isolation. `aws iam simulate-principal-policy`
against the KB execution role's exact actions/resources came back
"allowed" for everything, ruling out IAM. That narrowed it to something
specific to Bedrock's own orchestration of the write — which is what led
to checking the metadata configuration requirement.

`scripts/paced_ingest.py` was written as a workaround (submit documents a
few at a time via `ingest-knowledge-base-documents` instead of the
whole-corpus `start-ingestion-job`) before the real cause was found. Not
needed for the final successful run, but kept as a useful tool if a similar
symptom (mass ingestion failures) shows up again and needs isolating
document-by-document.

## Migration to ca-central-1 (2026-09-15/16) — data residency

TSB is a Canadian federal body; the original build ran entirely in
`us-east-1`, which Phase 2 of the article series named as an open,
unresolved gap. Re-checked 2026-09-15: `ca.amazon.nova-lite-v1:0` (this
account's generation model) is now a genuine all-Canada geographic
inference profile — AWS's own profile description reads *"Routes requests
to Nova Lite in ca-central-1 and ca-west-1"*, not the US/Global routing the
article originally described. Titan Embeddings V2 supports on-demand
invocation directly in `ca-central-1`, no inference profile needed. That
closes both halves of the residency gap, so the whole build was migrated.

**New resources (`ca-central-1`, account `805068224035`):**
- S3 raw-zone bucket: `rag-tsb-safety-raw-ca-805068224035`
- S3 Vectors bucket: `rag-tsb-safety-vectors`, index `reports-index`
  (same names as `us-east-1` — S3 Vectors bucket names are per-region, not
  globally unique, confirmed by creating both without conflict)
- Knowledge Base: `Z3Q6F4RTPY`, data source `3TRX9WE60L`
- Same execution role (`AmazonBedrockExecutionRoleForKB-rag-tsb-safety`) —
  its trust policy and permissions policy were extended (not replaced) to
  cover both regions' ARNs, so the `us-east-1` resources keep working until
  teardown.

**CloudFormation gotcha — could not get a diagnosis, worked around via CLI.**
`aws cloudformation deploy` of the same `knowledge-base.yaml` template that
worked cleanly in `us-east-1` fails instantly in `ca-central-1` at
changeset creation with `[AWS::EarlyValidation::PropertyValidation]` — no
resource-level detail, `describe-change-set`, `describe-stack-events`, and
`describe-change-set-hooks` all return the same generic message. Isolated
by building the template up one resource at a time
(`VectorBucket` → `+VectorIndex` → `+KnowledgeBase` → `+DataSource`,
mirroring the real template's structure): every combination passed
changeset creation and got to actual resource provisioning. The exact
production template with its real Parameters/Outputs sections and resource
names still fails identically, and testing with the real names directly
(bypassing CFN entirely) succeeded with no error at all. Best working
theory: something CFN's early-validation hook checks about the combination
of `Parameters`/`!Ref` indirection plus this template's specific resource
names/values in `ca-central-1` — never fully isolated, and the AWS-side
error gives no actionable detail to go further.

Given this project's existing precedent (the S3 bucket and IAM role were
already CLI-created rather than IaC, because Terraform/CDK are broken in
this sandbox — see above), the pragmatic choice was the same one: create
the `ca-central-1` Knowledge Base, data source, vector bucket, and index
directly via `aws s3vectors` / `aws bedrock-agent` CLI calls (all
succeeded immediately, first try, matching the CFN template's intended
configuration exactly). `infra/knowledge-base.yaml` still documents the
intended shape and is kept up to date, but is no longer the actual
provisioning path for this region — a genuine, disclosed gap in the
"CloudFormation works today" claim made when this file was first written.

**A second, more serious bug found during this migration: `retrieve_and_generate`
silently disconnects from the KB's own `retrieve()` results on this region's
Knowledge Base.** Discovered while re-running the demo: the "Lac-Mégantic
corrective actions" question, previously answered correctly, came back citing
an unrelated report (Gogama, R15H0021) instead. Isolated via a same-instant
paired comparison — standalone `retrieve()` ranked the correct report
(`R13D0054`) #1 by a clear score margin; `retrieve_and_generate()`'s own
internal citations never included it at all, consistently, across repeated
runs and multiple `numberOfResults` settings (5/10/20), on a fully-settled
370-document corpus (ruling out mid-ingestion churn as the cause). A
fixed-context test (identical retrieved chunks fed to both the on-demand
`us-east-1` model and the `ca-central-1` inference-profile model via
`converse()` directly) showed both generate correctly from the same
evidence — ruling out a generation-model behavior difference. The same
paired `retrieve()`-vs-`retrieve_and_generate()` comparison run against the
still-live `us-east-1` KB showed no divergence at all. Root cause not
isolated beyond "Bedrock's retrieve_and_generate orchestration and this
region's KB disagree with each other" — never reproduced on `us-east-1`,
never explained by anything in this project's own configuration.

**Residency verification (2026-09-16).** CloudTrail's account event history
(`lookup-events` for `bedrock.amazonaws.com`, no dedicated trail
configured, so this used the default 90-day lookup) shows every
`Converse` and `InvokeModel` call from this migration logged with
`awsRegion: ca-central-1` — none in `us-east-1` or elsewhere. This is
independent confirmation (AWS-logged, not self-reported) that every
generation and embedding call actually reached the Canadian regional
endpoint, closing the verification gap the original residency section left
open ("this build did none of it").

**Fix**: retired `retrieve_and_generate` entirely. `rag_utils.py`'s
`verified_retrieve_and_generate` now calls `retrieve()` and `converse()` as
two explicit, separately-inspectable steps — see that file's docstring for
the full evidence chain. Confirmed working: the demo's Lac-Mégantic and
recency-filter answers both reproduce correctly on this KB. This is also
arguably the more defensible design regardless of the bug: this project's
own `rag_utils.py` already existed specifically because Bedrock's
convenience APIs can't be trusted to report their own grounding accurately
(see that file's original docstring) — this finding is a sharper version of
exactly that concern, not an unrelated regression.

## Not yet created (step 8+)

## `us-east-1` teardown — completed 2026-09-16

Done as part of the `ca-central-1` migration, not the final project
teardown (the KB execution role is shared across both regions, so it was
narrowed rather than deleted):

```
aws bedrock-agent delete-data-source --knowledge-base-id LVBYRHRW4C --data-source-id OMIIV6SSYC
aws bedrock-agent delete-knowledge-base --knowledge-base-id LVBYRHRW4C
# KB deletion took ~45 minutes to leave DELETING state -- far slower than
# any other operation in this project; no failureReasons surfaced, so
# treated as a slow-but-normal S3-Vectors-backed KB deletion, not a stuck
# one, and it did eventually complete cleanly.
aws s3vectors delete-index --vector-bucket-name rag-tsb-safety-vectors --index-name reports-index
aws s3vectors delete-vector-bucket --vector-bucket-name rag-tsb-safety-vectors
aws s3 rm s3://rag-tsb-safety-raw-805068224035 --recursive  # 740 objects
aws s3api delete-bucket --bucket rag-tsb-safety-raw-805068224035
```

The shared execution role's trust and permissions policies were narrowed
back to `ca-central-1`-only (both had been extended to cover both regions
during migration) — role kept, not deleted, since `ca-central-1` still
depends on it. Verified the live KB still works post-narrowing with a
`retrieve()` call.

## Final teardown (once the article/demo material is fully captured)

```
aws bedrock-agent delete-data-source --knowledge-base-id Z3Q6F4RTPY --data-source-id 3TRX9WE60L
aws bedrock-agent delete-knowledge-base --knowledge-base-id Z3Q6F4RTPY
aws s3vectors delete-index --vector-bucket-name rag-tsb-safety-vectors --index-name reports-index
aws s3vectors delete-vector-bucket --vector-bucket-name rag-tsb-safety-vectors
aws iam delete-role-policy --role-name AmazonBedrockExecutionRoleForKB-rag-tsb-safety --policy-name kb-execution-permissions
aws iam delete-role --role-name AmazonBedrockExecutionRoleForKB-rag-tsb-safety
aws s3 rm s3://rag-tsb-safety-raw-ca-805068224035 --recursive
aws s3api delete-bucket --bucket rag-tsb-safety-raw-ca-805068224035
```
S3 Vectors has no idle cost, so there's no urgency to delete the vector
store specifically before this — unlike the OpenSearch Serverless scenario
this checklist step originally warned about. Region: `ca-central-1`
throughout (region flags omitted above where the CLI infers it from
resource ARN; add `--region ca-central-1` explicitly for the `s3` and
`iam` commands, which don't).
