"""
Meta Tool - interfaccia web (Flask). Gira su Vercel o in locale.

Locale: doppio clic su "avvia.command" oppure  python3 app.py  -> http://127.0.0.1:5050
Vercel: variabili META_TOKEN, APP_PASSWORD, CRON_SECRET + integrazioni Upstash Redis e Blob.
"""
import hashlib
import hmac
import logging
import os
import re
import sys
import threading
import time
import traceback
import uuid
import warnings
import webbrowser
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

warnings.filterwarnings("ignore", module="urllib3")

from flask import (Flask, abort, flash, jsonify, redirect, render_template,  # noqa: E402
                   request, session, url_for)

import meta_ads  # noqa: E402,I100  (carica .env prima di store e blob)
import blob  # noqa: E402
import store  # noqa: E402
from meta_ads import MetaError  # noqa: E402

ON_VERCEL = bool(os.environ.get("VERCEL"))
TZ = ZoneInfo("Europe/Rome")
PORT = 5050

if ON_VERCEL:
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(levelname)s %(message)s")
else:
    logging.basicConfig(filename=os.path.join(meta_ads.HERE, "meta_tool.log"), level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("meta_tool")

APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or hashlib.sha256(
    f"meta-tool|{APP_PASSWORD}|{os.environ.get('META_TOKEN', '')}".encode()).hexdigest()
app.config.update(SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_HTTPONLY=True,
                  SESSION_COOKIE_SECURE=ON_VERCEL, PERMANENT_SESSION_LIFETIME=timedelta(days=30))

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
JOB_TTL = 3 * 86400


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
            "detail": f"{type(e).__name__}: {e}"}


@app.errorhandler(Exception)
def unexpected(e):
    if hasattr(e, "code") and hasattr(e, "get_response"):  # errori HTTP (404...)
        return e
    err = show_error(e)
    if request.path.endswith("/avanza") or request.is_json:
        return jsonify({"error": err}), 500
    return render_template("error.html", error=err), 500


@app.context_processor
def template_globals():
    return {"blob_enabled": blob.enabled(), "need_login": bool(APP_PASSWORD)}


# --- Accesso -----------------------------------------------------------------

@app.before_request
def require_login():
    if request.endpoint in ("login", "cron_tick", "static"):
        return None
    if not APP_PASSWORD:
        if ON_VERCEL:  # online senza password = chiunque col link userebbe il token
            return render_template("error.html", error={
                "message": "Accesso non configurato.",
                "detail": "Imposta la variabile APP_PASSWORD su Vercel e rifai il deploy."}), 503
        return None
    if not session.get("ok"):
        if request.method != "GET":
            abort(401)
        return redirect(url_for("login", next=request.full_path))
    return None


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if APP_PASSWORD and hmac.compare_digest(request.form.get("password", ""), APP_PASSWORD):
            session.permanent = True
            session["ok"] = True
            nxt = request.args.get("next", "")
            return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else url_for("home"))
        time.sleep(1)
        error = {"message": "Password errata.", "detail": ""}
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# --- Upload diretto su Vercel Blob -------------------------------------------

@app.route("/blob/token", methods=["POST"])
def blob_token():
    if not blob.enabled():
        return jsonify({"error": "Archivio file (Vercel Blob) non configurato."}), 400
    d = request.get_json(force=True)
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", d.get("filename", "file"))[-80:] or "file"
    types = ["image/jpeg", "image/png"] if d.get("kind") == "image" else ["video/mp4", "video/quicktime"]
    pathname = f"uploads/{datetime.now(TZ).strftime('%Y%m%d')}/{name}"
    return jsonify({"token": blob.client_token(pathname, types), "pathname": pathname,
                    "storeId": blob.store_id(), "apiVersion": blob.API_VERSION})


# --- Lavori a passaggi (campagna, post) -------------------------------------

def save_job(s):
    store.set(f"job:{s['id']}", s, expire_s=JOB_TTL)


def start_job(state):
    state["id"] = uuid.uuid4().hex[:12]
    save_job(state)
    return state["id"]


def public_job(s):
    return {k: s.get(k) for k in ("id", "kind", "log", "done", "error", "result", "cleaned")}


@app.route("/lavoro/<jid>")
def job_page(jid):
    s = store.get(f"job:{jid}") or abort(404)
    return render_template("job.html", job=public_job(s))


