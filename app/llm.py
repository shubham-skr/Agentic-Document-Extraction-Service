"""Bounded OpenRouter client and tolerant JSON decoding for model responses."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any

try:
    from openai import AsyncOpenAI
except ImportError:  # deterministic spreadsheet parsing can run without the LLM client
    AsyncOpenAI = None

from .config import settings

log = logging.getLogger(__name__)
_ALLOWED = {
    'google/gemini-3.8-flash', 'google/gemini-3.1-pro-preview',
    'anthropic/claude-haiku-5.5', 'anthropic/claude-sonnet-5.5',
    'openai/gpt-6-luna', 'openai/gpt-6.1-sol', 'z-ai/glm-5.3-flash',
    'qwen/qwen3-vl-235b-a22b-instruct', 'deepseek/deepseek-v3.2',
}
_sem = asyncio.Semaphore(max(1, settings.max_llm_concurrency))


class LLM:
    def __init__(self):
        if settings.llm_api_key and not settings.llm_base_url and AsyncOpenAI:
            raise RuntimeError('LLM_BASE_URL must be set in the environment; no provider endpoint is hardcoded')
        self.client = (
            AsyncOpenAI(
                base_url=settings.llm_base_url,
                api_key=settings.llm_api_key,
                timeout=settings.llm_timeout_seconds,
                max_retries=0,
            )
            if settings.llm_api_key and settings.llm_base_url and AsyncOpenAI else None
        )
        self.calls = 0
        self.failed_calls = 0
        self.parse_failures = 0
        self.tokens_in = 0
        self.tokens_out = 0
        self.cost_usd = 0.0
        self.by_model: dict[str, dict[str, Any]] = {}

    async def complete(self, messages, model=None, temperature=0, max_tokens=4000, retries=1,
                       json_mode=True):
        if not self.client:
            raise RuntimeError('LLM_API_KEY is not configured')
        model = model or settings.fast_model
        if model not in _ALLOWED:
            raise ValueError(f'Model not allowed by assignment: {model}')

        async with _sem:
            for attempt in range(max(0, retries) + 1):
                try:
                    m = self.by_model.setdefault(model, {
                        'calls': 0, 'tokens_in': 0, 'tokens_out': 0, 'cost_usd': 0.0,
                    })
                    self.calls += 1
                    m['calls'] += 1
                    kwargs = {
                        'model': model,
                        'messages': messages,
                        'temperature': temperature,
                        'max_tokens': max_tokens,
                        'extra_body': {'usage': {'include': True}},
                    }
                    if json_mode:
                        kwargs['response_format'] = {'type': 'json_object'}
                    try:
                        response = await self.client.chat.completions.create(**kwargs)
                    except Exception as exc:
                        # A few OpenRouter model/provider combinations do not implement
                        # JSON mode. Fall back once, but only for an explicit 400 response.
                        status = getattr(exc, 'status_code', None)
                        if not json_mode or status != 400:
                            raise
                        log.warning('Provider rejected JSON mode for %s; retrying without it', model)
                        kwargs.pop('response_format', None)
                        self.calls += 1
                        m['calls'] += 1
                        response = await self.client.chat.completions.create(**kwargs)

                    usage = response.usage
                    ti = getattr(usage, 'prompt_tokens', 0) or 0
                    to = getattr(usage, 'completion_tokens', 0) or 0
                    self.tokens_in += ti
                    self.tokens_out += to
                    cost = float(getattr(usage, 'cost', 0) or 0)
                    self.cost_usd += cost
                    m['tokens_in'] += ti
                    m['tokens_out'] += to
                    m['cost_usd'] += cost
                    choices = getattr(response, 'choices', None) or []
                    if not choices:
                        raise RuntimeError('LLM provider returned no choices')
                    content = choices[0].message.content
                    if isinstance(content, list):
                        content = ''.join(x.get('text', '') for x in content if isinstance(x, dict))
                    return content or ''
                except Exception as exc:
                    status = getattr(exc, 'status_code', None)
                    retryable = status in (408, 429, 500, 502, 503, 504) or status is None
                    if attempt >= max(0, retries) or not retryable:
                        self.failed_calls += 1
                        raise
                    await asyncio.sleep(min(4.0, 0.5 * (2 ** attempt)))
        raise RuntimeError('LLM retries exhausted')


def _remove_fence(text: str) -> str:
    s = (text or '').strip().lstrip('\ufeff')
    s = re.sub(r'^```(?:json)?\s*', '', s, flags=re.I)
    s = re.sub(r'\s*```\s*$', '', s)
    # Remove prose before the first JSON container, which some providers still emit.
    starts = [i for i in (s.find('{'), s.find('[')) if i >= 0]
    if starts:
        s = s[min(starts):]
    return s.strip()


def _close_json_prefix(s: str) -> Any | None:
    """Recover complete leading object members when a model truncates its final value."""
    # Record commas outside strings. A prefix ending at one of these boundaries can
    # usually be closed without inventing any value; the unfinished member is dropped.
    commas: list[int] = []
    stack: list[str] = []
    in_string = False
    escaped = False
    for i, ch in enumerate(s):
        if in_string:
            if escaped:
                escaped = False
            elif ch == '\\':
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in '{[':
            stack.append('}' if ch == '{' else ']')
        elif ch in '}]':
            if stack and stack[-1] == ch:
                stack.pop()
        elif ch == ',' and stack:
            commas.append(i)

    for cut in reversed(commas):
        prefix = s[:cut].rstrip()
        # Recompute the closing delimiters for the candidate prefix.
        closes: list[str] = []
        quoted = False
        esc = False
        for ch in prefix:
            if quoted:
                if esc: esc = False
                elif ch == '\\': esc = True
                elif ch == '"': quoted = False
            elif ch == '"': quoted = True
            elif ch == '{': closes.append('}')
            elif ch == '[': closes.append(']')
            elif ch in '}]' and closes and closes[-1] == ch: closes.pop()
        if quoted:
            continue
        candidate = prefix + ''.join(reversed(closes))
        try:
            return json.loads(candidate)
        except Exception:
            continue
    return None


def parse_json(text: str):
    """Parse strict JSON; recover harmless formatting/truncation without guessing values."""
    s = _remove_fence(text)
    if not s:
        raise ValueError('LLM returned an empty response')
    try:
        return json.loads(s)
    except json.JSONDecodeError as original:
        # Normalize common JSON-like output errors (bare keys, Python literals,
        # trailing commas). This operates only on a model response, never source text.
        cleaned = re.sub(r'([{,]\s*)([A-Za-z_][A-Za-z0-9_-]*)(\s*:)', r'\1"\2"\3', s)
        cleaned = re.sub(r',\s*([}\]])', r'\1', cleaned)
        cleaned = re.sub(r'\bNone\b', 'null', cleaned)
        cleaned = re.sub(r'\bTrue\b', 'true', cleaned)
        cleaned = re.sub(r'\bFalse\b', 'false', cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            recovered = _close_json_prefix(cleaned)
            if recovered is not None:
                return recovered
            raise original
