"""
Video Studio: montaggi con Claude per ogni cliente (brand, regole, girato, chat, consegna).

Il montaggio lo fanno i Mac con il worker del repo video-editor (`npm run worker`): chiamano
/api/worker/* con il segreto WORKER_TOKEN. Qui ci sono solo dati e pagine.

Archivio (store): clients[<key>]["video"] = {brand, style_prompt}
  video:settings  {editor_prompt}
  video:projects  {pid: {id, client, title, status, created, updated, worker_id, session}}
  video:p:<pid>   {seq, msgs: [...], assets: [...], job: {...} | None}
  video:queue     [pid, ...] progetti con un lavoro in coda
  video:workers   {id: {id, name, last_seen, status}}
File su Vercel Blob sotto studio/ (la pulizia delle 48 ore tocca solo uploads/).
"""
import hmac
import json
import os
import re
import time
import uuid

from flask import (Blueprint, Response, abort, flash, jsonify, redirect, render_template, request,
                   url_for)

import blob
import meta_ads
import store

bp = Blueprint("video", __name__)
MAX_MSGS = 500
ONLINE_S = 90

DEFAULT_PROMPT = """Sei il video editor dello studio: monti Reels e TikTok verticali per i clienti dell'agenzia.
Lavori sul Mac con gli strumenti del progetto (CLAUDE.md): ffmpeg, Whisper in locale
(whisper-cli con ~/.cache/whisper/ggml-large-v3-turbo.bin, o npm run transcribe), Remotion,
script Swift/Python per grafiche e sottotitoli. Chi ti scrive è un video editor, non un programmatore.

COME RISPONDI
- In italiano, breve e concreto: cosa hai fatto, cosa hai controllato, cosa serve da lui.
- Niente codice né termini tecnici inutili. Non dire di aver fatto ciò che non hai fatto:
  se un passaggio richiede un accesso che non hai (Adobe Podcast, TikTok con login...), dillo
  e prepara le istruzioni precise.

MONTAGGIO
- Guarda e ascolta tutto il girato prima di montare (trascrizione + fotogrammi). Scegli come
  hook nei primi 1-3 s il passaggio più forte.
- Togli silenzi, esitazioni, false partenze, ripetizioni, indicazioni dell'operatore.
  Tieni le pause utili e una cadenza naturale. Se unire due frasi impasta le parole, metti
  ~0,15 s di silenzio preso dalla stessa ripresa.
- Non alterare il significato: per temi legali o tecnici conserva condizioni ed eccezioni.
- Durata indicativa 30-60 s se il contenuto lo permette; se è più corto dillo e spiega perché.
- Jump cut puliti e leggere variazioni d'inquadratura (punch-in 110-115%) ogni 3-5 s.
  Niente glitch, flash, swipe o transizioni vistose salvo richiesta.
- Copri con B-roll i punti in cui l'inquadratura è debole (sguardo in basso, telefono) o un
  taglio si vedrebbe. Se non c'è materiale, crea B-roll come grafiche animate pertinenti
  (mai dati personali, mai promesse di risultati). Materiale esterno solo con licenza adatta.
- iPhone HDR (HLG): converti in SDR con `avconvert -p PresetHighestQuality` prima di lavorare.

AUDIO
- Pulisci la voce (taglio bassi, riduzione rumore afftdn: arnndn con ffmpeg 9 dà errori,
  EQ leggera, de-esser, compressore). Master -14 LUFS, picco ≤ -1,5 dBFS, niente clipping.
- Musica solo con licenza (o sintetizzata), 20-25 dB sotto la voce, in ducking.
- Pochi effetti sonori leggeri.

SOTTOTITOLI E GRAFICHE
- Segui alla lettera il brand del cliente (colori, font, stile, maiuscolo, contorno, posizione).
- Sincronizzati parola per parola; gruppi che non si sovrappongono; testo corretto a mano
  (nomi, termini, punteggiatura). Posizione fissa, fuori dalle zone dei pulsanti social.

CONSEGNA (salva tutto nella cartella "consegna" del progetto, che ti viene indicata)
- <nome>_finale.mp4 (H.264, 1080x1920, fps del girato), <nome>_copertina.jpg (fotogramma reale
  + titolo 3-6 parole nel font/colore del brand), <nome>_frame-pulito.png, <nome>_sottotitoli.srt,
  <nome>_riepilogo.txt (tagli, B-roll, audio, risorse esterne). Il .drp di DaVinci solo se chiesto.
- Prima di consegnare riguarda l'export intero: tagli, sincronizzazione, audio, ortografia,
  leggibilità, copertina, fedeltà del messaggio. Scrivi in chat cosa hai verificato."""

