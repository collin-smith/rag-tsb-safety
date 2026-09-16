"""A minimal tool-calling agent over the same Knowledge Base and extraction table.

Distinct from extract_structured_findings.py in one deliberate way: that
script is a fixed, deterministic loop -- *I* decided in advance to call the
extraction tool once per report. This script hands the model two tools and
lets IT decide which one a given natural-language question needs:

- `verified_semantic_query`: the existing citation-gated retrieve+generate
  path (rag_utils.verified_retrieve_and_generate -- explicit retrieve()
  then converse(), not Bedrock's retrieve_and_generate convenience API,
  which was found to silently diverge from the KB's own retrieve() results
  on the ca-central-1 KB, see rag_utils.py) -- for "what caused X"
  questions that plain RAG handles well.
- `aggregate_structured_findings`: exact counts/sums over the exhaustive
  extraction table built by extract_structured_findings.py -- for "how many"
  / "what fraction" questions that RAG cannot answer reliably (the
  documented "what it can't do: counting" failure in
  demo/insight_exploration.md).

This is the actual fix for that documented weak spot: instead of a human
remembering which script answers which kind of question, the model routes
itself. Uses Bedrock Converse's native tool use (toolConfig) -- no separate
Bedrock Agent resource or Lambda action groups needed for this scope.

Usage:
    .venv/bin/python3 scripts/agent_router.py
"""
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clock_fix  # noqa: E402  (must import before boto3 client creation; sandbox clock drifts)
import boto3  # noqa: E402
from botocore.exceptions import ClientError  # noqa: E402
from rag_utils import verified_retrieve_and_generate, estimate_cost_usd  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_PATH = os.path.join(REPO_ROOT, "manifest", "reports_manifest.csv")
FINDINGS_PATH = os.path.join(REPO_ROOT, "demo", "structured_findings.json")
OUT_DIR = os.environ.get("AGENT_OUT_DIR", os.path.join(REPO_ROOT, "demo"))
OUT_PATH = os.path.join(OUT_DIR, "agent_router_transcript.json")

REGION = "ca-central-1"
KNOWLEDGE_BASE_ID = "Z3Q6F4RTPY"
# ca-central-1 Nova Lite is INFERENCE_PROFILE-only (confirmed 2026-09-15);
# this is the all-Canada geographic profile, not a us-east-1 on-demand ARN.
GENERATION_MODEL_ARN = "arn:aws:bedrock:ca-central-1:805068224035:inference-profile/ca.amazon.nova-lite-v1:0"
GENERATION_MODEL_ID = "ca.amazon.nova-lite-v1:0"
NOVA_LITE_INPUT_RATE = 0.06
NOVA_LITE_OUTPUT_RATE = 0.24

SYSTEM_PROMPT = """You answer questions about a corpus of Transportation Safety Board of \
Canada (TSB) investigation reports (rail, pipeline, marine, aviation). You have two tools:

- aggregate_structured_findings: use for questions asking for a COUNT, FRACTION, TOTAL, or \
comparison across reports (e.g. "how many", "what fraction", "total fatalities", broken down \
by mode or not). This queries an exhaustive, pre-extracted table covering every report -- it \
gives exact numbers.
- verified_semantic_query: use for questions asking WHAT HAPPENED or WHAT CAUSED a specific \
incident or type of incident. This searches report text and returns a grounded, cited answer.

Always call exactly one tool before answering. Never guess a count or statistic yourself --
that is what aggregate_structured_findings is for."""

TOOL_CONFIG = {
    "tools": [
        {
            "toolSpec": {
                "name": "aggregate_structured_findings",
                "description": "Exact counts/totals over the full 57-report extraction table.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "metric": {
                                "type": "string",
                                "enum": [
                                    "count_reports",
                                    "count_prior_recommendation_unimplemented",
                                    "count_dangerous_goods_involved",
                                    "sum_fatalities",
                                ],
                            },
                            "mode": {
                                "type": "string",
                                "enum": ["rail", "pipeline", "marine", "aviation"],
                                "description": "Optional: restrict to one mode. Omit for a "
                                                "per-mode breakdown plus total.",
                            },
                        },
                        "required": ["metric"],
                    }
                },
            }
        },
        {
            "toolSpec": {
                "name": "verified_semantic_query",
                "description": "Grounded, cited answer to a what-happened/what-caused "
                                "question, searched over report text.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "question": {"type": "string"},
                            "mode": {
                                "type": "string",
                                "enum": ["rail", "pipeline", "marine", "aviation"],
                                "description": "Optional: restrict search to one mode.",
                            },
                        },
                        "required": ["question"],
                    }
                },
            }
        },
    ]
}


