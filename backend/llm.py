"""
FINN — Unified LLM Gateway (Gemini only)
==========================================
Routes tasks to the correct Gemini model based on task type:
  - "cheap"     -> GEMINI_CHEAP_MODEL   (bulk: classify, extract, chat)
  - "reasoning" -> GEMINI_MODEL         (Stage-2: synthesis, grounded bio)

On 429/quota: tries GEMINI_FALLBACK_MODELS in order.
Tracks daily request budgets per model (persisted to cache/_llm_budget.json).
All model names come from env vars; nothing is hardcoded here.

Failure kinds returned: model_not_found | auth | quota | timeout | other
"""

import json
import logging
import os
import re
import time
import threading
from datetime import date
from pathlib import Path
from typing import Literal, Optional, Union

logger = logging.getLogger(__name__)

# ── Types ─────────────────────────────────────────────────────────────────────

TaskType = Literal["cheap", "reasoning"]
FailureKind = Literal["model_not_found", "auth", "quota", "timeout", "other"]


class LLMError(Exception):
    """Typed LLM failure. kind ∈ {model_not_found, auth, quota, timeout, other}."""

    def __init__(self, kind: FailureKind, message: str, model: str = ""):
        self.kind = kind
        self.model = model
        super().__init__(message)


class BudgetExhausted(LLMError):
    def __init__(self, model: str):
        super().__init__("quota", f"Daily budget limit reached for {model}. Try again tomorrow.", model)


# ── Budget tracking (persisted per day) ───────────────────────────────────────
# NOTE: The local budget counter is a best-effort client-side heuristic to avoid
# burning quota when a daily ceiling is near. It is persisted to cache/_llm_budget.json
# but may reset upon container restarts/redeploys. Real 429 (RESOURCE_EXHAUSTED) responses
# from Google API are the single authoritative source of truth.

# Conservative daily-request estimates per model slug.
# User can override via env var GEMINI_DAILY_LIMIT_<SLUG_UPPER_WITH_UNDERSCORES>.
# e.g. GEMINI_DAILY_LIMIT_GEMINI_3_5_FLASH_LITE=500
_DEFAULT_DAILY_LIMITS: dict[str, int] = {
    "gemini-3.5-flash-lite": 500,
    "gemini-3.1-flash-lite": 500,
    "gemini-2.5-flash-lite": 20,
    "gemini-2.5-flash": 20,
    "gemini-3.6-flash": 20,
    "gemini-3.8-flash": 20,
    "gemini-2.0-flash": 1500,  # known free-tier limit
}
# Use 90% of limit to preserve headroom for retries
_BUDGET_MARGIN = 0.90
_budget_lock = threading.Lock()


def _budget_file() -> Path:
    p = Path(__file__).parent.parent / "cache" / "_llm_budget.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_budget() -> dict:
    """Load today's budget dict. Auto-resets when date rolls over."""
    today = date.today().isoformat()
    f = _budget_file()
    if f.exists():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if data.get("date") == today:
                return data
        except Exception:
            pass
    return {"date": today, "models": {}}


def _save_budget(data: dict) -> None:
    _budget_file().write_text(json.dumps(data, indent=2), encoding="utf-8")


def _slug(model: str) -> str:
    """Strip 'models/' prefix if present: 'models/gemini-2.5-flash' -> 'gemini-2.5-flash'."""
    return model.removeprefix("models/").strip()


def _daily_limit(slug: str) -> int:
    env_key = "GEMINI_DAILY_LIMIT_" + slug.upper().replace("-", "_")
    val = os.environ.get(env_key)
    if val:
        try:
            return int(val)
        except ValueError:
            pass
    return _DEFAULT_DAILY_LIMITS.get(slug, 20)


def increment_budget(model: str) -> int:
    """Increment request count for model today. Returns new count."""
    s = _slug(model)
    with _budget_lock:
        data = _load_budget()
        data["models"].setdefault(s, 0)
        data["models"][s] += 1
        _save_budget(data)
        return data["models"][s]


