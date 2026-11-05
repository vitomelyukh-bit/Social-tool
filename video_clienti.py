"""
Clienti video di partenza: White Garden e Avvocato Ricci, con tutto quello che è emerso dai montaggi
(ottobre-novembre 2026). Vengono inseriti una sola volta (chiave store "video:seed:v1"); se il cliente
esiste già (stesso nome) e non ha ancora un brand video, gli viene assegnato questo.
"""
import store

SEED_FLAG = "video:seed:v1"

CLIENTI = {
    "white-garden": {
        "match": ["white garden"],
        "name": "White Garden Tattoo",
        "brand": {
            "settore": "Studio di tatuaggi (cover up, promo, concorsi)",
            "handle": "", "instagram": "",
            "tool": "CapCut: bozze native che poi l'utente rifinisce. Se l'utente ci ha già lavorato, modificare la bozza "
                    "IN PLACE (con backup, a CapCut chiuso), mai rigenerarla da zero. DaVinci solo se richiesto.",
            "colors": {"highlight": "#89F0D8", "text": "#FFFFFF", "outline": "#000000", "box": "#111111"},
            "fonts": {"captions": "Montserrat ExtraBold", "titles": "Montserrat ExtraBold", "cta": "Montserrat ExtraBold"},
            "captions": {"style": "parola", "uppercase": True, "effect": "contorno", "words": "1-3",
                         "position": "centro-basso", "size": "66 px su 1080x1920 (in CapCut: dimensione 12)", "y": "1300"},
            "safezone": "- Grafiche e testi MAI sul viso: sotto il mento (y 1030-1200), sopra i sottotitoli.\n"
                        "- x < 940 (a destra ci sono le icone di Instagram).\n"
                        "- Mai inquadrare lei girata mentre parla o appena prima: fermare 2-6 fotogrammi sul fotogramma buono "
                        "o coprire con B-roll.",
            "cta": "Chiusura sul logo: l'ultimo fotogramma del viso si sfoca, il logo entra con un flash di luce, musica più "
                   "alta (+2 dB). Nei video a tema si aggiungono elementi decorativi (es. Halloween: zucche, pipistrelli, "
                   "ragnatele). Mai chiusure nere tipo TV che si spegne.",
            "look": "Correzione colore con le regolazioni di CapCut su ogni clip, tranne il logo. Al massimo una vignetta "
                    "morbida; niente sfarfallii neri o tendine scure.",
            "audio": "- È una pubblicità (ADV) per attirare clienti, non un video «carino»: ritmo alto.\n"
                     "- Voce: togliere TUTTE le pause tra le frasi (si parte sulla prima sillaba), voce a x1,10. Mai tagliare "
                     "i silenzi DENTRO le parole (le consonanti doppie tipo «macchia», «copriamo»): nei punti delicati "
                     "velocità naturale.\n"
                     "- Voce su traccia separata, perché il cliente può sostituirla con una versione pulita.\n"
                     "- Musica dinamica che crea aspettativa e «gasa» (es. dance/trap 140 bpm), con drop sui momenti "
                     "chiave, ~10 dB sotto la voce in ducking.\n"
                     "- Tanti whoosh, swoosh e pop; colpi d'impatto sulle parole chiave (GRATIS, SPAVENTOSO, BRUTTO).\n"
                     "- Master -14 LUFS, picco -1,5 dBTP.",
            "retouch": "Non richiesto.",
            "avoid": "- Foto generiche dello studio, B-roll disegnati o illustrati, etichette tipo «MOSTRO N°1».\n"
                     "- Sfarfallii neri, ombre scure come effetto, chiusure nere.\n"
                     "- Pause lunghe e inizi lenti.\n"
                     "- Dati personali visibili nelle schermate (nomi, numeri): sfocarli.\n"
                     "- Parolacce in chiaro nei sottotitoli (censurare, es. «C***O»).",
            "reference": "- Reel di riferimento per i sottotitoli: ~/Downloads/IMG_6667.mp4.\n"
                         "- Lavori: White Garden/WG - Nov-26/Claude/ (Halloween 1 e 2, 27.10, Vincitore «Mostro cercasi»).\n"
                         "- Foto prima/dopo dei cover up veri: ~/Downloads/3 cover Up.\n"
                         "- Logo: ~/Desktop/LAVORO REELS/IMG_2928.jpg (chiedere al cliente una versione HD).",
            "notes": "Profilo Instagram da inserire. Prendere il colore esatto del logo se il cliente manda il file vettoriale.",
        },
        "style": """Tono: pubblicità diretta e divertente, deve attirare persone in studio.
- Hook immediato: il passaggio più forte nei primi 1-2 secondi; spesso un titolo o un countdown d'apertura.
- Jump cut coperti da zoom alternati (punch-in), ritmo serrato.
- Parole chiave GRANDI a schermo con suono d'impatto.
- Quando si parla di «mostri» o cover up: foto VERE prima/dopo dello studio, con etichette PRIMA/DOPO e
  rivelazione con flash (o slider PRIMA/DOPO).
- Sottotitoli: Montserrat ExtraBold MAIUSCOLO, bianchi, contorno nero + ombra morbida; si colora solo la
  parola detta (#89F0D8); centrati a y 1300.
- Trend e gag (es. «Ok, ma prima? … Prima ancora?»): titolo POV in alto sulla parete, effetti comici.
- Promo e concorsi: le condizioni (sconto, gratis, scadenza) devono restare corrette e leggibili.""",
    },
    "avvocato-ricci": {
        "match": ["ricci"],
        "name": "Avvocato Ricci",
        "brand": {
            "settore": "Studio legale: avvocato del lavoro (licenziamenti, contratti, straordinari, stipendi)",
            "handle": "@legalericci", "instagram": "https://www.instagram.com/legalericci/",
            "tool": "CapCut (bozze native; se l'utente ha già montato un progetto, si modifica in place con backup e a "
                    "CapCut chiuso; i file vanno messi dentro la cartella della bozza, Resources/). DaVinci con .drp solo se "
                    "richiesto.",
            "colors": {"highlight": "#E9E6BA", "text": "#FFFFFF", "outline": "#000000", "box": "#0A0A0A"},
            "fonts": {"captions": "Montserrat ExtraBold", "titles": "Montserrat ExtraBold", "cta": "Montserrat ExtraBold"},
            "captions": {"style": "karaoke", "uppercase": True, "effect": "contorno", "words": "1-3",
                         "position": "centro-basso", "size": "72-76 px su 1080x1920 («dimensione 12» in CapCut)",
                         "y": "~1300"},
            "safezone": "- Tutto dentro y 220-1520 e x < 940.\n"
                        "- B-roll PICCOLI: schede ~900x460 sotto il mento (centro y ~1250), che restino a schermo abbastanza "
                        "da essere lette senza allungare il video.\n"
                        "- MAI sottotitoli sopra i B-roll; le schede si agganciano ai gruppi di sottotitoli, mai a metà frase.",
            "cta": "Box nero con «INFO» (Montserrat, color crema #E9E6BA) che parte dal dito quando dice «scrivi info», "
                   "scorre SOLO in orizzontale seguendo la mano e si ferma al centro, sotto i sottotitoli. Niente «Segui @…» "
                   "a video.",
            "look": "Correzione colore professionale (regolazioni CapCut o LUT Avvocato_Pro.cube): contrasto e incarnato "
                    "caldo, naturale. Nessuna vignettatura.",
            "audio": "- Voce: NON elaborarla (niente filtri), solo guadagno lineare; uniformare il volume tra le riprese "
                     "(~-19 LUFS per pezzo, master -14 LUFS). Se il cliente manda una voce migliorata, si usa quella.\n"
                     "- Ai bordi dei tagli: lasciare il respiro prima e la coda intera delle parole; controllare smorfie e "
                     "rumori di bocca a ogni taglio.\n"
                     "- NIENTE musica sintetizzata (rifiutata). Musica solo se fornita/approvata.\n"
                     "- Effetti: un pop all'arrivo di ogni B-roll (pochi: «troppe bollicine» no), swish sulle transizioni "
                     "zoom ai cambi di argomento, suono su ogni timbro VIETATO/FALSO. Niente riser, ding o whoosh in più.",
            "retouch": "Leggero e naturale («non troppo»): pelle 0,35-0,55, denti 0,55-0,75, rughe attenuate. Non sfocare i "
                       "capelli grigi.",
            "avoid": "- Vignettature e ombreggiature.\n"
                     "- Musica sintetizzata.\n"
                     "- Keyframe di zoom generati che «schiacciano» la persona in CapCut.\n"
                     "- B-roll «scritti a mano» (rifiutati): usare infografiche pulite.\n"
                     "- Promettere risultati legali; mostrare dati personali.\n"
                     "- Promettere nel titolo cose che non dice (es. «5 frasi» se ne dice meno).\n"
                     "- Voci fuori campo del regista nel montaggio («vai», «ok», «grazie»...).",
            "reference": "- Lavori: AVV Ottobre/ (Vid 3-8, V5-V8) e AVV NOVEMBRE/22-10/ (Vid 2-5, Motion Graphics).\n"
                         "- I file nuovi in Documenti vanno trascinati nel terminale (il Terminale non ha accesso alla cartella).",
            "notes": "Profilo Instagram da verificare (@legalericci). Rosso per etichette/timbri (VIETATO, FALSO).",
        },
        "style": """Tono autorevole, chiaro, sobrio: costruire fiducia e generare contatti («scrivi INFO»).
- Struttura: domanda forte come hook (meglio con un oggetto in mano) → risposta breve → esempio concreto
  o calcolo → consiglio → CTA «scrivi INFO qua sotto».
- Titolo d'apertura DIVERSO dai sottotitoli: box nero in alto, riga piccola bianca + parola/frase su etichetta
  rossa. Formato domanda + gancio, es. «LAVORI PIÙ ORE DEL DOVUTO? / POTRESTI RECUPERARE 8.000 €».
- Sottotitoli karaoke: bianco MAIUSCOLO, il crema #E9E6BA riempie le lettere seguendo la voce, contorno nero,
  niente box/ombra/rimbalzo; 1-3 parole su una riga, divisi per senso, senza punti; in CapCut una sola clip
  (i karaoke a 1-3 parole sfarfallano). Testo corretto a mano (nomi, termini legali).
- B-roll: infografiche sobrie in stile V8 (pop, contatori, timbri VIETATO/FALSO in rosso, orologio, busta
  paga, calendario), piccole sotto il mento.
- Gesti con le mani (es. X): zoom sulle mani + tremolio + X rossa + impatto.
- Transizioni solo all'inizio e ai cambi di argomento (zoom con swish).
- Parolacce accennate: terremoto con bordi a specchio, flash rosso, «#@!%&*», beep; niente scritta CENSURATO.
- Non alterare il significato: conservare condizioni ed eccezioni giuridiche.""",
    },
}


def ensure_seed(load_clients, save_clients):
    """Inserisce White Garden e Ricci una volta sola. Non sovrascrive brand già impostati."""
    if store.get(SEED_FLAG, False):
        return
    clients = load_clients()
    changed = False
    for key, seed in CLIENTI.items():
        video = {"brand": seed["brand"], "style_prompt": seed["style"]}
        found = key if key in clients else next(
            (k for k, c in clients.items() if any(m in c.get("name", "").lower() for m in seed["match"])), None)
        if found is None:
            clients[key] = {"name": seed["name"], "video": video}
            changed = True
        elif not clients[found].get("video"):
            clients[found]["video"] = video
            changed = True
    if changed:
        save_clients(clients)
    store.set(SEED_FLAG, True)
