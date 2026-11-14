"""Adaptador local para la API de chat de Ollama."""

import ipaddress
import json
import math
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener

from atlas.core.errors import ContractError
from atlas.ports.llm import LLMRequest, LLMResponse


class OllamaError(Exception):
    """Error base del adaptador Ollama."""


class OllamaUnavailableError(OllamaError):
    """Ollama no está disponible en el endpoint local configurado."""


class OllamaResponseError(OllamaError):
    """Ollama devolvió un error o una respuesta incompatible."""


class JsonHttpTransport(Protocol):
    """Transporte mínimo inyectable para solicitudes JSON POST."""

    def post_json(
        self,
        url: str,
        payload: dict[str, object],
        timeout: float,
    ) -> dict[str, object]:
        """Envía JSON y devuelve un objeto JSON."""


class UrllibJsonTransport:
    """Transporte HTTP sin dependencias externas y sin proxies del entorno."""

    def __init__(self) -> None:
        self._opener = build_opener(ProxyHandler({}))

    def post_json(
        self,
        url: str,
        payload: dict[str, object],
        timeout: float,
    ) -> dict[str, object]:
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with self._opener.open(request, timeout=timeout) as response:
                raw_body = response.read()
        except HTTPError as exc:
            detail = exc.read(1024).decode("utf-8", errors="replace").strip()
            message = f"Ollama devolvió HTTP {exc.code}"
            if detail:
                message = f"{message}: {detail}"
            raise OllamaResponseError(message) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise OllamaUnavailableError(
                "No se pudo conectar con el servicio Ollama local"
            ) from exc

        try:
            decoded = json.loads(raw_body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OllamaResponseError(
                "Ollama devolvió una respuesta JSON inválida"
            ) from exc

        if not isinstance(decoded, dict):
            raise OllamaResponseError(
                "La respuesta JSON de Ollama debe ser un objeto"
            )
        return decoded


class OllamaProvider:
    """Implementa LLMProvider usando exclusivamente un endpoint loopback."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        timeout: float = 30.0,
        transport: JsonHttpTransport | None = None,
    ) -> None:
        self._base_url = self._validate_base_url(base_url)
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise ContractError("timeout debe ser un número finito positivo")
        if transport is not None and not callable(
            getattr(transport, "post_json", None)
        ):
            raise ContractError("transport debe implementar post_json()")

        self._timeout = float(timeout)
        self._transport = transport or UrllibJsonTransport()

    @staticmethod
    def _validate_base_url(base_url: str) -> str:
        if not isinstance(base_url, str) or not base_url.strip():
            raise ContractError("base_url debe ser una URL local no vacía")

        try:
            parsed = urlsplit(base_url.strip())
            hostname = parsed.hostname
            port = parsed.port
        except ValueError as exc:
            raise ContractError("base_url no es una URL válida") from exc

        if (
            parsed.scheme != "http"
            or hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise ContractError(
                "base_url debe ser un origen HTTP local sin credenciales ni ruta"
            )

        is_loopback = hostname.lower() == "localhost"
        if not is_loopback:
            try:
                is_loopback = ipaddress.ip_address(hostname).is_loopback
            except ValueError:
                is_loopback = False

        if not is_loopback:
            raise ContractError(
                "Ollama solo puede configurarse en localhost o una IP loopback"
            )
        if port is not None and not 1 <= port <= 65535:
            raise ContractError("El puerto de base_url está fuera de rango")

        return f"http://{parsed.netloc}"

    def generate(self, request: LLMRequest) -> LLMResponse:
        """Envía mensajes al endpoint local /api/chat y devuelve texto."""
        if not isinstance(request, LLMRequest):
            raise ContractError("request debe ser LLMRequest")

        payload: dict[str, object] = {
            "model": request.model,
            "messages": [
                {"role": message.role.value, "content": message.content}
                for message in request.messages
            ],
            "stream": False,
        }
        options: dict[str, object] = {}
        if request.temperature is not None:
            options["temperature"] = request.temperature
        if request.max_tokens is not None:
            options["num_predict"] = request.max_tokens
        if options:
            payload["options"] = options

        try:
            result = self._transport.post_json(
                f"{self._base_url}/api/chat",
                payload,
                self._timeout,
            )
        except OllamaError:
            raise
        except (TimeoutError, OSError) as exc:
            raise OllamaUnavailableError(
                "No se pudo completar la solicitud al Ollama local"
            ) from exc

        if not isinstance(result, dict):
            raise OllamaResponseError(
                "El transporte debe devolver un objeto JSON"
            )

        provider_error = result.get("error")
        if isinstance(provider_error, str) and provider_error.strip():
            raise OllamaResponseError(
                f"Ollama informó un error: {provider_error.strip()}"
            )

        message = result.get("message")
        if not isinstance(message, dict):
            raise OllamaResponseError(
                "La respuesta de Ollama no contiene un mensaje válido"
            )
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise OllamaResponseError(
                "Ollama no devolvió contenido de texto"
            )

        returned_model = result.get("model")
        model = (
            returned_model
            if isinstance(returned_model, str) and returned_model.strip()
            else request.model
        )
        finish_reason = result.get("done_reason")
        if not isinstance(finish_reason, str) or not finish_reason.strip():
            finish_reason = None

        return LLMResponse(
            provider="ollama",
            model=model,
            content=content,
            finish_reason=finish_reason,
        )
