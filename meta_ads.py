"""
Tool interno Meta Ads (modello agenzia, token System User).

Usato dalla web app (app.py) e ancora utilizzabile da riga di comando:
  python3 meta_ads.py launch test     # crea campagna completa in PAUSA
  python3 meta_ads.py report test     # spesa, lead e CPL ultimi 30 giorni
  python3 meta_ads.py report all

Il token si legge da .env / .env.local (META_TOKEN=...) o dalle variabili di Vercel.

Le operazioni lunghe (campagna, post) sono divise in passaggi brevi: ogni chiamata
ad `advance()` esegue un passaggio e aggiorna lo stato, cosi' su Vercel nessuna
richiesta supera il limite di durata delle funzioni.
"""
import json
import os
import sys
import time

import requests
from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, ".env.local"))
load_dotenv(os.path.join(HERE, ".env"))

import store  # noqa: E402  (dopo load_dotenv: legge le variabili all'import)

# v24.0 della Marketing API scade il 6/10/2026; v26.0 e' la corrente (29/07/2026).
# Changelog: https://developers.facebook.com/docs/graph-api/changelog
API_VERSION = "v26.0"
BASE = f"https://graph.facebook.com/{API_VERSION}"


class MetaError(Exception):
    """Errore da mostrare all'utente: `message` in italiano, `detail` e' il testo originale di Meta."""

    def __init__(self, message, detail=""):
        super().__init__(message)
        self.message = message
        self.detail = detail


def token():
    t = os.environ.get("META_TOKEN", "").strip()
    if not t:
        raise MetaError(
            "Manca il token di Meta.",
            "Va impostata la variabile META_TOKEN (su Vercel: Settings > Environment Variables; "
            "in locale: file .env). Poi riavvia o rifai il deploy.",
        )
    return t


# --- Errori Meta in italiano -------------------------------------------------

_ERROR_CODES = {
    1: "Errore temporaneo di Meta. Riprova tra qualche minuto.",
    2: "Servizio Meta momentaneamente non disponibile. Riprova tra qualche minuto.",
    4: "Troppe richieste in poco tempo. Aspetta qualche minuto e riprova.",
    10: "Il token non ha il permesso per questa operazione.",
    17: "Troppe richieste per questo account. Aspetta qualche minuto e riprova.",
    32: "Troppe richieste per questa pagina. Aspetta qualche minuto e riprova.",
    80004: "Troppe richieste all'account pubblicitario. Aspetta qualche minuto e riprova.",
    190: "Il token di Meta non e' valido o e' scaduto. Va rigenerato in Business Manager (Utenti di sistema).",
    200: "Il token non ha i permessi necessari su questa risorsa (account pubblicitario, pagina o Instagram).",
    368: "Meta ha bloccato temporaneamente l'operazione per motivi di policy.",
    613: "Troppe richieste in poco tempo. Aspetta qualche minuto e riprova.",
    2635: "La versione dell'API Meta usata non e' piu' supportata.",
    9004: "Meta non riesce a scaricare il file dall'URL indicato: controlla che sia un link diretto e pubblico.",
    9007: "Il contenuto Instagram non e' ancora pronto per la pubblicazione. Riprova tra poco.",
    36003: "Il formato o le proporzioni del file non sono accettati da Instagram.",
}

_SUBCODES = {
    463: "Il token di Meta e' scaduto. Va rigenerato in Business Manager.",
    467: "Il token di Meta non e' piu' valido. Va rigenerato in Business Manager.",
    1487390: "Lo stesso nome e' gia' in uso: cambia il nome e riprova.",
    2207026: "Formato video non supportato da Instagram (serve MP4/MOV, H.264, max 15 minuti).",
    2207052: "Instagram non riesce a scaricare il file: serve un link diretto e pubblico.",
    2207004: "L'immagine e' troppo grande per Instagram (max 8 MB).",
    2207009: "Le proporzioni dell'immagine non sono accettate da Instagram (tra 4:5 e 1.91:1).",
    2207042: "Hai raggiunto il limite di pubblicazioni Instagram via API nelle ultime 24 ore.",
}


