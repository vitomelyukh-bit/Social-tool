"""
Tool interno Meta Ads (modello agenzia, token System User).

Usato dalla web app (app.py) e ancora utilizzabile da riga di comando:
  python3 meta_ads.py launch test     # crea campagna completa in PAUSA
  python3 meta_ads.py report test     # spesa, lead e CPL ultimi 30 giorni
  python3 meta_ads.py report all

Il token si legge da .env (META_TOKEN=...).
"""
import json
import os
import sys
import time

import requests
from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, ".env"))

# v24.0 della Marketing API scade il 6/10/2026; v26.0 e' la corrente (29/07/2026).
# Changelog: https://developers.facebook.com/docs/graph-api/changelog
API_VERSION = "v26.0"
BASE = f"https://graph.facebook.com/{API_VERSION}"
VIDEO_BASE = f"https://graph-video.facebook.com/{API_VERSION}"  # per upload di file video
CLIENTS_FILE = os.path.join(HERE, "clients.json")


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
            "Apri il file .env nella cartella del tool e inserisci la riga META_TOKEN=... "
            "poi riavvia il programma.",
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
        if code == 100:
            msg = "Meta ha rifiutato uno dei dati inviati."
        else:
            msg = "Meta ha restituito un errore."
    # error_user_msg e' gia' pensato per l'utente finale (spesso in italiano grazie a locale=it_IT)
    detail_parts = [p for p in (user_title, user_msg) if p]
    detail = " - ".join(detail_parts) if detail_parts else raw
    if detail_parts and raw and raw not in detail:
        detail += f" (Meta: {raw})"
    where = f" [operazione: {path}]" if path else ""
    return MetaError(msg, detail + where)


# --- Chiamate API ------------------------------------------------------------

