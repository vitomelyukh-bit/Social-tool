"""
Archivio dati: Upstash Redis su Vercel, file JSON in locale.

Chiavi usate: "clients", "schedule", "job:<id>".
Redis si attiva se ci sono KV_REST_API_URL/KV_REST_API_TOKEN (integrazione Upstash
del Marketplace Vercel) oppure UPSTASH_REDIS_REST_URL/UPSTASH_REDIS_REST_TOKEN.
"""
import json
import os
import threading
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
# In locale "clients" resta su clients.json, come prima
LOCAL_FILES = {"clients": os.path.join(HERE, "clients.json")}

_URL = os.environ.get("KV_REST_API_URL") or os.environ.get("UPSTASH_REDIS_REST_URL")
_TOKEN = os.environ.get("KV_REST_API_TOKEN") or os.environ.get("UPSTASH_REDIS_REST_TOKEN")
_lock = threading.Lock()


def using_redis():
    return bool(_URL and _TOKEN)


def _redis(*cmd):
    r = requests.post(_URL, headers={"Authorization": f"Bearer {_TOKEN}"}, json=list(cmd), timeout=15)
    body = r.json()
    if "error" in body:
        raise RuntimeError(f"Errore archivio dati: {body['error']}")
    return body.get("result")


def _path(key):
    if key in LOCAL_FILES:
        return LOCAL_FILES[key]
    os.makedirs(DATA_DIR, exist_ok=True)
    return os.path.join(DATA_DIR, key.replace(":", "_") + ".json")


def get(key, default=None):
    if using_redis():
        raw = _redis("GET", key)
        return json.loads(raw) if raw is not None else default
    p = _path(key)
    if not os.path.exists(p):
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def set(key, value, expire_s=None):  # noqa: A001 - stessa semantica di Redis
    if using_redis():
        cmd = ["SET", key, json.dumps(value, ensure_ascii=False)]
        if expire_s:
            cmd += ["EX", int(expire_s)]
        _redis(*cmd)
        return
    p = _path(key)
    with _lock:
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, p)


_local_locks = {}


def lock(key, ttl_s):
    """Lock non bloccante con scadenza: True se acquisito."""
    if using_redis():
        return _redis("SET", key, "1", "NX", "EX", int(ttl_s)) == "OK"
    with _lock:
        if _local_locks.get(key, 0) > time.time():
            return False
        _local_locks[key] = time.time() + ttl_s
        return True


def unlock(key):
    if using_redis():
        _redis("DEL", key)
    else:
        _local_locks.pop(key, None)
