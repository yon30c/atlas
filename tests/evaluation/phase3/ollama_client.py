"""Cliente experimental Ollama: captura evidencia y desactiva thinking solo en el harness."""
import json
from urllib.request import ProxyHandler, Request, build_opener

from atlas.adapters.ollama import OllamaProvider


class EvaluationOllamaProvider(OllamaProvider):
    """OllamaProvider con thinking desactivado para respuestas evaluables.

    Es una opción exclusiva de la suite experimental; no modifica el adaptador
    ni la configuración productiva de Atlas.
    """

    @staticmethod
    def _payload(request, *, stream):
        payload = OllamaProvider._payload(request, stream=stream)
        payload["think"] = False
        return payload


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
