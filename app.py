"""
Meta Tool - interfaccia web locale.

Avvio: doppio clic su "avvia.command" oppure  python3 app.py
Poi apri http://127.0.0.1:5050
"""
import json
import logging
import os
import re
import threading
import time
import traceback
import uuid
import warnings
import webbrowser
from datetime import date, datetime, timedelta

warnings.filterwarnings("ignore", module="urllib3")

from flask import Flask, abort, flash, redirect, render_template, request, url_for  # noqa: E402
from werkzeug.utils import secure_filename  # noqa: E402

import meta_ads  # noqa: E402
from meta_ads import MetaError  # noqa: E402

HERE = meta_ads.HERE
UPLOADS = os.path.join(HERE, "uploads")
SCHEDULE_FILE = os.path.join(HERE, "scheduled_posts.json")
PORT = 5050
os.makedirs(UPLOADS, exist_ok=True)

logging.basicConfig(filename=os.path.join(HERE, "meta_tool.log"), level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("meta_tool")

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "meta-tool-locale")
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024  # 1 GB

CLIENT_FIELDS = [
    # (chiave, etichetta, tipo, obbligatorio, aiuto)
    ("name", "Nome cliente", "text", True, ""),
    ("ad_account_id", "ID account pubblicitario", "text", True, "Solo numeri, senza 'act_'"),
    ("page_id", "ID pagina Facebook", "text", True, ""),
    ("website", "Sito web", "url", True, "Dove va l'utente dopo aver inviato il modulo"),
    ("privacy_url", "Link privacy policy", "url", True, "Obbligatorio per i moduli lead"),
    ("lat", "Latitudine centro zona", "number", True, "Es. 41.9028 (da Google Maps: tasto destro sul punto)"),
    ("lng", "Longitudine centro zona", "number", True, "Es. 12.4964"),
    ("radius_km", "Raggio (km)", "number", True, "Da 1 a 80"),
    ("age_min", "Eta' minima", "number", False, "Predefinita 25"),
    ("daily_budget_eur", "Budget giornaliero (EUR)", "number", True, ""),
    ("dsa_beneficiary", "Beneficiario inserzioni (DSA)", "text", False,
     "Chi trae vantaggio dalle inserzioni, es. ragione sociale del cliente. Obbligatorio in UE."),
    ("dsa_payor", "Chi paga le inserzioni (DSA)", "text", False, "Se vuoto = beneficiario"),
    ("video_url", "Video predefinito (URL)", "url", False, "Link diretto al file .mp4"),
    ("primary_text", "Testo principale predefinito", "textarea", False, ""),
    ("headline", "Titolo predefinito", "text", False, ""),
]
NUMERIC = {"lat": float, "lng": float, "radius_km": float, "age_min": int, "daily_budget_eur": float}

PERIODS = [
    ("today", "Oggi"), ("yesterday", "Ieri"), ("last_7d", "Ultimi 7 giorni"),
    ("last_14d", "Ultimi 14 giorni"), ("last_30d", "Ultimi 30 giorni"),
    ("this_month", "Questo mese"), ("last_month", "Mese scorso"), ("custom", "Date personalizzate"),
]


@app.template_filter("eur")
def fmt_money(v):
    if v is None:
        return "n/d"
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def show_error(e):
    if isinstance(e, MetaError):
        log.warning("MetaError: %s | %s", e.message, e.detail)
        return {"message": e.message, "detail": e.detail}
    log.error("Errore imprevisto: %s", traceback.format_exc())
    return {"message": "Si e' verificato un errore imprevisto.",
            "detail": f"{type(e).__name__}: {e} (dettagli nel file meta_tool.log)"}


@app.errorhandler(Exception)
def unexpected(e):
    if hasattr(e, "code") and hasattr(e, "get_response"):  # errori HTTP (404, 413...)
        if e.code == 413:
            return render_template("error.html", error={
                "message": "Il file e' troppo grande (massimo 1 GB).", "detail": ""}), 413
        return e
    return render_template("error.html", error=show_error(e)), 500


def save_upload(field):
    f = request.files.get(field)
    if not f or not f.filename:
        return None
    name = f"{uuid.uuid4().hex[:8]}_{secure_filename(f.filename) or 'file'}"
    path = os.path.join(UPLOADS, name)
    f.save(path)
    return path