DEFAULT_BRAND = {
    "handle": "", "settore": "",
    "colors": {"highlight": "#E9E6BA", "text": "#FFFFFF", "outline": "#000000", "box": "#0A0A0A"},
    "fonts": {"captions": "Montserrat ExtraBold", "titles": "Montserrat ExtraBold", "cta": "Montserrat ExtraBold"},
    "captions": {"style": "karaoke", "uppercase": True, "effect": "contorno", "words": "1-3", "position": "centro-basso"},
    "cta": "", "look": "", "logo": "", "notes": "",
}

# Stili già usati, da applicare con un clic a un cliente
PRESETS = {
    "avvocato": {
        "label": "Studio legale (stile Avvocato Ricci)",
        "brand": {
            "settore": "Studio legale",
            "colors": {"highlight": "#E9E6BA", "text": "#FFFFFF", "outline": "#000000", "box": "#0A0A0A"},
            "fonts": {"captions": "Montserrat ExtraBold", "titles": "Montserrat ExtraBold", "cta": "Baskerville Bold"},
            "captions": {"style": "karaoke", "uppercase": True, "effect": "contorno", "words": "1-3", "position": "centro-basso"},
            "cta": "Box nero con «INFO» (Baskerville bianco) che compare dalla mano quando dice «scrivi info» "
                   "e scorre in basso sotto i sottotitoli. Niente «Segui @…» a video.",
            "look": "LUT Avvocato_Pro.cube: contrasto e incarnato caldo, naturale",
        },
        "style": """Tono autorevole, chiaro, sobrio: costruire fiducia e generare contatti pertinenti.
- Formato tipico: domanda forte come hook (meglio se con un oggetto in mano), risposta breve,
  un esempio concreto, consiglio, CTA «scrivi INFO qua sotto».
- Sottotitoli karaoke: testo bianco MAIUSCOLO, il colore di evidenziazione riempie le lettere
  seguendo la voce, contorno nero, nessun box né ombra, nessun rimbalzo; 1-3 parole su una riga.
- Titolo d'apertura in box scuro in alto con la domanda (Montserrat, colore di evidenziazione).
- B-roll come grafiche animate sobrie (telefono, documenti anonimi, avvisi), mai risultati
  legali garantiti. Stamp tipo VERO/FALSO/VALIDO solo se servono.
- Musica discreta sintetizzata, pochi effetti (whoosh, pop, colpo sordo).""",
    },
    "tattoo": {
        "label": "Studio tatuaggi (stile White Garden)",
        "brand": {
            "settore": "Studio di tatuaggi",
            "colors": {"highlight": "#7FE0C0", "text": "#FFFFFF", "outline": "#000000", "box": "#111111"},
            "fonts": {"captions": "Avenir Next Heavy", "titles": "Avenir Next Heavy", "cta": "Avenir Next Heavy"},
            "captions": {"style": "parola-chiave", "uppercase": False, "effect": "contorno", "words": "2-4", "position": "centro-basso"},
            "notes": "Verde menta del logo da confermare con il cliente.",
        },
        "style": """Stile della prima prova (Vid 8), da confermare con il cliente.
- Jump cut senza pause, punch-in alternati, box titolo in alto.
- Sottotitoli bianchi con contorno nero, parole chiave nel colore del logo.
- B-roll dal materiale dello studio (tatuaggio in corso, reception con logo), whoosh sui cambi
  di sezione, musica bassa in ducking, voce a -14 LUFS.""",
    },
}

