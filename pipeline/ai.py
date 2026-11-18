"""Free AI fallback chain. Returns (text, provider) or raises AllFailed."""
import os
import time
import requests

T = 60


class AllFailed(Exception):
    pass


def _openai_style(url, key, model, prompt, extra_headers=None):
    h = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    h.update(extra_headers or {})
    r = requests.post(url, headers=h, timeout=T, json={
        "model": model, "temperature": 0.4,
        "messages": [{"role": "user", "content": prompt}],
    })
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def gemini(prompt):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("no key")
    last = None
    for model in ("gemini-2.5-flash", "gemini-flash-latest", "gemini-2.0-flash"):
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                params={"key": key}, timeout=T,
                json={"contents": [{"parts": [{"text": prompt}]}],
                      "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json"}})
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:  # try next model name
            last = e
    raise last


def groq(prompt):
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("no key")
    return _openai_style("https://api.groq.com/openai/v1/chat/completions", key,
                         "llama-3.3-70b-versatile", prompt)


def openrouter(prompt):
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("no key")
    last = None
    for model in ("meta-llama/llama-3.3-70b-instruct:free", "deepseek/deepseek-chat-v3-0324:free",
                  "google/gemma-3-27b-it:free"):
        try:
            return _openai_style("https://openrouter.ai/api/v1/chat/completions", key, model, prompt,
                                 {"HTTP-Referer": "https://genzpulsehub.dpdns.org", "X-Title": "GenZ Pulse Hub"})
        except Exception as e:
            last = e
    raise last


def github_models(prompt):
    key = os.environ.get("GITHUB_TOKEN")
    if not key:
        raise RuntimeError("no key")
    return _openai_style("https://models.github.ai/inference/chat/completions", key,
                         "openai/gpt-4o-mini", prompt)


def cloudflare(prompt):
    key, acct = os.environ.get("CLOUDFLARE_API_TOKEN"), os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    if not key or not acct:
        raise RuntimeError("no key")
    r = requests.post(
        f"https://api.cloudflare.com/client/v4/accounts/{acct}/ai/run/@cf/meta/llama-3.3-70b-instruct-fp8-fast",
        headers={"Authorization": f"Bearer {key}"}, timeout=T,
        json={"messages": [{"role": "user", "content": prompt}], "max_tokens": 2048})
    r.raise_for_status()
    res = r.json()["result"]["response"]
    return res if isinstance(res, str) else __import__("json").dumps(res)


CHAIN = [("gemini", gemini), ("groq", groq), ("openrouter", openrouter),
         ("github_models", github_models), ("cloudflare", cloudflare)]

_fails = {}
ERRORS = {}  # provider -> last error (for status.json)


def ask(prompt):
    errors = []
    for name, fn in CHAIN:
        if _fails.get(name, 0) >= 2:
            continue
        try:
            out = fn(prompt)
            if out and out.strip():
                return out, name
        except Exception as e:
            _fails[name] = _fails.get(name, 0) + 1
            msg = str(e)[:200]
            if hasattr(e, 'response') and e.response is not None:
                msg += ' | ' + e.response.text[:200]
            ERRORS[name] = msg
            errors.append(f"{name}: {msg}")
            time.sleep(1)
    raise AllFailed("; ".join(errors))
