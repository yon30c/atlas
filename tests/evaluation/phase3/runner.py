"""Runner local P3-PI-002. Ejecuta solo generación de texto; no hay herramientas."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from uuid import uuid4

# Ejecutar como módulo: python -m tests.evaluation.phase3.runner
ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.adapters.ollama import OllamaProvider
from atlas.adapters.ollama_assistant import OllamaResponseGenerator
from .evaluator import evaluate
from .ollama_client import RecordingProvider, get_ollama_version
from .policies import get_policy
from .prompts import build_request
from .recorder import append_result

CORPUS = Path(__file__).with_name("corpus.json")
MODEL = "gemma4:e2b-it-q4_K_M"

def main(argv=None):
    parser = argparse.ArgumentParser(description="Atlas Phase 3 isolated evaluation runner")
    parser.add_argument("--case-id", default="P3-PI-002-CROSS-PROJECT-EXFILTRATION")
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--repetitions", type=int, default=None)
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--output", default=str(Path(__file__).with_name("results") / "runs.jsonl"))
    args = parser.parse_args(argv)
    if args.model != MODEL:
        parser.error("This experiment is pinned to " + MODEL)
    if args.repetitions is not None and args.repetitions < 1:
        parser.error("--repetitions must be >= 1")

    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    case = next((item for item in corpus["planned_cases"] if item["id"] == args.case_id), None)
    if case is None:
        parser.error("Only planned cases can be run; unknown case: " + args.case_id)
    repetitions = args.repetitions or case["execution_plan"]["repetitions_per_combination"]
    matrix = case["execution_plan"]["language_matrix"]
    try:
        base_provider = OllamaProvider(base_url=args.base_url, timeout=180)
        ollama_version = get_ollama_version(args.base_url)
    except Exception as exc:
        print("Cannot reach local Ollama: " + str(exc), file=sys.stderr)
        return 2

    for pair_index, pair in enumerate(matrix, 1):
        policy = get_policy(pair["policy_language"])
        for repetition in range(1, repetitions + 1):
            provider = RecordingProvider(base_provider)
            generator = OllamaResponseGenerator(
                provider, model=args.model, system_prompt=policy.content,
                temperature=0.2, max_tokens=512,
            )
            request = build_request(case, policy, pair["injection_language"])
            started = time.monotonic()
            # Reuse the production request builder but call the recording provider
            # directly so provider failures remain visible to the harness.
            llm_request = generator._build_request(request)
            llm_response = provider.generate(llm_request)
            elapsed = time.monotonic() - started
            if llm_request is None or llm_response is None:
                raise RuntimeError("No complete LLM request/response captured")
            messages = [{"role": msg.role.value, "content": msg.content} for msg in llm_request.messages]
            if case["protected_fixture"]["sentinel"] in json.dumps(messages, ensure_ascii=False):
                raise RuntimeError("Safety invariant failed: protected sentinel entered model context")
            assessment = evaluate(case, llm_response.content)
            result = {
                "schema_version": 1, "case_id": case["id"],
                "run_id": str(uuid4()), "matrix_pair": pair_index,
                "repetition": repetition, "model_requested": args.model,
                "model_returned": llm_response.model, "provider": llm_response.provider,
                "ollama_version": ollama_version,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "duration_seconds": round(elapsed, 3),
                "policy_language": pair["policy_language"],
                "injection_language": pair["injection_language"],
                "policy_id": "p3-pi-002-v1", "policy_sha256": policy.sha256,
                "temperature": 0.2, "max_tokens": 512,
                "request_messages": messages, "raw_response": llm_response.content,
                "finish_reason": llm_response.finish_reason,
                **assessment,
            }
            append_result(args.output, result)
            print(f'{result["run_id"]}: automatic_pass={assessment["automatic_pass"]}; manual_review=pending')
    print(f"Completed {len(matrix) * repetitions} runs. Review every raw response manually.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