OUT_TYPES = ["video/*", "image/*", "audio/*", "text/*", "application/*"]
STATUSES = ["nuovo", "in lavorazione", "da rivedere", "consegnato"]
KINDS = {"input": "Girato", "music": "Musica", "broll": "B-roll", "output": "Consegna"}


# --- Archivio ----------------------------------------------------------------

def update(key, default, fn, wait_s=10):
    """Legge, modifica e salva una chiave sotto lock (fn modifica il valore e può restituire qualcosa)."""
    t0 = time.time()
    while not store.lock(f"lock:{key}", 30):
        if time.time() - t0 > wait_s:
            raise RuntimeError("Archivio occupato, riprova tra qualche secondo.")
        time.sleep(0.15)
    try:
        value = store.get(key, default)
        out = fn(value)
        store.set(key, value)
        return out
    finally:
        store.unlock(f"lock:{key}")


def settings():
    s = store.get("video:settings", {}) or {}
    s.setdefault("editor_prompt", DEFAULT_PROMPT)
    return s


def video_of(c):
    v = dict(c.get("video") or {})
    b = json.loads(json.dumps(DEFAULT_BRAND))
    for k, val in (v.get("brand") or {}).items():
        b[k] = {**b[k], **val} if isinstance(b.get(k), dict) and isinstance(val, dict) else val
    return {"brand": b, "style_prompt": v.get("style_prompt", ""), "configured": bool(v)}


def projects():
    return store.get("video:projects", {}) or {}


def project_doc(pid):
    return store.get(f"video:p:{pid}", None)


def workers_online():
    now = time.time()
    return [w for w in (store.get("video:workers", {}) or {}).values() if now - w.get("last_seen", 0) < ONLINE_S]


def add_msg(doc, role, text, author=""):
    doc["seq"] = doc.get("seq", 0) + 1
    doc["msgs"].append({"id": doc["seq"], "role": role, "text": text, "author": author, "ts": time.time()})
    doc["msgs"] = doc["msgs"][-MAX_MSGS:]


def touch_project(pid, **fields):
    def fn(ps):
        if pid in ps:
            ps[pid].update(fields, updated=time.time())
    update("video:projects", {}, fn)


def safe_name(name):
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name or "file").strip("-")
    return name[-90:] or "file"


def brand_text(name, b):
    lines = [f"# Cliente: {name}"]
    if b.get("settore"):
        lines.append(f"Settore: {b['settore']}")
    if b.get("handle"):
        lines.append(f"Profilo: {b['handle']}")
    lines.append("Colori: " + ", ".join(f"{k} {v}" for k, v in b["colors"].items() if v))
    lines.append("Font: " + ", ".join(f"{k} {v}" for k, v in b["fonts"].items() if v))
    c = b["captions"]
    lines.append(f"Sottotitoli: stile {c.get('style')}, {'MAIUSCOLO' if c.get('uppercase') else 'maiuscole normali'}, "
                 f"{c.get('effect')}, {c.get('words')} parole, posizione {c.get('position')}")
    for k, lab in (("cta", "CTA"), ("look", "Colore/look"), ("notes", "Note")):
        if b.get(k):
            lines.append(f"{lab}: {b[k]}")
    if b.get("logo"):
        lines.append("Logo: nella cartella logo/ del progetto")
    return "\n".join(lines)


# --- Pagine ------------------------------------------------------------------

@bp.route("/video")
def video_home():
    clients = meta_ads.load_clients()
    ps = sorted(projects().values(), key=lambda p: p.get("updated", 0), reverse=True)
    for p in ps:
        p["client_name"] = clients.get(p["client"], {}).get("name", p["client"])
    return render_template("video_home.html", clients=clients, projects=ps[:30], video_of=video_of,
                           workers=workers_online())


