"""Persistencia local JSONL; no sincroniza resultados ni datos privados."""
import json
from pathlib import Path

def append_result(path, result):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