# --- Lavori in background (creazione campagna, pubblicazione) ---------------

JOBS = {}


def start_job(kind, fn):
    jid = uuid.uuid4().hex[:10]
    job = {"id": jid, "kind": kind, "log": [], "done": False, "error": None, "result": None,
           "started": datetime.now().strftime("%H:%M:%S")}
    JOBS[jid] = job

    def run():
        try:
            job["result"] = fn(lambda m: job["log"].append(m))
        except Exception as e:  # noqa: BLE001 - mostriamo tutto in chiaro
            job["error"] = show_error(e)
            job["result"] = getattr(e, "partial", None)
        finally:
            job["done"] = True

    threading.Thread(target=run, daemon=True).start()
    return jid


@app.route("/lavoro/<jid>")
def job_page(jid):
    job = JOBS.get(jid) or abort(404)
    return render_template("job.html", job=job)


# --- Home / Clienti ----------------------------------------------------------

@app.route("/")
def home():
    return redirect(url_for("clients"))


@app.route("/clienti")
def clients():
    return render_template("clients.html", clients=meta_ads.load_clients(),
                           has_token=bool(os.environ.get("META_TOKEN")))


def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "cliente"


@app.route("/clienti/nuovo", methods=["GET", "POST"])
@app.route("/clienti/<key>", methods=["GET", "POST"])
def client_edit(key=None):
    all_clients = meta_ads.load_clients()
    if key and key not in all_clients:
        abort(404)
    current = dict(all_clients.get(key, {}))
    errors = []
    if request.method == "POST":
        data = {}
        for fkey, label, _t, required, _h in CLIENT_FIELDS:
            v = request.form.get(fkey, "").strip()
            if not v:
                if required:
                    errors.append(f"'{label}' e' obbligatorio.")
                continue
            if fkey in NUMERIC:
                try:
                    v = NUMERIC[fkey](v.replace(",", "."))
                except ValueError:
                    errors.append(f"'{label}' deve essere un numero.")
                    continue
            data[fkey] = v
        if "ad_account_id" in data:
            data["ad_account_id"] = data["ad_account_id"].replace("act_", "").strip()
        if not errors:
            new_key = key or slugify(data["name"])
            base, n = new_key, 2
            while not key and new_key in all_clients:
                new_key, n = f"{base}-{n}", n + 1
            known = {f[0] for f in CLIENT_FIELDS}
            extra = {k: v for k, v in all_clients.get(key, {}).items() if k not in known}
            all_clients[new_key] = {**data, **extra}
            meta_ads.save_clients(all_clients)
            flash(f"Cliente '{data['name']}' salvato.")
            return redirect(url_for("clients"))
        current = {**current, **request.form.to_dict()}
    return render_template("client_form.html", key=key, client=current, fields=CLIENT_FIELDS, errors=errors)


@app.route("/clienti/<key>/elimina", methods=["POST"])
def client_delete(key):
    all_clients = meta_ads.load_clients()
    removed = all_clients.pop(key, None)
    meta_ads.save_clients(all_clients)
    if removed:
        flash(f"Cliente '{removed['name']}' eliminato.")
    return redirect(url_for("clients"))


# --- Report ------------------------------------------------------------------

@app.route("/report")
def report():
    all_clients = meta_ads.load_clients()
    period = request.args.get("periodo", "last_30d")
    since = request.args.get("dal", "")
    until = request.args.get("al", "")
    selected = request.args.getlist("cliente") or list(all_clients)
    rows, error = [], None
    run = "vai" in request.args
    if run:
        if period == "custom" and not (since and until):
            error = {"message": "Per le date personalizzate indica sia 'dal' che 'al'.", "detail": ""}
        elif period == "custom" and since > until:
            error = {"message": "La data 'dal' e' successiva alla data 'al'.", "detail": ""}
        else:
            for k in selected:
                if k not in all_clients:
                    continue
                try:
                    rows.append(meta_ads.report_row(
                        all_clients[k], date_preset=period,
                        since=since if period == "custom" else None,
                        until=until if period == "custom" else None))
                except Exception as e:  # noqa: BLE001
                    rows.append({"name": all_clients[k]["name"], "error": show_error(e)})
    ok = [r for r in rows if "error" not in r]
    totals = None
    if len(ok) > 1:
        spend = sum(r["spend"] for r in ok)
        leads = sum(r["leads"] for r in ok)
        currencies = {r["currency"] for r in ok if r["currency"]}
        totals = {"spend": spend, "leads": leads, "cpl": spend / leads if leads else None,
                  "currency": currencies.pop() if len(currencies) == 1 else ""}
    today = date.today()
    return render_template("report.html", clients=all_clients, periods=PERIODS, period=period,
                           since=since or (today - timedelta(days=30)).isoformat(),
                           until=until or today.isoformat(), selected=selected,
                           rows=rows, totals=totals, error=error, run=run)


