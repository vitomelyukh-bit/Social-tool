# Revisione dell'app Meta (accesso avanzato)

Cosa compilare nella dashboard dell'app Meta e cosa registrare per la revisione.
Lo strumento usa un token di **utente di sistema** (Business Manager), non il Login con Facebook.

## Impostazioni › Di base

| Campo | Valore |
|---|---|
| URL informativa privacy | https://social-tool-iota.vercel.app/privacy |
| URL eliminazione dati | https://social-tool-iota.vercel.app/eliminazione-dati (scegli "URL istruzioni", non "callback") |
| Icona 1024×1024 | `static/icon-1024.png` |
| Categoria | Business e pagine (Business and Pages) |
| Dominio dell'app | social-tool-iota.vercel.app (o il dominio definitivo, se lo cambiamo) |
| DPO / GDPR | email e indirizzo del titolare, paese **Italia** |

Le pagine privacy ed eliminazione dati leggono ragione sociale, indirizzo, P. IVA, email e DPO da
`OWNER` in `app.py`: finché sono vuoti mostrano "da completare" in rosso. Vanno compilati prima di inviare.

## Casi d'uso

Tieni solo quelli che usiamo davvero: meno permessi chiedi, meno screencast servono e più è facile l'approvazione.

- **Tenere**: Marketing API (crea e gestisci inserzioni), Pagine (gestisci tutto sulla Pagina), Instagram (gestisci messaggi e contenuti, solo pubblicazione).
- **Togliere**: WhatsApp e Login for Business (il codice non li usa). Lead ads: lo strumento crea i moduli ma **non** scarica i contatti, quindi `leads_retrieval` non serve.

## Permessi da richiedere (accesso avanzato)

Solo quelli che il codice usa (`meta_ads.py`). Descrizioni in inglese, come le legge il revisore.

| Permesso | Dove lo usiamo | Descrizione per Meta |
|---|---|---|
| `business_management` | accesso alle risorse dei clienti condivise col nostro Business Manager | Our agency manages Pages, Instagram accounts and ad accounts that clients share with our Business Manager. The system user needs this to access those business assets. |
| `pages_show_list` | elenco e token delle Pagine | Used to list the client Pages our system user has access to and obtain their Page access token. |
| `pages_read_engagement` | nome della Pagina, account Instagram collegato, permalink | Used to read basic Page information (name, linked Instagram account) shown in the tool before publishing. |
| `pages_manage_posts` | `/{page}/feed`, `/photos`, `/videos` | Our staff publish and schedule text, photo and video posts on client Pages from the "Pubblica post" screen. |
| `pages_manage_ads` | `/{page}/leadgen_forms`, controllo termini lead ads | Used to create the lead form attached to a client's lead ad campaign. |
| `instagram_basic` | id e username dell'account Instagram della Pagina | Used to find the Instagram professional account linked to the client Page and show its username. |
| `instagram_content_publish` | `/{ig}/media`, `/media_publish` | Our staff publish photos and Reels to the client Instagram account, immediately or at a scheduled time. |
| `ads_management` | campagne, gruppi, video e inserzioni | Our staff create lead generation campaigns (campaign, ad set, creative, ad) in client ad accounts from the "Nuova campagna" screen. |
| `ads_read` | `/act_{id}/insights` | The "Risultati" screen shows spend, impressions, clicks, leads and cost per lead of client campaigns. |

## Screencast (uno per permesso, si può riusare lo stesso video)

Registra lo schermo a 1080p, in inglese o con sottotitoli/didascalie in inglese, senza tagli nei passaggi chiave.
Meta vuole vedere: login allo strumento, la scelta della risorsa, l'azione, e il risultato **su Facebook/Instagram**.

1. **Pubblicazione Facebook + Instagram** (pages_manage_posts, pages_show_list, pages_read_engagement, instagram_basic, instagram_content_publish):
   apri https://social-tool-iota.vercel.app → accedi → Pubblica post → scegli il cliente → carica un'immagine,
   scrivi il testo, spunta Facebook e Instagram → Pubblica → attendi i passi verdi → apri il link del post
   su Facebook e su Instagram e mostra che è online. Poi mostra anche un post programmato e il suo annullamento.
2. **Campagna lead** (ads_management, pages_manage_ads, business_management): Nuova campagna → cliente →
   video, testi, budget → crea → apri Gestione inserzioni e mostra campagna, gruppo, inserzione e modulo creati
   (in pausa, così non spendono).
3. **Risultati** (ads_read): Risultati → cliente → periodo → mostra la tabella con spesa e contatti, e gli stessi
   numeri in Gestione inserzioni.

## Accesso per il revisore

Nelle note per il revisore (App Review › Istruzioni) metti URL, una password valida e i passi sopra.
Conviene una password temporanea: cambia `APP_PASSWORD` su Vercel per la durata della revisione e rimettila dopo.
Il revisore deve poter pubblicare su una Pagina e un account Instagram di prova, non su quelli dei clienti:
crea un cliente "Test" con una Pagina e un Instagram nostri.

## Verifica dell'azienda

Per l'accesso avanzato serve anche la **verifica dell'azienda** (Business Verification) del Business Manager
proprietario dell'app, se non è già fatta: Impostazioni dell'azienda › Centro sicurezza.