def load_mode_map():
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        return {r["report_id"]: r["mode"] for r in csv.DictReader(f)}


def load_findings():
    with open(FINDINGS_PATH, encoding="utf-8") as f:
        return json.load(f)


def run_aggregate(mode_map, findings, metric, mode=None):
    by_mode = {}
    for r in findings:
        m = mode_map.get(r["report_id"], "unknown")
        if mode and m != mode:
            continue
        by_mode.setdefault(m, {"count_reports": 0, "count_prior_recommendation_unimplemented": 0,
                                "count_dangerous_goods_involved": 0, "sum_fatalities": 0})
        by_mode[m]["count_reports"] += 1
        if r.get("prior_recommendation_unimplemented") is True:
            by_mode[m]["count_prior_recommendation_unimplemented"] += 1
        if r.get("dangerous_goods_involved") is True:
            by_mode[m]["count_dangerous_goods_involved"] += 1
        by_mode[m]["sum_fatalities"] += r.get("fatality_count") or 0

    total = sum(v[metric] for v in by_mode.values())
    result = {"metric": metric, "total": total}
    if not mode:
        result["by_mode"] = {m: v[metric] for m, v in by_mode.items()}
    return result


def run_semantic(bedrock_runtime, agent_runtime, question, mode=None):
    metadata_filter = {"equals": {"key": "mode", "value": mode}} if mode else None
    result = verified_retrieve_and_generate(
        agent_runtime, bedrock_runtime, question, KNOWLEDGE_BASE_ID, GENERATION_MODEL_ID,
        metadata_filter=metadata_filter, number_of_results=8,
    )
    if not result["grounded"]:
        return {"grounded": False, "answer": "No supporting evidence found in the corpus for this question."}
    return {"grounded": True, "answer": result["answer"],
            "distinct_reports_cited": result["distinct_reports_cited"]}


def execute_tool(name, tool_input, mode_map, findings, bedrock_runtime, agent_runtime):
    if name == "aggregate_structured_findings":
        return run_aggregate(mode_map, findings, tool_input["metric"], tool_input.get("mode"))
    elif name == "verified_semantic_query":
        return run_semantic(bedrock_runtime, agent_runtime, tool_input["question"], tool_input.get("mode"))
    raise ValueError(f"unknown tool: {name}")


def converse_with_retry(bedrock_runtime, messages):
    """Nova Lite has a reproducible tool-use decoding failure on at least one
    entity name in this corpus (Lac-Megantic): either a hard
    ModelErrorException ("invalid sequence as part of ToolUse") or a silent
    degeneration into blank-line filler that burns the whole token budget
    without ever emitting a toolUse block. Both are deterministic at
    temperature=0. One retry at temperature=0.3 reliably breaks the pattern
    without materially changing answer quality for these short, factual
    questions.
    """
    for temperature in (0, 0.3):
        try:
            response = bedrock_runtime.converse(
                modelId=GENERATION_MODEL_ID,
                system=[{"text": SYSTEM_PROMPT}],
                messages=messages,
                toolConfig=TOOL_CONFIG,
                inferenceConfig={"maxTokens": 500, "temperature": temperature},
            )
        except ClientError as e:
            if "invalid sequence as part of ToolUse" in str(e) and temperature == 0:
                continue  # retry once at higher temperature
            raise

        output_message = response["output"]["message"]
        stalled = (response.get("stopReason") == "max_tokens" and
                   not any("toolUse" in b for b in output_message["content"]))
        if stalled and temperature == 0:
            continue  # same failure family, silent form -- retry once
        return response

    return response  # both attempts exhausted; return whatever the last one gave