def call(method, path, token_=None, files=None, base=BASE, **params):
    data = {k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in params.items()}
    data["access_token"] = token_ or token()
    data.setdefault("locale", "it_IT")  # error_user_msg in italiano quando disponibile
    kwargs = {"params": data} if method == "GET" else {"data": data}
    if files:
        kwargs["files"] = files
    try:
        r = requests.request(method, f"{base}/{path}", timeout=600 if files else 120, **kwargs)
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
    if not os.path.exists(CLIENTS_FILE):
        return {}
    with open(CLIENTS_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_clients(clients):
    tmp = CLIENTS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(clients, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, CLIENTS_FILE)


def load_client(key):
    clients = load_clients()
    if key not in clients:
        raise MetaError(f"Cliente '{key}' non trovato.", f"Disponibili: {', '.join(clients)}")
    return clients[key]


def page_token(page_id):
    return call("GET", page_id, fields="access_token")["access_token"]


# --- Campagne ----------------------------------------------------------------

def upload_video(act, video_url=None, video_path=None, log=print):
    if video_path:
        with open(video_path, "rb") as f:
            video_id = call("POST", f"{act}/advideos", base=VIDEO_BASE,
                            files={"source": (os.path.basename(video_path), f)})["id"]
    else:
        video_id = call("POST", f"{act}/advideos", file_url=video_url)["id"]
    log(f"Video caricato ({video_id}), attendo l'elaborazione di Meta...")
    for _ in range(120):
        status = call("GET", video_id, fields="status")["status"]["video_status"]
        if status == "ready":
            break
        if status == "error":
            raise MetaError("Meta non e' riuscita a elaborare il video.",
                            "Prova con un MP4 diverso o un link diretto al file.")
        time.sleep(5)
    else:
        raise MetaError("Il video ci mette troppo a essere elaborato (oltre 10 minuti).", "Riprova piu' tardi.")
    thumbs = call("GET", f"{video_id}/thumbnails").get("data", [])
    if thumbs:
        thumb = next((t for t in thumbs if t.get("is_preferred")), thumbs[0])["uri"]
    else:
        thumb = call("GET", video_id, fields="picture")["picture"]
    return video_id, thumb


def create_lead_form(c, name):
    # I moduli lead si creano con il token della PAGINA
    return call(
        "POST", f"{c['page_id']}/leadgen_forms", token_=page_token(c["page_id"]),
        name=name,
        locale="it_IT",
        questions=[{"type": "FULL_NAME"}, {"type": "PHONE"}, {"type": "EMAIL"}],
        privacy_policy={"url": c["privacy_url"], "link_text": "Privacy policy"},
        follow_up_action_url=c["website"],
    )["id"]


def ads_manager_url(c, campaign_id):
    return ("https://adsmanager.facebook.com/adsmanager/manage/campaigns"
            f"?act={c['ad_account_id']}&selected_campaign_ids={campaign_id}")


def launch(key, overrides=None, log=print):
    """Crea campagna + ad set + modulo + creativita' + inserzione, tutto in PAUSA.

    `overrides` sovrascrive i campi del cliente (video_url/video_path, primary_text,
    headline, lat, lng, radius_km, daily_budget_eur).
    """
    c = {**load_client(key), **(overrides or {})}
    result = {}
    try:
        return _launch(c, result, log)
    except MetaError as e:
        e.partial = result  # cosa e' stato creato prima dell'errore
        raise


def _launch(c, result, log):
    act = f"act_{c['ad_account_id']}"
    name = f"{c['name']} | Lead | {time.strftime('%Y-%m-%d %H:%M')}"

    video_id, thumb_url = upload_video(act, c.get("video_url"), c.get("video_path"), log=log)
    result["video_id"] = video_id

    campaign_id = call(
        "POST", f"{act}/campaigns",
        name=name,
        objective="OUTCOME_LEADS",
        status="PAUSED",
        special_ad_categories=[],
        is_adset_budget_sharing_enabled="false",
    )["id"]
    result["campaign_id"] = campaign_id
    result["ads_manager_url"] = ads_manager_url(c, campaign_id)
    log(f"Campagna creata: {campaign_id}")

    adset = dict(
        name=f"{name} | {c['radius_km']}km",
        campaign_id=campaign_id,
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
    adset_id = call("POST", f"{act}/adsets", **adset)["id"]
    result["adset_id"] = adset_id
    log(f"Gruppo di inserzioni creato: {adset_id}")

    form_id = create_lead_form(c, name)
    result["form_id"] = form_id
    log(f"Modulo lead creato: {form_id}")

    creative_id = call(
        "POST", f"{act}/adcreatives",
        name=name,
        object_story_spec={
            "page_id": c["page_id"],
            "video_data": {
                "video_id": video_id,
                "image_url": thumb_url,
                "message": c["primary_text"],
                "title": c["headline"],
                "call_to_action": {
                    "type": "SIGN_UP",
                    "value": {"lead_gen_form_id": form_id},
                },
            },
        },
    )["id"]
    result["creative_id"] = creative_id
    log(f"Creativita' creata: {creative_id}")

    ad_id = call(
        "POST", f"{act}/ads",
        name=name,
        adset_id=adset_id,
        creative={"creative_id": creative_id},
        status="PAUSED",
    )["id"]
    result["ad_id"] = ad_id
    log(f"Inserzione creata: {ad_id}")
    log("Fatto. Tutto in PAUSA: controlla in Gestione inserzioni e attiva.")
    return result


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

def instagram_account(page_id):
    ig = call("GET", page_id, fields="instagram_business_account{id,username}").get("instagram_business_account")
    if not ig:
        raise MetaError("Questa pagina Facebook non ha un account Instagram professionale collegato.",
                        "Collega l'account Instagram alla pagina da Meta Business Suite.")
    return ig


def publish_facebook(c, message, kind=None, media_url=None, media_path=None, scheduled_ts=None):
    """kind: None (solo testo), 'image' o 'video'. scheduled_ts: unix timestamp o None."""
    pid = c["page_id"]
    ptok = page_token(pid)
    sched = {"published": "false", "scheduled_publish_time": int(scheduled_ts)} if scheduled_ts else {}

    def send(path, base=BASE, file_field="source", **params):
        if media_path:
            with open(media_path, "rb") as f:
                return call("POST", path, token_=ptok, base=base,
                            files={file_field: (os.path.basename(media_path), f)}, **params, **sched)
        return call("POST", path, token_=ptok, base=base, **params, **sched)

    if kind == "image":
        extra = {} if media_path else {"url": media_url}
        r = send(f"{pid}/photos", message=message, **extra)
        return r.get("post_id") or r["id"]
    if kind == "video":
        extra = {} if media_path else {"file_url": media_url}
        return send(f"{pid}/videos", base=VIDEO_BASE, description=message, **extra)["id"]
    return call("POST", f"{pid}/feed", token_=ptok, message=message, **sched)["id"]


def _wait_ig_container(container_id, log):
    for _ in range(60):
        st = call("GET", container_id, fields="status_code,status")
        code = st.get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise MetaError("Instagram non e' riuscito a elaborare il file.", st.get("status", ""))
        time.sleep(10)
    raise MetaError("Instagram ci mette troppo a elaborare il file (oltre 10 minuti).", "")


def publish_instagram(c, caption, kind, media_url=None, media_path=None, log=print):
    """Pubblica subito su Instagram. Le API Instagram non supportano la programmazione:
    i post programmati vengono pubblicati dalla web app all'ora indicata."""
    if kind not in ("image", "video"):
        raise MetaError("Su Instagram serve un'immagine o un video.", "")
    ig_id = instagram_account(c["page_id"])["id"]
    temp_photo = None
    try:
        if kind == "image":
            if media_path:
                # Instagram vuole un URL pubblico: carico la foto sulla pagina come non pubblicata
                # e uso il suo indirizzo CDN, poi la elimino.
                ptok = page_token(c["page_id"])
                with open(media_path, "rb") as f:
                    temp_photo = call("POST", f"{c['page_id']}/photos", token_=ptok, published="false",
                                      temporary="true", files={"source": (os.path.basename(media_path), f)})["id"]
                images = call("GET", temp_photo, token_=ptok, fields="images")["images"]
                media_url = max(images, key=lambda i: i["width"])["source"]
            container = call("POST", f"{ig_id}/media", image_url=media_url, caption=caption)["id"]
        else:
            if media_path:
                container = call("POST", f"{ig_id}/media", media_type="REELS", caption=caption,
                                 upload_type="resumable")["id"]
                size = os.path.getsize(media_path)
                with open(media_path, "rb") as f:
                    r = requests.post(
                        f"https://rupload.facebook.com/ig-api-upload/{API_VERSION}/{container}",
                        headers={"Authorization": f"OAuth {token()}", "offset": "0", "file_size": str(size)},
                        data=f, timeout=1200,
                    )
                body = r.json() if r.content else {}
                if "error" in body or not body.get("success", r.ok):
                    raise translate_error(body.get("error") or {"message": r.text[:300]}, "upload video Instagram")
            else:
                container = call("POST", f"{ig_id}/media", media_type="REELS", video_url=media_url,
                                 caption=caption)["id"]
        log("File inviato a Instagram, attendo l'elaborazione...")
        _wait_ig_container(container, log)
        return call("POST", f"{ig_id}/media_publish", creation_id=container)["id"]
    finally:
        if temp_photo:
            try:
                call("DELETE", temp_photo, token_=page_token(c["page_id"]))
            except MetaError:
                pass


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("launch", "report"):
        sys.exit(__doc__)
    try:
        {"launch": launch, "report": report}[sys.argv[1]](sys.argv[2])
    except MetaError as e:
        sys.exit(f"ERRORE: {e.message}\n{e.detail}")