def _budget_ok(model: str) -> bool:
    s = _slug(model)
    with _budget_lock:
        data = _load_budget()
    used = data.get("models", {}).get(s, 0)
    limit = _daily_limit(s)
    return used < int(limit * _BUDGET_MARGIN)


def get_budget_status() -> dict:
    """Return {slug: {requests_today, estimated_daily_limit, headroom}} for tracked models."""
    with _budget_lock:
        data = _load_budget()
    result: dict = {}
    for s, used in data.get("models", {}).items():
        lim = _daily_limit(s)
        result[s] = {
            "requests_today": used,
            "estimated_daily_limit": lim,
            "headroom": max(0, int(lim * _BUDGET_MARGIN) - used),
        }
    return result


# ── Model availability cache ───────────────────────────────────────────────────

_avail_cache: dict[str, bool] = {}
_avail_lock = threading.Lock()


def _get_client():
    """Return an authenticated Gemini client. Raises LLMError('auth') if key missing."""
    try:
        from google import genai  # type: ignore
    except ImportError as e:
        raise LLMError("other", f"google-genai package not installed: {e}")
    key = (
        os.environ.get("GEMINI_API_KEY", "")
        or os.environ.get("GOOGLE_API_KEY", "")
        or os.environ.get("GOOGLE_GENAI_API_KEY", "")
    ).strip().strip('"').strip("'")
    if not key:
        raise LLMError("auth", "GEMINI_API_KEY is not set in environment variables")
    return genai.Client(api_key=key)


def list_available_text_models() -> list[str]:
    """
    Query the Gemini model listing endpoint and return slugs of models that
    support generateContent. Results are cached for the process lifetime.
    """
    with _avail_lock:
        if _avail_cache:
            return [s for s, ok in _avail_cache.items() if ok]

    try:
        client = _get_client()
        slugs: list[str] = []
        for m in client.models.list():
            name: str = getattr(m, "name", "") or ""
            s = _slug(name)
            # Check for content-generation capability
            methods = (
                getattr(m, "supported_generation_methods", None)
                or getattr(m, "supported_actions", None)
                or []
            )
            # In newer SDK versions, methods may be a list of strings or action objects
            method_strs = [
                (str(x.get("name", x)) if isinstance(x, dict) else str(x))
                for x in methods
            ]
            if any("generate" in x.lower() or "content" in x.lower() for x in method_strs):
                slugs.append(s)
            elif not methods:
                # SDK version that doesn't expose methods — include by name if it looks like a text model
                if "flash" in s or "pro" in s or "ultra" in s:
                    slugs.append(s)

        with _avail_lock:
            for s in slugs:
                _avail_cache[s] = True
        logger.info("[LLM] Available text models: %s", slugs)
        return slugs
    except LLMError:
        raise
    except Exception as e:
        logger.warning("[LLM] Could not list models: %s", e)
        return []


def validate_models() -> dict[str, str]:
    """
    Validate all configured models. Returns {slug: "ok"|"not_found"|"auth"|"unknown"}.
    Logs warnings for unavailable models and suggests alternatives.
    """
    from backend.config import GEMINI_MODEL, GEMINI_CHEAP_MODEL, GEMINI_FALLBACK_MODELS

    configured = list(dict.fromkeys(
        _slug(m) for m in [GEMINI_MODEL, GEMINI_CHEAP_MODEL] + GEMINI_FALLBACK_MODELS
    ))

    try:
        available = set(list_available_text_models())
    except LLMError as e:
        if e.kind == "auth":
            return {m: "auth" for m in configured}
        available = set()

    result: dict[str, str] = {}
    flash_available = sorted(s for s in available if "flash" in s.lower())

    for s in configured:
        if s in available:
            result[s] = "ok"
        elif not available:
            result[s] = "unknown"
        else:
            result[s] = "not_found"
            logger.warning(
                "[LLM] Model '%s' not available for this API key. "
                "Available Flash-class models: %s. "
                "Update GEMINI_MODEL / GEMINI_CHEAP_MODEL env vars.",
                s, flash_available,
            )
    return result