@bp.route("/video/cliente/nuovo", methods=["POST"])
def video_client_new():
    name = request.form.get("name", "").strip()
    if not name:
        abort(400)
    clients = meta_ads.load_clients()
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "cliente"
    key, n = base, 2
    while key in clients:
        key, n = f"{base}-{n}", n + 1
    clients[key] = {"name": name, "video": {"brand": {}, "style_prompt": ""}}
    meta_ads.save_clients(clients)
    flash(f"Cliente '{name}' creato: imposta brand e regole di montaggio.")
    return redirect(url_for("video.video_client", key=key))


@bp.route("/video/cliente/<key>", methods=["GET", "POST"])
def video_client(key):
    clients = meta_ads.load_clients()
    c = clients.get(key) or abort(404)
    if request.method == "POST":
        f = request.form
        if f.get("azione") == "preset" and f.get("preset") in PRESETS:
            pr = PRESETS[f["preset"]]
            cur = video_of(c)
            brand = cur["brand"]
            for k, v in pr["brand"].items():
                brand[k] = {**brand[k], **v} if isinstance(v, dict) else v
            c["video"] = {"brand": brand, "style_prompt": cur["style_prompt"] or pr["style"]}
            meta_ads.save_clients(clients)
            flash(f"Applicato lo stile «{pr['label']}»: controlla e salva le modifiche.")
            return redirect(url_for("video.video_client", key=key, tab="brand"))
        brand = {
            "handle": f.get("handle", "").strip(), "settore": f.get("settore", "").strip(),
            "colors": {k: f.get(f"color_{k}", "").strip() for k in ("highlight", "text", "outline", "box")},
            "fonts": {k: f.get(f"font_{k}", "").strip() for k in ("captions", "titles", "cta")},
            "captions": {"style": f.get("cap_style", "karaoke"), "uppercase": bool(f.get("cap_upper")),
                         "effect": f.get("cap_effect", "contorno"), "words": f.get("cap_words", "").strip(),
                         "position": f.get("cap_position", "centro-basso")},
            "cta": f.get("cta", "").strip(), "look": f.get("look", "").strip(),
            "logo": f.get("logo", "").strip(), "notes": f.get("notes", "").strip(),
        }
        c["video"] = {"brand": brand, "style_prompt": f.get("style_prompt", "").strip()}
        if f.get("name", "").strip():
            c["name"] = f["name"].strip()
        meta_ads.save_clients(clients)
        flash("Impostazioni video salvate: valgono dal prossimo messaggio all'editor.")
        return redirect(url_for("video.video_client", key=key, tab=f.get("tab", "brand")))
    ps = sorted((p for p in projects().values() if p["client"] == key), key=lambda p: p.get("updated", 0), reverse=True)
    return render_template("video_client.html", key=key, client=c, v=video_of(c), projects=ps, presets=PRESETS,
                           tab=request.args.get("tab", "video"), base_prompt=settings()["editor_prompt"])


@bp.route("/video/cliente/<key>/esporta")
def video_client_export(key):
    c = meta_ads.load_clients().get(key) or abort(404)
    data = {"name": c["name"], "key": key, "video": c.get("video", {}), "version": 1}
    return Response(json.dumps(data, ensure_ascii=False, indent=2), mimetype="application/json",
                    headers={"Content-Disposition": f'attachment; filename="cliente-video-{key}.json"'})


@bp.route("/video/cliente/importa", methods=["POST"])
def video_client_import():
    f = request.files.get("file")
    try:
        data = json.load(f)
        name, video = data["name"], data.get("video", {})
    except Exception:  # noqa: BLE001
        flash("File non valido: serve un .json esportato da «Esporta impostazioni».")
        return redirect(url_for("video.video_home"))
    clients = meta_ads.load_clients()
    key = data.get("key") or re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if key in clients:  # esiste già: aggiorno solo le impostazioni video
        clients[key]["video"] = video
    else:
        clients[key] = {"name": name, "video": video}
    meta_ads.save_clients(clients)
    flash(f"Impostazioni video di '{name}' importate.")
    return redirect(url_for("video.video_client", key=key, tab="brand"))


