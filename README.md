# Meta Tool

Tool interno per Meta Ads e post organici: clienti, report (spesa, lead, CPL),
nuova campagna lead (creata in PAUSA) e pubblicazione su Pagina Facebook + Instagram.
Sezione **Video**: Reels/TikTok montati da Claude con brand e regole di ogni cliente (vedi sotto).

## Online (Vercel)

Variabili d'ambiente (Vercel > Settings > Environment Variables):

| Variabile | Cosa |
|---|---|
| `META_TOKEN` | Token System User di Meta |
| `APP_PASSWORD` | Password per entrare nel tool (senza, il tool online non si apre) |
| `CRON_SECRET` | Segreto per `/cron/tick` (uguale nel secret GitHub `CRON_SECRET`) |
| `KV_REST_API_URL`, `KV_REST_API_TOKEN` | Impostate dall'integrazione Upstash Redis |
| `BLOB_READ_WRITE_TOKEN` | Impostata collegando lo store Vercel Blob |
| `WORKER_TOKEN` | Codice lungo a caso che usano i Mac per montare i video (sezione Video) |

Dopo aver cambiato una variabile serve un nuovo deploy.

I post Instagram programmati vengono pubblicati da `.github/workflows/tick.yml`
(ogni 5 minuti; GitHub puo' ritardare di qualche minuto).

## In locale

Doppio clic su `avvia.command` (oppure `python3 app.py`), poi http://127.0.0.1:5050.
Il token va in `.env` (`META_TOKEN=...`). Per avere le stesse variabili di Vercel:
`vercel env pull .env.local`. Senza Redis i dati restano in `clients.json` e `data/`.

## Video (montaggi con Claude)

- Ogni cliente (anche «solo video», senza dati Meta) ha brand video (colori, font, sottotitoli,
  CTA, logo) e regole di montaggio; in «Prompt e Mac» c'è il prompt base dell'editor.
- In un video carichi il girato (va su Blob sotto `studio/`, che la pulizia delle 48 ore non tocca),
  scrivi all'editor in chat e scarichi la consegna (video finale, copertina, SRT, riepilogo).
- Il montaggio lo fanno i Mac con il repo **video-editor**: `npm run worker -- --login` (indirizzo del
  tool + `WORKER_TOKEN`), poi `npm run worker`. Usano Claude Code con l'abbonamento, niente chiavi API.
- Codice: `video.py` (pagine + API `/api/worker/*` per i Mac), `templates/video_*.html`.
- I file su Blob sono pubblici ma con indirizzo non indovinabile: non condividere i link.
