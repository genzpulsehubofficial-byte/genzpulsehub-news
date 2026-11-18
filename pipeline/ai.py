"""Free AI fallback chain with automatic model discovery.

Each provider asks its own API which models exist right now and picks the best free one,
so retired model names never break the pipeline. Returns (text, provider) or raises AllFailed.
"""
import json
import os
import re
import time
import requests

T = 60
ERRORS = {}   # provider -> last error (keys stripped) for status.json
MODELS = {}   # provider -> model chosen this run
_fails = {}


class AllFailed(Exception):
    pass


def _redact(s):
    s = re.sub(r"([?&](key|token)=)[^&\s\"']+", r"\1***", str(s))
    for k in ("GEMINI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY", "CLOUDFLARE_API_TOKEN", "GITHUB_TOKEN"):
        v = os.environ.get(k)
        if v:
            s = s.replace(v, "***")
    return s


def _chat(url, key, model, prompt, extra=None):
    h = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    h.update(extra or {})
    r = requests.post(url, headers=h, timeout=T, json={
        "model": model, "temperature": 0.4, "messages": [{"role": "user", "content": prompt}]})
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _pick(names, prefer):
    names = sorted(set(names), reverse=True)
    for pat in prefer:
        for n in names:
            if re.search(pat, n):
                return n
    return names[0] if names else None


def _gemini_model(key):
    r = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                     params={"key": key, "pageSize": 200}, timeout=30)
    r.raise_for_status()
    ok = [m["name"].split("/", 1)[1] for m in r.json().get("models", [])
          if "generateContent" in m.get("supportedGenerationMethods", [])]
    ok = [n for n in ok if "flash" in n and not re.search(r"image|tts|audio|live|thinking|exp|preview|lite", n)]
    return _pick(ok, [r"^gemini-[\d.]+-flash$", r"flash-latest", r"flash"])


def _groq_model(key):
    r = requests.get("https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {key}"}, timeout=30)
    r.raise_for_status()
    ids = [m["id"] for m in r.json()["data"] if m.get("active", True)]
    ids = [i for i in ids if not re.search(r"whisper|guard|tts|orpheus|prompt|vision|compound", i)]
    return _pick(ids, [r"llama-?4.*maverick", r"llama.*70b", r"gpt-oss-120b", r"qwen", r"llama"])


def _openrouter_models():
    r = requests.get("https://openrouter.ai/api/v1/models", timeout=30)
    r.raise_for_status()
    free = [m["id"] for m in r.json()["data"]
            if m["id"].endswith(":free") and str(m.get("pricing", {}).get("prompt", "1")) in ("0", "0.0")]
    order = []
    for pat in [r"llama.*70b", r"deepseek", r"qwen", r"gemma", r"mistral", r"."]:
        order += [i for i in sorted(free, reverse=True) if re.search(pat, i) and i not in order]
    return order[:4]


def gemini(prompt):
    key = os.environ["GEMINI_API_KEY"]
    m = MODELS.get("gemini") or _gemini_model(key)
    MODELS["gemini"] = m
    r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent",
                      params={"key": key}, timeout=T,
                      json={"contents": [{"parts": [{"text": prompt}]}],
                            "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json"}})
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def groq(prompt):
    key = os.environ["GROQ_API_KEY"]
    m = MODELS.get("groq") or _groq_model(key)
    MODELS["groq"] = m
    return _chat("https://api.groq.com/openai/v1/chat/completions", key, m, prompt)


def openrouter(prompt):
    key = os.environ["OPENROUTER_API_KEY"]
    last = None
    for m in ([MODELS["openrouter"]] if MODELS.get("openrouter") else _openrouter_models()):
        try:
            out = _chat("https://openrouter.ai/api/v1/chat/completions", key, m, prompt,
                        {"HTTP-Referer": "https://genzpulsehub.dpdns.org", "X-Title": "GenZ Pulse Hub"})
            MODELS["openrouter"] = m
            return out
        except Exception as e:
            last = e
    raise last or RuntimeError("no free models")


def github_models(prompt):
    key = os.environ["GITHUB_TOKEN"]
    last = None
    for m in ("openai/gpt-4.1-mini", "openai/gpt-4o-mini", "meta/Llama-3.3-70B-Instruct"):
        try:
            out = _chat("https://models.github.ai/inference/chat/completions", key, m, prompt)
            MODELS["github_models"] = m
            return out
        except Exception as e:
            last = e
    raise last


def cloudflare(prompt):
    key, acct = os.environ["CLOUDFLARE_API_TOKEN"], os.environ["CLOUDFLARE_ACCOUNT_ID"]
    m = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
    r = requests.post(f"https://api.cloudflare.com/client/v4/accounts/{acct}/ai/run/{m}",
                      headers={"Authorization": f"Bearer {key}"}, timeout=T,
                      json={"messages": [{"role": "user", "content": prompt}], "max_tokens": 2048})
    r.raise_for_status()
    MODELS["cloudflare"] = m
    res = r.json()["result"]["response"]
    return res if isinstance(res, str) else json.dumps(res, ensure_ascii=False)


CHAIN = [("gemini", gemini), ("groq", groq), ("openrouter", openrouter),
         ("github_models", github_models), ("cloudflare", cloudflare)]


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
            if getattr(e, "response", None) is not None:
                msg += " | " + e.response.text[:200]
            msg = _redact(msg)
            ERRORS[name] = msg
            errors.append(f"{name}: {msg}")
            time.sleep(1)
    raise AllFailed(_redact("; ".join(errors)))