def is_degenerate(text):
    """Nova Lite's tool-use decoder can lock onto blank-line filler and never
    recover, even across a temperature bump (observed reproducibly on
    "Lac-Megantic" phrasings -- not a stochastic fluke). Heuristic: strip the
    one legitimate <thinking> block and see if anything substantive is left.
    """
    import re
    stripped = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL).strip()
    return len(stripped) < 20


def ask(bedrock_runtime, agent_runtime, mode_map, findings, question):
    messages = [{"role": "user", "content": [{"text": question}]}]
    total_in, total_out = 0, 0
    tool_calls = []

    for _ in range(3):  # cap the loop; two tool calls max expected in practice
        response = converse_with_retry(bedrock_runtime, messages)
        usage = response.get("usage", {})
        total_in += usage.get("inputTokens", 0)
        total_out += usage.get("outputTokens", 0)

        output_message = response["output"]["message"]
        messages.append(output_message)

        if response.get("stopReason") != "tool_use":
            final_text = "".join(b.get("text", "") for b in output_message["content"])
            if not tool_calls and is_degenerate(final_text):
                # Routing itself failed to produce any tool call and the model's
                # own text is empty filler. Fail safe: default to the grounded
                # semantic path with the raw question rather than surface garbage.
                fallback = run_semantic(bedrock_runtime, agent_runtime, question)
                return {"question": question, "final_answer": fallback["answer"],
                        "tool_calls": [{"tool": "verified_semantic_query (fallback)",
                                         "input": {"question": question}, "result": fallback}],
                        "fallback_used": True,
                        "input_tokens": total_in, "output_tokens": total_out}
            return {"question": question, "final_answer": final_text, "tool_calls": tool_calls,
                    "input_tokens": total_in, "output_tokens": total_out}

        tool_result_content = []
        for block in output_message["content"]:
            if "toolUse" in block:
                tu = block["toolUse"]
                result = execute_tool(tu["name"], tu["input"], mode_map, findings, bedrock_runtime, agent_runtime)
                tool_calls.append({"tool": tu["name"], "input": tu["input"], "result": result})
                tool_result_content.append({
                    "toolResult": {"toolUseId": tu["toolUseId"], "content": [{"json": result}]}
                })
        messages.append({"role": "user", "content": tool_result_content})

    return {"question": question, "final_answer": "(exceeded tool-call loop limit)",
            "tool_calls": tool_calls, "input_tokens": total_in, "output_tokens": total_out}


def main():
    bedrock_runtime = boto3.client("bedrock-runtime", region_name=REGION)
    agent_runtime = boto3.client("bedrock-agent-runtime", region_name=REGION)
    mode_map = load_mode_map()
    findings = load_findings()

    questions = [
        "How many reports cite an unimplemented prior recommendation, broken down by mode?",
        "What caused the Lac-Megantic derailment?",
        "What fraction of pipeline reports involved dangerous goods?",
    ]

    results = []
    total_in, total_out = 0, 0
    for q in questions:
        print(f"\n{'=' * 80}\nQ: {q}")
        try:
            r = ask(bedrock_runtime, agent_runtime, mode_map, findings, q)
        except ClientError as e:
            # converse_with_retry already retried once at a bumped
            # temperature; a ClientError surfacing here means that retry
            # didn't clear it. Record the failure and keep going rather
            # than losing every remaining question to one bad routing call.
            print(f"  -> ROUTING FAILED after retry: {e}")
            r = {"question": q, "final_answer": None, "tool_calls": [],
                 "input_tokens": 0, "output_tokens": 0, "error": str(e)}
        for tc in r["tool_calls"]:
            print(f"  -> tool: {tc['tool']}({tc['input']})")
        print(f"A: {r['final_answer']}")
        results.append(r)
        total_in += r["input_tokens"]
        total_out += r["output_tokens"]

    cost = estimate_cost_usd(total_in, total_out, NOVA_LITE_INPUT_RATE, NOVA_LITE_OUTPUT_RATE)
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\n{'=' * 80}\nTokens: {total_in} in / {total_out} out. "
          f"Measured cost @ Nova Lite rates: ${cost:.4f}")
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
