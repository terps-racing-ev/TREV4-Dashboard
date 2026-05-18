# Dashboard

## Runtime dashboard

```bash
python -m app.main
```

Runtime configuration now lives in `config/config.json`; DBC files live in `config/`.

## Browser editor

Install Python and web dependencies, build the frontend once, then start the editor:

```bash
pip install -r requirements.txt
cd web
npm install
npm run build
cd ..
python web/dash_editor.py
```

Open `http://<raspberry-pi-ip>:8000` from a laptop on the car network. The editor keeps changes in a draft until `Save` is pressed and renders previews through the real Pygame gauge code.