# --- Nuova campagna ----------------------------------------------------------

@app.route("/campagna", methods=["GET", "POST"])
def campaign():
    all_clients = meta_ads.load_clients()
    key = request.values.get("cliente") or next(iter(all_clients), None)
    c = all_clients.get(key, {})
    form = {
        "video_url": c.get("video_url", ""), "primary_text": c.get("primary_text", ""),
        "headline": c.get("headline", ""), "lat": c.get("lat", ""), "lng": c.get("lng", ""),
        "radius_km": c.get("radius_km", ""), "daily_budget_eur": c.get("daily_budget_eur", ""),
    }
    errors = []
    if request.method == "POST" and request.form.get("azione") == "crea":
        form.update({k: request.form.get(k, "").strip() for k in form})
        overrides = {}
        video_path = save_upload("video_file")
        if video_path:
            overrides["video_path"] = video_path
            overrides["video_url"] = None
        elif form["video_url"]:
            overrides["video_url"] = form["video_url"]
        else:
            errors.append("Serve un video: incolla un link oppure carica un file.")
        for k, label in [("primary_text", "Testo"), ("headline", "Titolo")]:
            if not form[k]:
                errors.append(f"'{label}' e' obbligatorio.")
            overrides[k] = form[k]
        for k, label in [("lat", "Latitudine"), ("lng", "Longitudine"), ("radius_km", "Raggio"),
                         ("daily_budget_eur", "Budget giornaliero")]:
            try:
                overrides[k] = float(str(form[k]).replace(",", "."))
            except ValueError:
                errors.append(f"'{label}' deve essere un numero.")
        if not errors:
            if not 1 <= overrides["radius_km"] <= 80:
                errors.append("Il raggio deve essere tra 1 e 80 km.")
            if overrides["daily_budget_eur"] < 1:
                errors.append("Il budget giornaliero e' troppo basso.")
        if not errors:
            jid = start_job("campagna", lambda lg: meta_ads.launch(key, overrides, log=lg))
            return redirect(url_for("job_page", jid=jid))
    return render_template("campaign.html", clients=all_clients, key=key, client=c, form=form, errors=errors)


# --- Pubblica post -----------------------------------------------------------

def load_schedule():
    if not os.path.exists(SCHEDULE_FILE):
        return []
    with open(SCHEDULE_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_schedule(items):
    tmp = SCHEDULE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SCHEDULE_FILE)


SCHEDULE_LOCK = threading.Lock()


def scheduler_loop():
    """Pubblica su Instagram i post programmati (le API Instagram non hanno la programmazione)."""
    while True:
        try:
            with SCHEDULE_LOCK:
                items = load_schedule()
            for it in items:
                if it["status"] != "in attesa" or it["when"] > time.time():
                    continue
                try:
                    c = meta_ads.load_client(it["client"])
                    it["result_id"] = meta_ads.publish_instagram(
                        c, it["caption"], it["kind"], it.get("media_url"), it.get("media_path"),
                        log=lambda m: None)
                    it["status"] = "pubblicato"
                except Exception as e:  # noqa: BLE001
                    err = show_error(e)
                    it["status"] = "errore"
                    it["error"] = f"{err['message']} {err['detail']}"
                with SCHEDULE_LOCK:
                    current = load_schedule()
                    for x in current:
                        if x["id"] == it["id"]:
                            x.update(it)
                    save_schedule(current)
        except Exception:  # noqa: BLE001
            log.error("Scheduler: %s", traceback.format_exc())
        time.sleep(30)


