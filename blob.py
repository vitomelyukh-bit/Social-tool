"""
Vercel Blob: il browser carica i file direttamente su Blob (niente limite di 4,5 MB
delle funzioni) con un token temporaneo firmato qui, come fa @vercel/blob
(generateClientTokenFromReadWriteToken). Meta poi scarica il file dal suo URL pubblico.
"""
import base64
import hashlib
import hmac
import json
import os
import time

import requests

API = "https://vercel.com/api/blob"
API_VERSION = "12"
MAX_BYTES = 1024 * 1024 * 1024  # 1 GB


def rw_token():
    return os.environ.get("BLOB_READ_WRITE_TOKEN", "").strip()


def enabled():
    return bool(rw_token())


def store_id():
    # formato: vercel_blob_rw_<storeId>_<segreto>
    return rw_token().split("_")[3]


def client_token(pathname, content_types, max_bytes=MAX_BYTES, valid_s=3600):
    payload = base64.b64encode(json.dumps({
        "pathname": pathname,
        "allowedContentTypes": content_types,
        "maximumSizeInBytes": max_bytes,
        "addRandomSuffix": True,
        "validUntil": int((time.time() + valid_s) * 1000),
    }, separators=(",", ":")).encode()).decode()
    sig = hmac.new(rw_token().encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"vercel_blob_client_{store_id()}_" + base64.b64encode(f"{sig}.{payload}".encode()).decode()


def _headers():
    return {"authorization": f"Bearer {rw_token()}", "x-api-version": API_VERSION,
            "x-vercel-blob-store-id": store_id()}


def delete(urls):
    urls = [u for u in urls if u and ".blob.vercel-storage.com" in u]
    if urls and enabled():
        requests.post(f"{API}/delete", headers={**_headers(), "content-type": "application/json"},
                      json={"urls": urls}, timeout=30)


def list_all(prefix="uploads/"):
    out, cursor = [], None
    while True:
        params = {"prefix": prefix, "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        body = requests.get(f"{API}/", headers=_headers(), params=params, timeout=30).json()
        out += body.get("blobs", [])
        cursor = body.get("cursor")
        if not body.get("hasMore"):
            return out
