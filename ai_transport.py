"""Bounded, single-attempt Responses API transport; no application or user logging."""
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MAX_RESPONSE_BYTES = 256 * 1024
SOCKET_TIMEOUT_SECONDS = 60


class AnalysisFailure(ValueError):
    """A safe category, never a provider response body or exception message."""

    def __init__(self, category):
        self.category = category
        super().__init__(category)


def structured_response(payload, api_key, opener=urlopen):
    """Return parsed JSON and response ID. Socket timeout is not a total deadline.

    Do not automatically retry: a timeout may follow a billable completed request.
    The caller must still validate the application's schema and business rules.
    """
    request = Request(
        "https://api.openai.com/v1/responses", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    try:
        with opener(request, timeout=SOCKET_TIMEOUT_SECONDS) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise AnalysisFailure("response_too_large")
    except HTTPError as error:
        status = error.code
        error.close()
        category = ("rate_limited" if status == 429 else
                    "authentication" if status in (401, 403) else
                    "provider_unavailable" if status >= 500 else "provider_rejected")
        raise AnalysisFailure(category) from None
    except TimeoutError:
        raise AnalysisFailure("timeout") from None
    except URLError as error:
        category = "timeout" if isinstance(error.reason, TimeoutError) else "connection"
        raise AnalysisFailure(category) from None
    except OSError:
        raise AnalysisFailure("connection") from None
    try:
        envelope = json.loads(raw)
        if not isinstance(envelope, dict):
            raise AnalysisFailure("invalid_response")
        if envelope.get("status") != "completed":
            raise AnalysisFailure("incomplete")
        output = envelope.get("output")
        if not isinstance(output, list):
            raise AnalysisFailure("invalid_response")
        texts = []
        for item in output:
            if not isinstance(item, dict):
                raise AnalysisFailure("invalid_response")
            content = item.get("content", [])
            if not isinstance(content, list):
                raise AnalysisFailure("invalid_response")
            for part in content:
                if not isinstance(part, dict):
                    raise AnalysisFailure("invalid_response")
                if part.get("type") == "refusal":
                    raise AnalysisFailure("refused")
                if part.get("type") == "output_text":
                    if not isinstance(part.get("text"), str):
                        raise AnalysisFailure("invalid_response")
                    texts.append(part["text"])
        result = json.loads("".join(texts))
        if not isinstance(result, dict):
            raise AnalysisFailure("invalid_response")
        response_id = envelope.get("id")
        if response_id is not None and (not isinstance(response_id, str) or len(response_id) > 256):
            raise AnalysisFailure("invalid_response")
        return result, response_id
    except (TypeError, UnicodeError, json.JSONDecodeError):
        raise AnalysisFailure("invalid_response") from None