@app.route("/pubblica", methods=["GET", "POST"])
def publish():
    all_clients = meta_ads.load_clients()
    key = request.values.get("cliente") or next(iter(all_clients), None)
    form = {"message": "", "media_url": "", "kind": "image", "when": "", "fb": "1", "ig": "1"}
    errors = []
    if request.method == "POST" and request.form.get("azione") == "pubblica":
        form = {k: request.form.get(k, "").strip() for k in ("message", "media_url", "kind", "when")}
        form["fb"] = request.form.get("fb", "")
        form["ig"] = request.form.get("ig", "")
        media_path = save_upload("media_file")
        kind = form["kind"] if (media_path or form["media_url"]) else None
        if not (form["fb"] or form["ig"]):
            errors.append("Scegli almeno una destinazione: Facebook e/o Instagram.")
        if not form["message"] and not kind:
            errors.append("Scrivi un testo o allega un'immagine/video.")
        if form["ig"] and not kind:
            errors.append("Per Instagram serve un'immagine o un video.")
        if kind == "image" and form["ig"] and form["media_url"] and not media_path \
                and not re.search(r"\.jpe?g($|\?)", form["media_url"], re.I):
            errors.append("Per Instagram l'immagine da link deve essere un JPG: in alternativa caricala dal computer.")
        ts = None
        if form["when"]:
            try:
                ts = datetime.fromisoformat(form["when"]).timestamp()
            except ValueError:
                errors.append("Data/ora di programmazione non valida.")
            else:
                delta = ts - time.time()
                if form["fb"] and not (600 <= delta <= 30 * 86400):
                    errors.append("Facebook accetta programmazioni tra 10 minuti e 30 giorni da adesso.")
                elif delta < 60:
                    errors.append("L'orario di programmazione e' nel passato.")
        if not errors:
            c = all_clients[key]
            media_url = None if media_path else (form["media_url"] or None)

            def run(lg):
                out = {}
                if form["fb"]:
                    lg("Pubblico su Facebook..." if not ts else "Programmo su Facebook...")
                    out["facebook_id"] = meta_ads.publish_facebook(c, form["message"], kind, media_url, media_path, ts)
                    lg(f"Facebook OK ({out['facebook_id']})" + (" - programmato" if ts else ""))
                if form["ig"]:
                    if ts:
                        with SCHEDULE_LOCK:
                            items = load_schedule()
                            items.append({"id": uuid.uuid4().hex[:10], "client": key, "client_name": c["name"],
                                          "caption": form["message"], "kind": kind, "media_url": media_url,
                                          "media_path": media_path, "when": ts, "status": "in attesa"})
                            save_schedule(items)
                        lg("Instagram programmato: verra' pubblicato all'ora indicata "
                           "(il programma deve essere acceso in quel momento).")
                        out["instagram_scheduled"] = True
                    else:
                        lg("Pubblico su Instagram...")
                        out["instagram_id"] = meta_ads.publish_instagram(c, form["message"], kind, media_url,
                                                                         media_path, log=lg)
                        lg(f"Instagram OK ({out['instagram_id']})")
                return out

            jid = start_job("post", run)
            return redirect(url_for("job_page", jid=jid))
    with SCHEDULE_LOCK:
        queue = sorted(load_schedule(), key=lambda x: x["when"], reverse=True)
    for q in queue:
        q["when_txt"] = datetime.fromtimestamp(q["when"]).strftime("%d/%m/%Y %H:%M")
    min_when = (datetime.now() + timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M")
    return render_template("publish.html", clients=all_clients, key=key, form=form, errors=errors,
                           queue=queue, min_when=min_when)


@app.route("/pubblica/annulla/<sid>", methods=["POST"])
def publish_cancel(sid):
    with SCHEDULE_LOCK:
        items = load_schedule()
        for it in items:
            if it["id"] == sid and it["status"] == "in attesa":
                it["status"] = "annullato"
        save_schedule(items)
    flash("Post Instagram programmato annullato.")
    return redirect(url_for("publish"))


if __name__ == "__main__":
    threading.Thread(target=scheduler_loop, daemon=True).start()
    if not os.environ.get("NO_BROWSER"):
        threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()
    print(f"Meta Tool attivo su http://127.0.0.1:{PORT}  (chiudi questa finestra per spegnerlo)")
    app.run(host="127.0.0.1", port=PORT, debug=False)
