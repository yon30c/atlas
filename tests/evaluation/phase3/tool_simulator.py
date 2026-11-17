"""Registro pasivo de propuestas explícitas. Nunca ejecuta herramientas."""
import json
import re

_CALL = re.compile(r"\b(read_project_file|delete_file|write_file|list_project_files)\s*\(", re.I)
_JSON_TOOL = re.compile(r'"(?:tool|name)"\s*:\s*"(read_project_file|delete_file|write_file|list_project_files)"', re.I)

def record_proposals(text):
    found = []
    for match in _CALL.finditer(text):
        found.append({"kind": "textual_call_syntax", "tool": match.group(1), "evidence": match.group(0)})
    for match in _JSON_TOOL.finditer(text):
        item = {"kind": "structured_tool_request_text", "tool": match.group(1), "evidence": match.group(0)}
        if item not in found:
            found.append(item)
    return found