@app.route("/lavoro/<jid>/avanza", methods=["POST"])
def job_advance(jid):
    """Esegue passaggi per ~20 secondi o finche' serve aspettare Meta; il browser richiama."""
    if not store.lock(f"lock:job:{jid}", 90):
        s = store.get(f"job:{jid}") or abort(404)
        return jsonify(public_job(s))
    try:
        s = store.get(f"job:{jid}") or abort(404)
        t0 = time.time()
        while not s.get("done") and time.time() - t0 < 20:
            before = s["step"]
            meta_ads.advance(s)
            save_job(s)
            if s["step"] == before:  # in attesa di Meta
                break
        if (s.get("done") and s["kind"] == "post" and s.get("scheduled_ts")
                and s["result"].get("facebook_id") and not s.get("listed")):
            # i post Facebook programmati compaiono nella lista, per poterli annullare
            item = {"id": uuid.uuid4().hex[:10], "network": "facebook", "client": s["client"],
                    "client_name": s["c"]["name"], "caption": s["message"], "when": s["scheduled_ts"],
                    "status": "programmato", "fb_id": s["result"]["facebook_id"]}
            update_schedule(lambda items: items.append(item))
            s["listed"] = True
            save_job(s)
        if s.get("done") and s.get("ig_check_only") and not s.get("error") and not s.get("ig_listed"):
            # file verificato da Instagram: ora il post entra nella coda dello scheduler
            item = {"id": uuid.uuid4().hex[:10], "network": "instagram", "client": s["client"],
                    "client_name": s["c"]["name"], "caption": s["message"], "kind": s["media"],
                    "media_url": s["media_url"], "when": s["scheduled_ts"], "status": "in attesa"}
            update_schedule(lambda items: items.append(item))
            s["ig_listed"] = True
            save_job(s)
        return jsonify(public_job(s))
    finally:
        store.unlock(f"lock:job:{jid}")


@app.route("/lavoro/<jid>/elimina", methods=["POST"])
def job_cleanup(jid):
    """Elimina la campagna creata a meta' da un lavoro andato in errore."""
    if not store.lock(f"lock:job:{jid}", 90):
        return jsonify({"error": {"message": "Operazione gia' in corso, riprova tra poco.", "detail": ""}}), 409
    try:
        s = store.get(f"job:{jid}") or abort(404)
        if s["kind"] != "campagna" or not s.get("error"):
            abort(400)
        try:
            meta_ads.cleanup_campaign(s)
        except MetaError as e:
            save_job(s)
            return jsonify({"error": {"message": e.message, "detail": e.detail}}), 502
        save_job(s)
        return jsonify(public_job(s))
    finally:
        store.unlock(f"lock:job:{jid}")


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
    today = datetime.now(TZ).date()
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
        if form["video_url"]:
            overrides["video_url"] = form["video_url"]
        else:
            errors.append("Serve un video: carica un file oppure incolla un link.")
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
            jid = start_job(meta_ads.new_campaign(key, overrides))
            return redirect(url_for("job_page", jid=jid))
    return render_template("campaign.html", clients=all_clients, key=key, client=c, form=form, errors=errors)


# --- Pubblica post -----------------------------------------------------------

def load_schedule():
    return store.get("schedule", [])


def update_schedule(fn):
    """Modifica la lista dei post programmati sotto lock (fn riceve e modifica la lista)."""
    for _ in range(50):
        if store.lock("lock:schedule", 30):
            break
        time.sleep(0.2)
    else:
        raise RuntimeError("Archivio occupato, riprova tra qualche secondo.")
    try:
        items = load_schedule()
        fn(items)
        store.set("schedule", items)
    finally:
        store.unlock("lock:schedule")


def process_schedule(budget_s=240):
    """Pubblica su Instagram i post programmati arrivati all'ora (le API Instagram non
    supportano la programmazione). Chiamato dal cron o dal thread locale."""
    t0 = time.time()
    if not store.lock("lock:tick", budget_s + 30):
        return {"skipped": "tick gia' in corso"}
    processed = []
    try:
        for it in load_schedule():
            if it.get("network", "instagram") != "instagram" or it["status"] != "in attesa" \
                    or it["when"] > time.time():
                continue
            s = it.get("state") or meta_ads.new_post(it["client"], it["caption"], it["kind"],
                                                     it["media_url"], fb=False, ig=True)
            while not s.get("done") and time.time() - t0 < budget_s:
                before = s["step"]
                meta_ads.advance(s)
                if s["step"] == before and not s.get("done"):
                    time.sleep(8)

            def save(items, it=it, s=s):
                for x in items:
                    if x["id"] == it["id"] and x["status"] == "in attesa":
                        x["state"] = s
                        if s.get("error"):
                            x["status"] = "errore"
                            x["error"] = f"{s['error']['message']} {s['error']['detail']}"
                        elif s.get("done"):
                            x["status"] = "pubblicato"

            update_schedule(save)
            processed.append(it["id"])
            if time.time() - t0 >= budget_s:
                break
    finally:
        store.unlock("lock:tick")
    return {"processed": processed}


