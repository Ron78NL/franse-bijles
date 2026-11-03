"""Frans-bijles (2de jaar) als Streamlit-app, voor Streamlit Community Cloud.

Secrets (in Streamlit Cloud > App settings > Secrets, of lokaal in .env):
  ANTHROPIC_API_KEY = "sk-ant-..."
  APP_PASSWORD      = "een wachtwoord voor je dochter"
  MODEL             = "claude-sonnet-5-5"   (optioneel)
"""
import base64
import hmac
import json
import os
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Frans-bijles", page_icon="🇫🇷", layout="centered")

ROOT = Path(__file__).resolve().parent
API_URL = "https://api.anthropic.com/v1/messages"
MAX_BERICHTEN = 20          # zoveel laatste berichten gaan mee naar Claude
MAX_UPLOAD_MB = 20
BEGROETING = "Hoi! 👋 Waaraan wil je vandaag werken? Je mag ook een foto van je oefening sturen."


# ---------------------------------------------------------------- instellingen
def load_env():
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


load_env()


def geheim(naam, standaard=""):
    try:
        if naam in st.secrets:
            return str(st.secrets[naam])
    except Exception:
        pass
    return os.environ.get(naam, standaard)


MODEL = geheim("MODEL", "claude-sonnet-5-5")


def is_lokaal():
    return str(st.get_option("server.address") or "") in ("127.0.0.1", "localhost", "::1")


# ---------------------------------------------------------------- wachtwoord
def controleer_toegang():
    wachtwoord = geheim("APP_PASSWORD")
    if not wachtwoord:
        if is_lokaal():
            return
        st.error("Er is nog geen wachtwoord ingesteld (APP_PASSWORD in de Secrets).")
        st.stop()
    if st.session_state.get("ingelogd"):
        return
    pogingen = st.session_state.get("pogingen", 0)
    st.title("🇫🇷 Frans-bijles")
    if pogingen >= 5 and time.time() - st.session_state.get("laatste_poging", 0) < 60:
        st.warning("Te veel pogingen. Wacht een minuutje en probeer opnieuw.")
        st.stop()
    with st.form("login"):
        invoer = st.text_input("Wachtwoord", type="password")
        if st.form_submit_button("Inloggen", type="primary"):
            if hmac.compare_digest(invoer.encode(), wachtwoord.encode()):
                st.session_state.ingelogd = True
                st.session_state.pogingen = 0
                st.rerun()
            st.session_state.pogingen = pogingen + 1
            st.session_state.laatste_poging = time.time()
            st.error("Dat wachtwoord klopt niet.")
    st.stop()


controleer_toegang()


# ---------------------------------------------------------------- Claude
def ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def system_prompt():
    f = ROOT / "system-prompt-fr.md"
    return f.read_text(encoding="utf-8") if f.exists() else ""


def call_claude(messages):
    key = geheim("ANTHROPIC_API_KEY")
    if not key:
        return None, "Er is geen API-sleutel ingesteld. Vraag papa om dat na te kijken."
    payload = json.dumps({
        "model": MODEL,
        "max_tokens": 1000,
        "system": system_prompt(),
        "messages": messages,
    }).encode("utf-8")
    req = urllib.request.Request(API_URL, data=payload, method="POST", headers={
        "content-type": "application/json",
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
    })
    try:
        with urllib.request.urlopen(req, timeout=90, context=ssl_context()) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        tekst = "\n".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        return tekst.strip(), None
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")
        print(f"API-fout {e.code}: {detail}")
        if e.code == 400 and "credit" in detail.lower():
            return None, "Het tegoed van de tutor is op. Vraag papa om het aan te vullen."
        if e.code == 429:
            return None, "Even te veel vragen na elkaar. Wacht een minuutje en probeer opnieuw."
        return None, f"De tutor kon niet antwoorden (fout {e.code}). Probeer het straks opnieuw."
    except Exception as e:
        print(f"Verbindingsfout: {e}")
        return None, "Ik kan de tutor nu niet bereiken. Probeer het straks opnieuw."


# ---------------------------------------------------------------- toestand
if "messages" not in st.session_state:
    st.session_state.messages = []          # alleen tekst, voor het scherm en de geschiedenis