# ── Error classification ───────────────────────────────────────────────────────

def _classify_error(exc: Exception, model: str) -> LLMError:
    """Map any SDK/HTTP exception to a typed LLMError."""
    msg = str(exc).lower()

    # Try to extract numeric HTTP status
    code: Optional[int] = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if code is None:
        m = re.search(r"\b(4\d\d|5\d\d)\b", str(exc))
        if m:
            code = int(m.group(1))

    if code == 429 or any(k in msg for k in ("quota", "rate limit", "resource_exhausted", "resource exhausted")):
        return LLMError("quota", f"Rate limit / quota exceeded on {model}. Retrying with next model.", model)
    if code == 404 or any(k in msg for k in ("not found", "not_found", "is not supported")):
        return LLMError("model_not_found", f"Model '{model}' not found or retired.", model)
    if code in (401, 403) or any(k in msg for k in ("api_key", "permission", "unauthorized", "unauthenticated")):
        return LLMError("auth", "Authentication failed — check GEMINI_API_KEY.", model)
    if any(k in msg for k in ("timeout", "deadline", "timed out")):
        return LLMError("timeout", f"Request timed out on {model}.", model)
    return LLMError("other", str(exc)[:300], model)


# ── Core generation ────────────────────────────────────────────────────────────

def _do_generate(
    model: str,
    prompt: str,
    system: Optional[str],
    json_mode: bool,
    temperature: float,
    max_tokens: int,
    grounded: bool,
) -> str:
    """Single call attempt. Raises LLMError on any failure."""
    try:
        from google import genai  # type: ignore
        from google.genai import types as genai_types  # type: ignore
    except ImportError as e:
        raise LLMError("other", f"google-genai not installed: {e}")

    client = _get_client()
    s = _slug(model)

    cfg_kwargs: dict = {
        "temperature": temperature,
        "max_output_tokens": max_tokens,
    }
    if json_mode:
        cfg_kwargs["response_mime_type"] = "application/json"
    if system:
        cfg_kwargs["system_instruction"] = system
    if grounded:
        try:
            cfg_kwargs["tools"] = [genai_types.Tool(google_search=genai_types.GoogleSearch())]
        except Exception:
            # Grounding not available in this SDK version — fall back silently
            pass

    try:
        config = genai_types.GenerateContentConfig(**cfg_kwargs)
        response = client.models.generate_content(
            model=s,
            contents=prompt,
            config=config,
        )
        increment_budget(s)
        text = getattr(response, "text", None)
        if text is None:
            # Some SDK versions expose candidates
            try:
                text = response.candidates[0].content.parts[0].text
            except Exception:
                text = ""
        return text or ""
    except LLMError:
        raise
    except Exception as e:
        raise _classify_error(e, s) from e


# ── Public API ─────────────────────────────────────────────────────────────────

