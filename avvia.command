#!/bin/bash
# Doppio clic per avviare il Meta Tool. Chiudi la finestra per spegnerlo.
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "Prima installazione, attendi..."
  python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt || { echo "Installazione fallita"; read -r; exit 1; }
fi
.venv/bin/python app.py