def translate_error(err, path=""):
    code = err.get("code")
    sub = err.get("error_subcode")
    user_title = err.get("error_user_title") or ""
    user_msg = err.get("error_user_msg") or ""
    raw = err.get("message", "")

    msg = _SUBCODES.get(sub) or _ERROR_CODES.get(code)
    if "dsa" in (raw + user_msg).lower() or "beneficiar" in (raw + user_msg).lower():
        msg = "Mancano beneficiario/pagante (obbligo DSA per le inserzioni in UE): compilali nella scheda cliente."
    if not msg:
        msg = "Meta ha rifiutato uno dei dati inviati." if code == 100 else "Meta ha restituito un errore."
    # error_user_msg e' gia' pensato per l'utente finale (in italiano grazie a locale=it_IT)
    detail_parts = [p for p in (user_title, user_msg) if p]
    detail = " - ".join(detail_parts) if detail_parts else raw
    if detail_parts and raw and raw not in detail:
        detail += f" (Meta: {raw})"
    where = f" [operazione: {path}]" if path else ""
    return MetaError(msg, detail + where)


# --- Chiamate API ------------------------------------------------------------

def call(method, path, token_=None, **params):
    data = {k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in params.items()}
    data["access_token"] = token_ or token()
    data.setdefault("locale", "it_IT")  # error_user_msg in italiano quando disponibile
    kwargs = {"params": data} if method == "GET" else {"data": data}
    try:
        r = requests.request(method, f"{BASE}/{path}", timeout=60, **kwargs)
    except requests.RequestException as e:
        raise MetaError("Impossibile contattare Meta: controlla la connessione a internet.", str(e))
    try:
        body = r.json()
    except ValueError:
        raise MetaError(f"Risposta non valida da Meta (HTTP {r.status_code}).", r.text[:300])
    if isinstance(body, dict) and "error" in body:
        raise translate_error(body["error"], path)
    return body


# --- Clienti -----------------------------------------------------------------

def load_clients():
    return store.get("clients", {})


def save_clients(clients):
    store.set("clients", clients)


def load_client(key):
    clients = load_clients()
    if key not in clients:
        raise MetaError(f"Cliente '{key}' non trovato.", f"Disponibili: {', '.join(clients)}")
    return clients[key]


def page_token(page_id):
    return call("GET", page_id, fields="access_token")["access_token"]


# --- Motore a passaggi -------------------------------------------------------
# Ogni passaggio riceve lo stato `s` e restituisce True (fatto, vai avanti)
# o False (in attesa di Meta: richiamalo tra qualche secondo).

def advance(s):
    """Esegue un passaggio. Restituisce lo stato aggiornato."""
    steps = CAMPAIGN_STEPS if s["kind"] == "campagna" else POST_STEPS
    if s.get("done"):
        return s
    try:
        step = steps[s["step"]]
        if step(s):
            s["step"] += 1
            s["waits"] = 0
        else:
            s["waits"] = s.get("waits", 0) + 1
            if s["waits"] > s.get("max_waits", 150):
                raise MetaError("Meta ci mette troppo a elaborare il file.", "Riprova piu' tardi.")
        if s["step"] >= len(steps):
            s["done"] = True
    except MetaError as e:
        s["error"] = {"message": e.message, "detail": e.detail}
        s["done"] = True
    except Exception as e:  # noqa: BLE001 - mai lasciare un lavoro bloccato a meta'
        s["error"] = {"message": "Si e' verificato un errore imprevisto.", "detail": f"{type(e).__name__}: {e}"}
        s["done"] = True
    return s


def run_to_end(s, sleep=5, log=print):
    """Per CLI e scheduler: esegue tutti i passaggi aspettando quando serve."""
    printed = 0
    while not s.get("done"):
        before = s["step"]
        advance(s)
        for line in s["log"][printed:]:
            log(line)
        printed = len(s["log"])
        if s["step"] == before and not s.get("done"):
            time.sleep(sleep)
    return s


# --- Campagne ----------------------------------------------------------------

def new_campaign(key, overrides=None):
    """`overrides` sovrascrive i campi del cliente (video_url, primary_text, headline,
    lat, lng, radius_km, daily_budget_eur)."""
    c = {**load_client(key), **(overrides or {})}
    return {"kind": "campagna", "client": key, "c": c, "step": 0, "log": [], "result": {},
            "name": f"{c['name']} | Lead | {time.strftime('%Y-%m-%d %H:%M')}"}