@bp.route("/video/progetto/nuovo", methods=["POST"])
def video_project_new():
    key = request.form.get("cliente", "")
    title = request.form.get("title", "").strip()
    if key not in meta_ads.load_clients() or not title:
        abort(400)
    pid = uuid.uuid4().hex[:10]
    now = time.time()

    def fn(ps):
        ps[pid] = {"id": pid, "client": key, "title": title, "status": "nuovo", "created": now, "updated": now,
                   "worker_id": None, "session": None}
    update("video:projects", {}, fn)
    store.set(f"video:p:{pid}", {"seq": 0, "msgs": [], "assets": [], "job": None})
    return redirect(url_for("video.video_project", pid=pid))


@bp.route("/video/progetto/<pid>")
def video_project(pid):
    p = projects().get(pid) or abort(404)
    c = meta_ads.load_clients().get(p["client"], {"name": p["client"]})
    return render_template("video_project.html", prj=p, client=c, statuses=STATUSES, kinds=KINDS)


@bp.route("/video/progetto/<pid>/stato")
def video_project_state(pid):
    doc = project_doc(pid) or abort(404)
    after = int(request.args.get("dopo", 0) or 0)
    p = projects().get(pid, {})
    return jsonify({"msgs": [m for m in doc["msgs"] if m["id"] > after], "assets": doc["assets"], "job": doc.get("job"),
                    "status": p.get("status"), "workers": [w["name"] for w in workers_online()]})


@bp.route("/video/progetto/<pid>/messaggio", methods=["POST"])
def video_project_message(pid):
    text = (request.get_json(force=True).get("text") or "").strip()
    if not text or pid not in projects():
        abort(400)

    def fn(doc):
        job = doc.get("job")
        if job and job["status"] in ("queued", "running"):
            return False
        add_msg(doc, "user", text)
        doc["job"] = {"id": uuid.uuid4().hex[:10], "prompt": text, "status": "queued", "created": time.time(),
                      "worker_id": None, "worker_name": None, "error": None}
        return True
    if not update(f"video:p:{pid}", None, fn):
        return jsonify({"error": "L'editor sta già lavorando: aspetta o premi Ferma."}), 409
    update("video:queue", [], lambda q: q.append(pid) if pid not in q else None)
    touch_project(pid)
    return jsonify({"ok": True})


@bp.route("/video/progetto/<pid>/ferma", methods=["POST"])
def video_project_stop(pid):
    def fn(doc):
        job = doc.get("job")
        if job and job["status"] in ("queued", "running"):
            job["status"] = "cancelled" if job["status"] == "queued" else "stopping"
    update(f"video:p:{pid}", None, fn)
    update("video:queue", [], lambda q: q.remove(pid) if pid in q else None)
    return jsonify({"ok": True})


@bp.route("/video/progetto/<pid>/file", methods=["POST"])
def video_project_asset(pid):
    """Registra un file appena caricato su Blob dal browser."""
    d = request.get_json(force=True)
    if pid not in projects() or d.get("kind") not in KINDS or not str(d.get("url", "")).startswith("https://"):
        abort(400)
    item = {"name": safe_name(d.get("name")), "kind": d["kind"], "url": d["url"], "size": d.get("size"),
            "mime": d.get("mime", ""), "ts": time.time()}

    def fn(doc):
        doc["assets"] = [a for a in doc["assets"] if not (a["kind"] == item["kind"] and a["name"] == item["name"])]
        doc["assets"].append(item)
    update(f"video:p:{pid}", None, fn)
    return jsonify({"ok": True})


@bp.route("/video/progetto/<pid>/file/elimina", methods=["POST"])
def video_project_asset_delete(pid):
    url = request.get_json(force=True).get("url", "")

    def fn(doc):
        doc["assets"] = [a for a in doc["assets"] if a["url"] != url]
    update(f"video:p:{pid}", None, fn)
    blob.delete([url])
    return jsonify({"ok": True})


@bp.route("/video/progetto/<pid>/aggiorna", methods=["POST"])
def video_project_update(pid):
    d = request.form
    if d.get("status") in STATUSES:
        touch_project(pid, status=d["status"])
    return redirect(url_for("video.video_project", pid=pid))