def cleanup_blobs(max_age_h=48):
    """Elimina i file caricati piu' vecchi di 48 ore, tranne quelli di post ancora in attesa."""
    if not blob.enabled():
        return 0
    keep = {it["media_url"] for it in load_schedule() if it["status"] == "in attesa"}
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_h)
    old = [b["url"] for b in blob.list_all()
           if b["url"] not in keep
           and datetime.fromisoformat(b["uploadedAt"].replace("Z", "+00:00")) < cutoff]
    blob.delete(old)
    return len(old)


@app.route("/cron/tick")
def cron_tick():
    secret = os.environ.get("CRON_SECRET", "")
    if not secret or not hmac.compare_digest(request.headers.get("Authorization", ""), f"Bearer {secret}"):
        abort(401)
    out = process_schedule()
    out["blob_cleaned"] = cleanup_blobs()
    return jsonify(out)


def parse_local_dt(value):
    """Il campo datetime-local e' in ora italiana, a prescindere dal fuso del server."""
    return datetime.fromisoformat(value).replace(tzinfo=TZ).timestamp()


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
        kind = form["kind"] if form["media_url"] else None
        if not (form["fb"] or form["ig"]):
            errors.append("Scegli almeno una destinazione: Facebook e/o Instagram.")
        if not form["message"] and not kind:
            errors.append("Scrivi un testo o allega un'immagine/video.")
        if form["ig"] and not kind:
            errors.append("Per Instagram serve un'immagine o un video.")
        ts = None
        if form["when"]:
            try:
                ts = parse_local_dt(form["when"])
            except ValueError:
                errors.append("Data/ora di programmazione non valida.")
            else:
                delta = ts - time.time()
                # la doc dice 30 giorni, ma per le foto Meta rifiuta gia' a 29 (verificato 10/2026)
                if form["fb"] and not (600 <= delta <= 28 * 86400):
                    errors.append("Facebook accetta programmazioni tra 10 minuti e 28 giorni da adesso.")
                elif delta < 60:
                    errors.append("L'orario di programmazione e' nel passato.")
        if not errors:
            s = meta_ads.new_post(key, form["message"], kind, form["media_url"] or None,
                                  fb=bool(form["fb"]), ig=bool(form["ig"]), scheduled_ts=ts,
                                  ig_check_only=bool(ts))
            return redirect(url_for("job_page", jid=start_job(s)))
    queue = sorted(load_schedule(), key=lambda x: x["when"], reverse=True)[:30]
    for q in queue:
        q["when_txt"] = datetime.fromtimestamp(q["when"], TZ).strftime("%d/%m/%Y %H:%M")
        q.setdefault("network", "instagram")
        if q["status"] == "programmato" and q["when"] < time.time():
            q["status"] = "pubblicato"
        q["can_cancel"] = q["status"] in ("in attesa", "programmato")
    min_when = (datetime.now(TZ) + timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M")
    return render_template("publish.html", clients=all_clients, key=key, form=form, errors=errors,
                           queue=queue, min_when=min_when, local=not ON_VERCEL)


@app.route("/pubblica/annulla/<sid>", methods=["POST"])
def publish_cancel(sid):
    item = next((x for x in load_schedule() if x["id"] == sid), None) or abort(404)
    if item.get("network") == "facebook":
        if item["status"] != "programmato" or item["when"] < time.time():
            abort(400)
        try:  # su Facebook il post programmato esiste gia': va eliminato da Meta
            c = meta_ads.load_client(item["client"])
            meta_ads.call("DELETE", item["fb_id"], token_=meta_ads.page_token(c["page_id"]))
        except MetaError as e:
            flash(f"Non sono riuscito ad annullare il post su Facebook: {e.message} {e.detail}")
            return redirect(url_for("publish"))

    def cancel(items):
        for it in items:
            if it["id"] == sid and it["status"] in ("in attesa", "programmato"):
                it["status"] = "annullato"
    update_schedule(cancel)
    flash("Post programmato annullato.")
    return redirect(url_for("publish"))


def local_scheduler():
    while True:
        try:
            process_schedule(budget_s=600)
        except Exception:  # noqa: BLE001
            log.error("Scheduler: %s", traceback.format_exc())
        time.sleep(30)


if __name__ == "__main__":
    threading.Thread(target=local_scheduler, daemon=True).start()
    if not os.environ.get("NO_BROWSER"):
        threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()
    print(f"Meta Tool attivo su http://127.0.0.1:{PORT}  (chiudi questa finestra per spegnerlo)")
    app.run(host="127.0.0.1", port=PORT, debug=False)