def ads_manager_url(c, campaign_id):
    return ("https://adsmanager.facebook.com/adsmanager/manage/campaigns"
            f"?act={c['ad_account_id']}&selected_campaign_ids={campaign_id}")


def _act(s):
    return f"act_{s['c']['ad_account_id']}"


def step_checks(s):
    """Controlli prima di creare qualsiasi cosa, per non lasciare campagne a meta'."""
    pid = s["c"]["page_id"]
    page = call("GET", pid, fields="name,leadgen_tos_accepted")
    if not page.get("leadgen_tos_accepted"):
        raise MetaError(
            f"La pagina '{page.get('name', pid)}' non ha ancora accettato le Condizioni di Meta "
            "per le inserzioni di generazione contatti.",
            "Un amministratore della pagina deve aprire questo link e accettare (si fa una volta sola): "
            f"https://www.facebook.com/ads/leadgen/tos?page_id={pid}")
    s["log"].append("Controlli pagina OK.")
    return True


def cleanup_campaign(s):
    """Elimina quanto creato da un lavoro fallito: la campagna (con gruppo e inserzione
    che contiene) e archivia il modulo lead (i moduli non si possono eliminare)."""
    r = s["result"]
    if r.get("campaign_id"):
        call("DELETE", r["campaign_id"])
        s["log"].append(f"Campagna {r['campaign_id']} eliminata.")
    if r.get("form_id"):
        call("POST", r["form_id"], token_=page_token(s["c"]["page_id"]), status="ARCHIVED")
        s["log"].append(f"Modulo lead {r['form_id']} archiviato.")
    s["cleaned"] = True
    s["result"] = {}


def step_upload_video(s):
    s["result"]["video_id"] = call("POST", f"{_act(s)}/advideos", file_url=s["c"]["video_url"])["id"]
    s["log"].append(f"Video inviato a Meta ({s['result']['video_id']}), attendo l'elaborazione...")
    return True


def step_wait_video(s):
    vid = s["result"]["video_id"]
    status = call("GET", vid, fields="status")["status"]["video_status"]
    if status == "error":
        raise MetaError("Meta non e' riuscita a elaborare il video.",
                        "Prova con un MP4 diverso o un link diretto al file.")
    if status != "ready":
        return False
    thumbs = call("GET", f"{vid}/thumbnails").get("data", [])
    if thumbs:
        s["thumb"] = next((t for t in thumbs if t.get("is_preferred")), thumbs[0])["uri"]
    else:
        s["thumb"] = call("GET", vid, fields="picture")["picture"]
    s["log"].append("Video pronto.")
    return True


def step_campaign(s):
    cid = call(
        "POST", f"{_act(s)}/campaigns",
        name=s["name"],
        objective="OUTCOME_LEADS",
        status="PAUSED",
        special_ad_categories=[],
        is_adset_budget_sharing_enabled="false",
    )["id"]
    s["result"]["campaign_id"] = cid
    s["result"]["ads_manager_url"] = ads_manager_url(s["c"], cid)
    s["log"].append(f"Campagna creata: {cid}")
    return True


def step_adset(s):
    c = s["c"]
    adset = dict(
        name=f"{s['name']} | {c['radius_km']}km",
        campaign_id=s["result"]["campaign_id"],
        status="PAUSED",
        daily_budget=int(round(float(c["daily_budget_eur"]) * 100)),
        billing_event="IMPRESSIONS",
        optimization_goal="LEAD_GENERATION",
        bid_strategy="LOWEST_COST_WITHOUT_CAP",
        destination_type="ON_AD",
        promoted_object={"page_id": c["page_id"]},
        targeting={
            "geo_locations": {
                "custom_locations": [{
                    "latitude": float(c["lat"]),
                    "longitude": float(c["lng"]),
                    "radius": float(c["radius_km"]),
                    "distance_unit": "kilometer",
                }]
            },
            "age_min": int(c.get("age_min") or 25),
            "targeting_automation": {"advantage_audience": 0},
        },
    )
    # Obbligo DSA per inserzioni rivolte all'UE: beneficiario e pagante
    if c.get("dsa_beneficiary"):
        adset["dsa_beneficiary"] = c["dsa_beneficiary"]
        adset["dsa_payor"] = c.get("dsa_payor") or c["dsa_beneficiary"]
    s["result"]["adset_id"] = call("POST", f"{_act(s)}/adsets", **adset)["id"]
    s["log"].append(f"Gruppo di inserzioni creato: {s['result']['adset_id']}")
    return True