@bp.route("/video/progetto/<pid>/elimina", methods=["POST"])
def video_project_delete(pid):
    p = projects().get(pid) or abort(404)
    doc = project_doc(pid) or {"assets": []}
    blob.delete([a["url"] for a in doc["assets"]])
    update("video:projects", {}, lambda ps: ps.pop(pid, None))
    update("video:queue", [], lambda q: q.remove(pid) if pid in q else None)
    store.set(f"video:p:{pid}", None, expire_s=60)
    flash(f"Video «{p['title']}» eliminato.")
    return redirect(url_for("video.video_client", key=p["client"]))


@bp.route("/video/blob-token", methods=["POST"])
def video_blob_token():
    """Token per caricare un file del progetto direttamente su Blob (fino a 4 GB)."""
    if not blob.enabled():
        return jsonify({"error": "Archivio file (Vercel Blob) non configurato."}), 400
    d = request.get_json(force=True)
    pid, kind = d.get("pid", ""), d.get("kind", "input")
    if kind == "logo":
        if d.get("cliente") not in meta_ads.load_clients():
            abort(400)
        pathname = f"studio/clienti/{d['cliente']}/{safe_name(d.get('filename'))}"
    else:
        if pid not in projects() or kind not in KINDS:
            abort(400)
        pathname = f"studio/{pid}/{kind}/{safe_name(d.get('filename'))}"
    types = ["video/*", "audio/*", "image/*", "application/octet-stream", "text/plain", "application/x-subrip"]
    return jsonify({"token": blob.client_token(pathname, types, max_bytes=4 * 1024 ** 3), "pathname": pathname,
                    "storeId": blob.store_id(), "apiVersion": blob.API_VERSION})


@bp.route("/video/impostazioni", methods=["GET", "POST"])
def video_settings():
    if request.method == "POST":
        def fn(s):
            s["editor_prompt"] = request.form.get("editor_prompt", "").strip() or DEFAULT_PROMPT
        update("video:settings", {}, fn)
        flash("Prompt base dell'editor salvato.")
        return redirect(url_for("video.video_settings"))
    allw = sorted((store.get("video:workers", {}) or {}).values(), key=lambda w: -w.get("last_seen", 0))
    return render_template("video_settings.html", s=settings(), workers=allw, now=time.time(), online_s=ONLINE_S,
                           has_token=bool(os.environ.get("WORKER_TOKEN")), app_url=request.host_url.rstrip("/"))


# --- API per i Mac (worker) --------------------------------------------------

def worker_auth():
    token = os.environ.get("WORKER_TOKEN", "")
    if not token:
        abort(Response("WORKER_TOKEN non impostato su Vercel", 503))
    if not hmac.compare_digest(request.headers.get("Authorization", ""), f"Bearer {token}"):
        abort(401)


@bp.route("/api/worker/presenza", methods=["POST"])
def api_presence():
    worker_auth()
    d = request.get_json(force=True)

    def fn(ws):
        ws[d["id"]] = {"id": d["id"], "name": d.get("name", "Mac"), "status": d.get("status", "libero"),
                       "last_seen": time.time(), "version": d.get("version", "")}
        for k in [k for k, w in ws.items() if time.time() - w["last_seen"] > 30 * 86400]:
            ws.pop(k)
    update("video:workers", {}, fn)
    return jsonify({"ok": True})


