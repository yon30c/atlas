"""Proveedor decorador para capturar la respuesta LLM completa sin cambiar runtime."""
import json
from urllib.request import ProxyHandler, Request, build_opener

class RecordingProvider:
    def __init__(self, provider):
        self.provider = provider
        self.last_request = None
        self.last_response = None

    def generate(self, request):
        self.last_request = request
        response = self.provider.generate(request)
        self.last_response = response
        return response

def get_ollama_version(base_url="http://127.0.0.1:11434", timeout=5.0):
    opener = build_opener(ProxyHandler({}))
    req = Request(base_url.rstrip("/") + "/api/version", headers={"Accept": "application/json"})
    with opener.open(req, timeout=timeout) as response:
        payload = json.loads(response.read())
    if not isinstance(payload, dict) or not isinstance(payload.get("version"), str):
        raise RuntimeError("Ollama /api/version returned an invalid response")
    return payload["version"]