def step_form(s):
    # I moduli lead si creano con il token della PAGINA
    c = s["c"]
    s["result"]["form_id"] = call(
        "POST", f"{c['page_id']}/leadgen_forms", token_=page_token(c["page_id"]),
        name=s["name"],
        locale="it_IT",
        questions=[{"type": "FULL_NAME"}, {"type": "PHONE"}, {"type": "EMAIL"}],
        privacy_policy={"url": c["privacy_url"], "link_text": "Privacy policy"},
        follow_up_action_url=c["website"],
    )["id"]
    s["log"].append(f"Modulo lead creato: {s['result']['form_id']}")
    return True


def step_creative(s):
    c = s["c"]
    s["result"]["creative_id"] = call(
        "POST", f"{_act(s)}/adcreatives",
        name=s["name"],
        object_story_spec={
            "page_id": c["page_id"],
            "video_data": {
                "video_id": s["result"]["video_id"],
                "image_url": s["thumb"],
                "message": c["primary_text"],
                "title": c["headline"],
                "call_to_action": {
                    "type": "SIGN_UP",
                    "value": {"lead_gen_form_id": s["result"]["form_id"]},
                },
            },
        },
    )["id"]
    s["log"].append(f"Creativita' creata: {s['result']['creative_id']}")
    return True


def step_ad(s):
    s["result"]["ad_id"] = call(
        "POST", f"{_act(s)}/ads",
        name=s["name"],
        adset_id=s["result"]["adset_id"],
        creative={"creative_id": s["result"]["creative_id"]},
        status="PAUSED",
    )["id"]
    s["log"].append(f"Inserzione creata: {s['result']['ad_id']}")
    s["log"].append("Fatto. Tutto in PAUSA: controlla in Gestione inserzioni e attiva.")
    return True


CAMPAIGN_STEPS = [step_checks, step_upload_video, step_wait_video, step_campaign, step_adset,
                  step_form, step_creative, step_ad]


def launch(key):
    s = run_to_end(new_campaign(key))
    if s.get("error"):
        raise MetaError(s["error"]["message"], s["error"]["detail"])


# --- Report ------------------------------------------------------------------

def report_row(c, date_preset="last_30d", since=None, until=None):
    params = {"fields": "spend,impressions,actions,account_currency"}
    if since and until:
        params["time_range"] = {"since": since, "until": until}
    else:
        params["date_preset"] = date_preset
    rows = call("GET", f"act_{c['ad_account_id']}/insights", **params)["data"]
    if not rows:
        return {"name": c["name"], "spend": 0.0, "leads": 0, "cpl": None, "impressions": 0, "currency": ""}
    row = rows[0]
    spend = float(row.get("spend", 0))
    leads = sum(int(a["value"]) for a in row.get("actions", []) if a["action_type"] == "lead")
    return {
        "name": c["name"],
        "spend": spend,
        "leads": leads,
        "cpl": spend / leads if leads else None,
        "impressions": int(row.get("impressions", 0)),
        "currency": row.get("account_currency", ""),
    }


def report(key):
    keys = load_clients() if key == "all" else [key]
    for k in keys:
        r = report_row(load_client(k))
        if not r["spend"]:
            print(f"{r['name']}: nessuna spesa negli ultimi 30 giorni")
            continue
        cpl = f"{r['cpl']:.2f} {r['currency']}" if r["cpl"] else "n/d"
        print(f"{r['name']}: spesa {r['spend']:.2f} {r['currency']} | lead {r['leads']} | CPL {cpl}")


# --- Post organici (Pagina Facebook + Instagram) ----------------------------