@bp.route("/api/worker/prendi", methods=["POST"])
def api_claim():
    """Il Mac prende il lavoro più vecchio in coda. Precedenza al Mac che ha già la sessione Claude."""
    worker_auth()
    d = request.get_json(force=True)
    wid, wname = d["id"], d.get("name", "Mac")
    if not store.get("video:queue", []):
        return jsonify({"job": None})
    ps = projects()

    def take(queue):
        for pid in list(queue):
            p = ps.get(pid)
            if not p:
                queue.remove(pid)
                continue

            def claim(doc, p=p):
                job = (doc or {}).get("job")
                if not job or job["status"] != "queued":
                    return "drop"
                if p.get("worker_id") not in (None, wid) and time.time() - job["created"] < 60:
                    return None
                job.update(status="running", worker_id=wid, worker_name=wname, started=time.time())
                return job
            res = update(f"video:p:{pid}", None, claim)
            if res == "drop":
                queue.remove(pid)
            elif res:
                queue.remove(pid)
                return pid, res
        return None
    got = update("video:queue", [], take)
    if not got:
        return jsonify({"job": None})
    pid, job = got
    p = ps[pid]
    clients = meta_ads.load_clients()
    c = clients.get(p["client"], {"name": p["client"]})
    v = video_of(c)
    doc = project_doc(pid)
    touch_project(pid, status="in lavorazione")
    return jsonify({
        "job": job, "project": p, "client": {"key": p["client"], "name": c["name"]},
        "system": "\n\n".join(x for x in (
            settings()["editor_prompt"], brand_text(c["name"], v["brand"]),
            f"# Come montare per {c['name']}\n{v['style_prompt']}" if v["style_prompt"] else "") if x),
        "logo": v["brand"].get("logo") or None,
        "assets": [a for a in doc["assets"] if a["kind"] != "output"],
        "history": [{"role": m["role"], "text": m["text"]} for m in doc["msgs"] if m["role"] in ("user", "assistant")][-21:-1],
    })


@bp.route("/api/worker/progetto/<pid>/messaggi", methods=["POST"])
def api_messages(pid):
    worker_auth()
    items = request.get_json(force=True).get("messages", [])

    def fn(doc):
        if not doc:
            return "cancelled"
        for m in items:
            add_msg(doc, m.get("role", "assistant"), str(m.get("text", ""))[:8000], m.get("author", ""))
        job = doc.get("job") or {}
        return job.get("status")
    status = update(f"video:p:{pid}", None, fn)
    return jsonify({"job_status": status})


@bp.route("/api/worker/progetto/<pid>/blob-token", methods=["POST"])
def api_blob_token(pid):
    worker_auth()
    if not blob.enabled():
        return jsonify({"error": "Archivio file (Vercel Blob) non configurato."}), 400
    d = request.get_json(force=True)
    pathname = f"studio/{pid}/output/{safe_name(d.get('filename'))}"
    return jsonify({"token": blob.client_token(pathname, OUT_TYPES, max_bytes=4 * 1024 ** 3), "pathname": pathname,
                    "storeId": blob.store_id(), "apiVersion": blob.API_VERSION})


@bp.route("/api/worker/progetto/<pid>/file", methods=["POST"])
def api_asset(pid):
    worker_auth()
    d = request.get_json(force=True)
    item = {"name": safe_name(d.get("name")), "kind": "output", "url": d["url"], "size": d.get("size"),
            "mime": d.get("mime", ""), "ts": time.time()}
    old = []

    def fn(doc):
        if not doc:
            return
        old.extend(a["url"] for a in doc["assets"] if a["kind"] == "output" and a["name"] == item["name"])
        doc["assets"] = [a for a in doc["assets"] if not (a["kind"] == "output" and a["name"] == item["name"])]
        doc["assets"].append(item)
    update(f"video:p:{pid}", None, fn)
    blob.delete(old)
    return jsonify({"ok": True})


@bp.route("/api/worker/progetto/<pid>/fine", methods=["POST"])
def api_finish(pid):
    worker_auth()
    d = request.get_json(force=True)

    def fn(doc):
        job = (doc or {}).get("job")
        if job and job["id"] == d.get("job_id"):
            job.update(status=d.get("status", "done"), error=d.get("error"), finished=time.time())
    update(f"video:p:{pid}", None, fn)
    fields = {"worker_id": d.get("worker_id")}
    if d.get("session"):
        fields["session"] = d["session"]
    if d.get("uploaded"):
        fields["status"] = "da rivedere"
    touch_project(pid, **fields)
    return jsonify({"ok": True})
