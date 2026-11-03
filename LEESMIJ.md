# Frans-bijles (2de jaar)

Bijlestutor Frans voor Nouveau Quartier français 2. Legt uit in het Nederlands, oefent in het Frans, en geeft nooit meteen het antwoord.

Er zijn twee versies:
- `app.py` – Streamlit-versie, voor online gebruik (Streamlit Community Cloud), met wachtwoord.
- `server.py` + `public/` – eenvoudige lokale versie op http://localhost:3001.

Het gedrag staat in `system-prompt-fr.md`.

## Online zetten (Streamlit Community Cloud)
1. Zet deze map in een eigen **privé** GitHub-repository. `.env` en `schoolwerk/` gaan niet mee (staat in `.gitignore`).
2. Ga naar share.streamlit.io > Create app > kies de repository, branch `main`, bestand `app.py`.
3. Advanced settings > Secrets:
   ```
   ANTHROPIC_API_KEY = "sk-ant-..."
   APP_PASSWORD = "kies-een-wachtwoord"
   ```
4. Deploy. Geef je dochter de link en het wachtwoord.

## Lokaal testen
```bash
pip3 install -r requirements.txt
streamlit run app.py
```
Lokaal (127.0.0.1) is geen wachtwoord nodig als APP_PASSWORD niet in `.env` staat.

## Kosten
Elk bericht en elke foto kost een klein bedrag via de API-sleutel. Stel in de Anthropic Console een maandlimiet in (liefst een aparte werkruimte/sleutel voor de bijlesbots).