def new_post(key, message, kind=None, media_url=None, fb=True, ig=True, scheduled_ts=None):
    """kind: None (solo testo), 'image' o 'video'. scheduled_ts vale per Facebook (nativo);
    per Instagram la programmazione la gestisce lo scheduler della web app."""
    return {"kind": "post", "client": key, "c": load_client(key), "step": 0, "log": [], "result": {},
            "message": message, "media": kind, "media_url": media_url, "fb": fb, "ig": ig,
            "scheduled_ts": scheduled_ts, "max_waits": 60}


def instagram_account(page_id):
    ig = call("GET", page_id, fields="instagram_business_account{id,username}").get("instagram_business_account")
    if not ig:
        raise MetaError("Questa pagina Facebook non ha un account Instagram professionale collegato.",
                        "Collega l'account Instagram alla pagina da Meta Business Suite.")
    return ig


def step_facebook(s):
    if not s["fb"]:
        return True
    pid = s["c"]["page_id"]
    ptok = page_token(pid)
    p = {}
    if s.get("scheduled_ts"):
        p = {"published": "false", "scheduled_publish_time": int(s["scheduled_ts"])}
    if s["media"] == "image":
        r = call("POST", f"{pid}/photos", token_=ptok, url=s["media_url"], message=s["message"], **p)
        fid = r.get("post_id") or r["id"]
    elif s["media"] == "video":
        fid = call("POST", f"{pid}/videos", token_=ptok, file_url=s["media_url"],
                   description=s["message"], **p)["id"]
    else:
        fid = call("POST", f"{pid}/feed", token_=ptok, message=s["message"], **p)["id"]
    s["result"]["facebook_id"] = fid
    s["log"].append(f"Facebook: {'programmato' if p else 'pubblicato'} ({fid})")
    return True


def step_ig_create(s):
    if not s["ig"]:
        return True
    if s["media"] not in ("image", "video"):
        raise MetaError("Su Instagram serve un'immagine o un video.", "")
    ig_id = instagram_account(s["c"]["page_id"])["id"]
    s["ig_id"] = ig_id
    if s["media"] == "image":
        url = s["media_url"]
        if not url.lower().split("?")[0].endswith((".jpg", ".jpeg")):
            # Instagram accetta solo JPEG: lo faccio convertire a Facebook caricando la foto
            # sulla pagina come non pubblicata, uso l'URL del CDN e poi la elimino.
            ptok = page_token(s["c"]["page_id"])
            s["temp_photo"] = call("POST", f"{s['c']['page_id']}/photos", token_=ptok,
                                   url=url, published="false", temporary="true")["id"]
            images = call("GET", s["temp_photo"], token_=ptok, fields="images")["images"]
            url = max(images, key=lambda i: i["width"])["source"]
        s["ig_container"] = call("POST", f"{ig_id}/media", image_url=url, caption=s["message"])["id"]
    else:
        s["ig_container"] = call("POST", f"{ig_id}/media", media_type="REELS",
                                 video_url=s["media_url"], caption=s["message"])["id"]
    s["log"].append("File inviato a Instagram, attendo l'elaborazione...")
    return True


def step_ig_wait(s):
    if not s["ig"]:
        return True
    st = call("GET", s["ig_container"], fields="status_code,status")
    code = st.get("status_code")
    if code in ("ERROR", "EXPIRED"):
        raise MetaError("Instagram non e' riuscito a elaborare il file.", st.get("status", ""))
    return code == "FINISHED"


def step_ig_publish(s):
    if not s["ig"]:
        return True
    s["result"]["instagram_id"] = call("POST", f"{s['ig_id']}/media_publish",
                                       creation_id=s["ig_container"])["id"]
    s["log"].append(f"Instagram: pubblicato ({s['result']['instagram_id']})")
    if s.get("temp_photo"):
        try:
            call("DELETE", s["temp_photo"], token_=page_token(s["c"]["page_id"]))
        except MetaError:
            pass
    return True


POST_STEPS = [step_facebook, step_ig_create, step_ig_wait, step_ig_publish]


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("launch", "report"):
        sys.exit(__doc__)
    try:
        {"launch": launch, "report": report}[sys.argv[1]](sys.argv[2])
    except MetaError as e:
        sys.exit(f"ERRORE: {e.message}\n{e.detail}")
