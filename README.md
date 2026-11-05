# Meta Tool

Tool interno per Meta Ads e post organici: clienti, report (spesa, lead, CPL),
nuova campagna lead (creata in PAUSA) e pubblicazione su Pagina Facebook + Instagram.

## Online (Vercel)

Variabili d'ambiente (Vercel > Settings > Environment Variables):

| Variabile | Cosa |
|---|---|
| `META_TOKEN` | Token System User di Meta |
| `APP_PASSWORD` | Password per entrare nel tool (senza, il tool online non si apre) |
| `CRON_SECRET` | Segreto per `/cron/tick` (uguale nel secret GitHub `CRON_SECRET`) |
| `KV_REST_API_URL`, `KV_REST_API_TOKEN` | Impostate dall'integrazione Upstash Redis |
| `BLOB_READ_WRITE_TOKEN` | Impostata collegando lo store Vercel Blob |

Dopo aver cambiato una variabile serve un nuovo deploy.

I post Instagram programmati vengono pubblicati da `.github/workflows/tick.yml`
(ogni 5 minuti; GitHub puo' ritardare di qualche minuto).

## In locale

Doppio clic su `avvia.command` (oppure `python3 app.py`), poi http://127.0.0.1:5050.
Il token va in `.env` (`META_TOKEN=...`). Per avere le stesse variabili di Vercel:
`vercel env pull .env.local`. Senza Redis i dati restano in `clients.json` e `data/`.