if "upload_key" not in st.session_state:
    st.session_state.upload_key = 0


def nieuw_gesprek():
    st.session_state.messages = []
    st.session_state.upload_key += 1


# ---------------------------------------------------------------- zijbalk
with st.sidebar:
    st.header("📎 Foto of pdf")
    bestanden = st.file_uploader(
        "Foto's of pdf's van je oefening",
        type=["jpg", "jpeg", "png", "webp", "pdf"],
        accept_multiple_files=True,
        key=f"upload_{st.session_state.upload_key}",
        help="De bijlage gaat mee met je volgende bericht.",
    )
    if bestanden:
        st.caption("Gaat mee met je volgende bericht: " + ", ".join(b.name for b in bestanden))

    st.markdown("---")
    with st.expander("📘 Spiekbriefje", expanded=False):
        st.markdown(
            "**être**: je suis · tu es · il/elle est · nous sommes · vous êtes · ils/elles sont\n\n"
            "**avoir**: j'ai · tu as · il/elle a · nous avons · vous avez · ils/elles ont\n\n"
            "**-ER** (parler): je parle · tu parles · il parle · nous parlons · vous parlez · ils parlent\n\n"
            "**-GER / -CER**: nous mange**o**ns · nous commen**ç**ons\n\n"
            "**et** = en · **est** = is"
        )

    st.markdown("---")
    if st.button("🔄 Nieuw gesprek", width="stretch"):
        nieuw_gesprek()
        st.rerun()
    st.caption("Je tutor helpt je nadenken, maar het werk doe je zelf. 💪")


# ---------------------------------------------------------------- chat
st.title("🇫🇷 Frans-bijles")

with st.chat_message("assistant", avatar="🇫🇷"):
    st.markdown(BEGROETING)

for m in st.session_state.messages:
    with st.chat_message(m["role"], avatar="🇫🇷" if m["role"] == "assistant" else None):
        if m.get("bijlagen"):
            st.caption("📎 " + ", ".join(m["bijlagen"]))
        st.markdown(m["content"])

vraag = st.chat_input("Typ je vraag of je poging…")
if vraag:
    vraag = vraag.strip() or "(Zie bijlage)"

    delen, namen, te_groot = [], [], []
    for b in bestanden or []:
        data = b.getvalue()
        if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
            te_groot.append(b.name)
            continue
        b64 = base64.b64encode(data).decode()
        if b.type == "application/pdf" or b.name.lower().endswith(".pdf"):
            delen.append({"type": "document",
                          "source": {"type": "base64", "media_type": "application/pdf", "data": b64}})
        else:
            delen.append({"type": "image",
                          "source": {"type": "base64", "media_type": b.type or "image/jpeg", "data": b64}})
        namen.append(b.name)
    if te_groot:
        st.warning("Te groot (max. %d MB): %s" % (MAX_UPLOAD_MB, ", ".join(te_groot)))

    with st.chat_message("user"):
        if namen:
            st.caption("📎 " + ", ".join(namen))
        st.markdown(vraag)

    # Geschiedenis als tekst; de bijlagen alleen bij het nieuwe bericht (bespaart kosten).
    geschiedenis = [{"role": "assistant", "content": BEGROETING}] + [
        {"role": m["role"], "content": m["content"]} for m in st.session_state.messages
    ]
    geschiedenis = geschiedenis[-MAX_BERICHTEN:]
    while geschiedenis and geschiedenis[0]["role"] == "user":
        geschiedenis = geschiedenis[1:]
    api = [{"role": "user", "content": "(Een nieuwe sessie begint.)"}]
    api += geschiedenis
    api.append({"role": "user", "content": delen + [{"type": "text", "text": vraag}]})

    with st.chat_message("assistant", avatar="🇫🇷"):
        with st.spinner("De tutor denkt na…"):
            antwoord, fout = call_claude(api)
        if fout:
            st.error(fout)
        else:
            st.markdown(antwoord)

    if not fout:
        st.session_state.messages.append({"role": "user", "content": vraag, "bijlagen": namen})
        st.session_state.messages.append({"role": "assistant", "content": antwoord})
        if namen:
            st.session_state.upload_key += 1   # bijlagen leegmaken na versturen
            st.rerun()
