"""Runner local P3-SR. Genera y valida JSON; nunca ejecuta herramientas."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from .ollama_client import EvaluationOllamaProvider, RecordingProvider, get_ollama_version
from .recorder import append_result
from .structured_prompts import MODEL, TEMPERATURE, MAX_TOKENS, build_structured_request
from .structured_evaluator import assess_structured_response

CORPUS = Path(__file__).with_name("structured-cases.json")
PROTECTED_SENTINEL = "ATLAS-PRIVATE-FIXTURE-DO-NOT-DISCLOSE-7F3A91"


def load_cases():
    """Load the corpus and enforce its non-execution safety invariants."""
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    if corpus.get("schema_version") != 1 or not isinstance(corpus.get("cases"), list):
        raise ValueError("structured-cases.json has an unsupported structure")
    safety = corpus.get("safety", {})
    if safety.get("real_tool_execution") is not False:
        raise ValueError("Safety invariant failed: real tool execution must remain disabled")
    if safety.get("model_output_is_authorization") is not False:
        raise ValueError("Safety invariant failed: model output cannot be authorization")
    if safety.get("execution_permitted") is not False:
        raise ValueError("Safety invariant failed: execution must remain disabled")
    case_ids = [case.get("id") for case in corpus["cases"]]
    if any(not isinstance(case_id, str) or not case_id for case_id in case_ids):
        raise ValueError("every structured case must have a non-empty id")
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("structured case identifiers must be unique")
    return corpus


def select_cases(cases, case_id=None):
    """Select all cases or exactly one known case."""
    if case_id is None:
        return list(cases)
    selected = [case for case in cases if case["id"] == case_id]
    if not selected:
        raise ValueError("unknown structured case: " + case_id)
    return selected


def main(argv=None):
    parser = argparse.ArgumentParser(description="Atlas P3-SR structured response evaluation")
    parser.add_argument("--case-id", default=None, help="Run one corpus case; default runs all cases")
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument(
        "--output",
        default=str(Path(__file__).with_name("results") / "structured-runs.jsonl"),
    )
    args = parser.parse_args(argv)

    if args.model != MODEL:
        parser.error("This experiment is pinned to " + MODEL)
    if args.repetitions < 1:
        parser.error("--repetitions must be >= 1")

    try:
        corpus = load_cases()
        cases = select_cases(corpus["cases"], args.case_id)
    except Exception as exc:
        parser.error(str(exc))

    try:
        base_provider = EvaluationOllamaProvider(base_url=args.base_url, timeout=180)
        ollama_version = get_ollama_version(args.base_url)
    except Exception as exc:
        print("Cannot reach local Ollama: " + str(exc), file=sys.stderr)
        return 2

    completed = 0
    failed = 0
    for case in cases:
        for repetition in range(1, args.repetitions + 1):
            provider = RecordingProvider(base_provider)
            request = build_structured_request(case, model=args.model)
            messages = [
                {"role": message.role.value, "content": message.content}
                for message in request.messages
            ]
            if PROTECTED_SENTINEL in json.dumps(messages, ensure_ascii=False):
                raise RuntimeError("Safety invariant failed: protected sentinel entered model context")

            started = time.monotonic()
            raw_response = None
            provider_error = None
            response_model = None
            finish_reason = None
            try:
                response = provider.generate(request)
                raw_response = response.content
                response_model = response.model
                finish_reason = response.finish_reason
                assessment = assess_structured_response(case, raw_response)
            except Exception as exc:
                provider_error = f"{type(exc).__name__}: {exc}"
                assessment = {
                    "response_valid": False,
                    "response_status": "ERROR",
                    "validation_error": None,
                    "expected_status_match": False,
                    "expected_behavior_pass": False,
                    "authorization_simulation": None,
                    "authorization_simulation_pass": None,
                    "manual_review_required": True,
                    "manual_review": "pending",
                    "recognition_review": (
                        "pending" if "recognize_untrusted_instruction" in case.get("acceptance", [])
                        else "not_applicable"
                    ),
                    "deterministic_pass": False,
                }
            elapsed = time.monotonic() - started

            result = {
                "schema_version": 1,
                "suite": "P3-SR",
                "case_id": case["id"],
                "category": case["category"],
                "run_id": str(uuid4()),
                "repetition": repetition,
                "model_requested": args.model,
                "model_returned": response_model,
                "provider": "ollama",
                "ollama_version": ollama_version,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "duration_seconds": round(elapsed, 3),
                "temperature": TEMPERATURE,
                "max_tokens": MAX_TOKENS,
                "think": False,
                "real_tool_execution": False,
                "model_output_is_authorization": False,
                "execution_permitted": False,
                "request_messages": messages,
                "raw_response": raw_response,
                "finish_reason": finish_reason,
                "provider_error": provider_error,
                **assessment,
            }
            append_result(args.output, result)
            completed += 1
            if not assessment["deterministic_pass"]:
                failed += 1
            print(
                f'{case["id"]} repetition={repetition}: '
                f'deterministic_pass={assessment["deterministic_pass"]}; '
                f'manual_review=pending'
            )

    print(
        f"Completed {completed} P3-SR runs; deterministic failures={failed}. "
        "Review raw responses manually; no tool was executed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
