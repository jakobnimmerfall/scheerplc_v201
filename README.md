# Arbeitsorte – Wochenansicht (Flask, Python 3.9)

Eine kleine Web-App, mit der Nutzer:innen pro Tag der ausgewählten Kalenderwoche einen Arbeitsort (Homeoffice, Office, Customer) festlegen und als Excel exportieren können.

## Features
- **Voreinstellung**: aktuelles Jahr und aktuelle Kalenderwoche
- **Manuelle Auswahl**: Jahr und KW anpassen (inkl. Navigation zu Vor-/Folgewoche)
- **Wochenansicht**: Montag–Sonntag mit Auswahl pro Tag
- **Namensfeld**: Name wird im Export mitgeführt
- **Export**: Download einer `.xlsx`-Datei (Excel)
- **Stateless**: Keine Datenbank, gut geeignet für Cloud Run

## Lokal starten
```bash
python3.9 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
# Öffnen: http://localhost:8080
```

Oder mit Gunicorn:
```bash
gunicorn -b 0.0.0.0:8080 app:app
```

## Deployment auf **Google Cloud Run**
> Voraussetzung: gcloud CLI installiert und Projekt konfiguriert (`gcloud init`, `gcloud auth login`).

1. **Container bauen und in Artifact Registry/Container Registry pushen**  
   ```bash
   gcloud builds submit --tag gcr.io/PROJECT_ID/arbeitsorte:latest
   ```

2. **Auf Cloud Run deployen** (Region-Beispiel: `europe-west1`)  
   ```bash
   gcloud run deploy arbeitsorte \
     --image gcr.io/PROJECT_ID/arbeitsorte:latest \
     --platform managed \
     --region europe-west1 \
     --allow-unauthenticated
   ```

3. **Öffentliche URL** wird im CLI-Output angezeigt.

### Konfiguration
- Der Service lauscht auf Port `8080` (per `PORT`-Env überschreibbar).
- Keine persistenten Daten – Exporte werden on-the-fly generiert und direkt ausgeliefert.

## Ordnerstruktur
```
arbeitsorte_app/
├─ app.py
├─ requirements.txt
├─ Dockerfile
└─ templates/
   └─ index.html
```

Viel Erfolg! 🙌