def gemini_generate(
    prompt: str,
    task: TaskType = "cheap",
    system: Optional[str] = None,
    json_mode: bool = False,
    temperature: float = 0.2,
    max_tokens: int = 2048,
    grounded: bool = False,
) -> str:
    """
    Generate text using the appropriate model for the task.

    task="cheap"     -> GEMINI_CHEAP_MODEL  (classification, extraction, chat)
    task="reasoning" -> GEMINI_MODEL        (synthesis, grounded bio)

    On 429 or model_not_found, automatically tries GEMINI_FALLBACK_MODELS.
    Raises LLMError when all models in the chain fail.
    """
    from backend.config import GEMINI_MODEL, GEMINI_CHEAP_MODEL, GEMINI_FALLBACK_MODELS

    primary = GEMINI_MODEL if task == "reasoning" else GEMINI_CHEAP_MODEL
    fallbacks = [f for f in GEMINI_FALLBACK_MODELS if _slug(f) != _slug(primary)]
    chain = [primary] + fallbacks

    last_error: Optional[LLMError] = None

    for model in chain:
        s = _slug(model)

        if not _budget_ok(s):
            logger.warning("[LLM] Daily budget exhausted for %s, trying next in chain", s)
            last_error = BudgetExhausted(s)
            continue

        # Retry loop for model s:
        # - model_not_found: skip immediately to next model in chain (no backoff)
        # - auth: stop immediately (fatal error)
        # - 429/quota/timeout/5xx: retry with capped exponential backoff up to 3x, then try next model
        for attempt in range(3):
            try:
                return _do_generate(
                    model=s,
                    prompt=prompt,
                    system=system,
                    json_mode=json_mode,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    grounded=grounded,
                )
            except Exception as raw_e:
                err = raw_e if isinstance(raw_e, LLMError) else _classify_error(raw_e, s)
                last_error = err

                # Rule 1: auth -> fatal, stop at once
                if err.kind == "auth":
                    logger.error("[LLM] Authentication failure on %s. Stopping immediately.", s)
                    raise err

                # Rule 2: model_not_found -> skip immediately to next model (NO backoff)
                if err.kind == "model_not_found":
                    with _avail_lock:
                        _avail_cache[s] = False
                    logger.warning("[LLM] Model '%s' not found. Skipping to fallback model immediately.", s)
                    break

                # Rule 3: quota (429) -> retry with backoff, then switch model
                if err.kind == "quota":
                    if attempt < 2:
                        wait = min(2 ** (attempt + 1), 8)
                        logger.warning("[LLM] Quota hit on %s (attempt %d/3). Backing off %ds...", s, attempt + 1, wait)
                        time.sleep(wait)
                        continue
                    else:
                        logger.warning("[LLM] Quota exhausted on %s after 3 attempts. Moving to next fallback model.", s)
                        with _budget_lock:
                            data = _load_budget()
                            data["models"][s] = _daily_limit(s) + 1
                            _save_budget(data)
                        break

                # Rule 4: timeout or transient server/network error -> retry with backoff
                if attempt < 2:
                    wait = min(2 ** (attempt + 1), 8)
                    logger.warning("[LLM] %s on %s (attempt %d/3). Retrying in %ds...", err.kind, s, attempt + 1, wait)
                    time.sleep(wait)
                else:
                    logger.warning("[LLM] %s failed on %s after 3 attempts. Moving to next fallback model.", err.kind, s)
                    break

    if last_error:
        raise last_error
    raise LLMError("other", "All models in the fallback chain failed.")


def gemini_generate_json(
    prompt: str,
    task: TaskType = "cheap",
    system: Optional[str] = None,
    temperature: float = 0.1,
    max_tokens: int = 4096,
) -> Union[dict, list]:
    """
    Generate and parse JSON. Strips markdown fences if the model wraps output.
    Raises LLMError or json.JSONDecodeError.
    """
    text = gemini_generate(
        prompt=prompt,
        task=task,
        system=system,
        json_mode=True,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    text = text.strip()
    # Strip ```json ... ``` or ``` ... ``` wrappers
    if text.startswith("```"):
        lines = text.splitlines()
        start = 1  # skip the opening fence line
        end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[start:end]).strip()
    return json.loads(text)


def health_check_llm() -> dict:
    """
    Make a minimal test call to each configured model.
    Returns {slug: "ok"|"model_not_found"|"auth"|"quota"|"timeout"|"other"}.
    Does NOT include API keys in the response.
    """
    from backend.config import GEMINI_MODEL, GEMINI_CHEAP_MODEL, GEMINI_FALLBACK_MODELS

    all_slugs = list(dict.fromkeys(
        _slug(m) for m in [GEMINI_MODEL, GEMINI_CHEAP_MODEL] + GEMINI_FALLBACK_MODELS
    ))
    statuses: dict[str, str] = {}

    for s in all_slugs:
        try:
            result = _do_generate(
                model=s,
                prompt="Reply with the single word: OK",
                system=None,
                json_mode=False,
                temperature=0.0,
                max_tokens=5,
                grounded=False,
            )
            statuses[s] = "ok" if result.strip() else "empty_response"
        except LLMError as e:
            statuses[s] = e.kind
        except Exception as e:
            statuses[s] = _classify_error(e, s).kind

    return statuses
