"""Automatische controle van een project (draait in GitHub Actions).

LEERMODUS - wat doet dit script?
Het is een "robot-controleur" die na elke wijziging (push) nakijkt of het
project nog in orde is. Vindt hij een probleem, dan wordt de controle rood
in GitHub en krijg je een mail. Zo zie je fouten voordat gebruikers ze zien.

Wat er gecontroleerd wordt (alleen wat in dit project voorkomt):
  1. JavaScript-bestanden: geen tikfouten in de code (node --check).
  2. JSON en manifesten: geldig en leesbaar.
  3. Installeerbare app (PWA): eigen id/scope en eigen cache-voorvoegsel,
     volgens de afspraken van vandaag (zie de skill github-pages-pwa).
  4. HTML: bestaan de bestanden waar de pagina naar verwijst?
  5. Python: geen tikfouten (py_compile).
Met --live wordt bovendien de website zelf opgevraagd.

Uitvoer: een rapport in de GitHub-samenvatting. Exitcode 1 = probleem.
"""
import json
import os
import pathlib
import py_compile
import re
import subprocess
import sys
import urllib.parse
import urllib.request

ROOT = pathlib.Path(".")
REPO = os.environ.get("GITHUB_REPOSITORY", "lokaal/" + ROOT.resolve().name).split("/")[1]
OVERSLAAN = {".git", "node_modules", "__pycache__", ".venv", "venv", ".devcontainer", ".vscode"}
fouten, waarschuwingen, ok = [], [], []


def bestanden(*ext):
    for p in ROOT.rglob("*"):
        if p.is_file() and p.suffix.lower() in ext and not (set(p.parts) & OVERSLAAN):
            yield p


def check_js():
    n = 0
    for p in bestanden(".js"):
        if ".github" in p.parts:
            continue
        r = subprocess.run(["node", "--check", str(p)], capture_output=True, text=True)
        n += 1
        if r.returncode:
            regels = r.stderr.strip().splitlines()
            melding = next((l for l in regels if "Error" in l), regels[0] if regels else "onbekend")
            plek = next((l for l in regels if l.startswith(str(p))), "")
            fouten.append(f"JavaScript-fout in `{p}`: {melding.strip()} {('(' + plek.split(':')[-1] + ')') if plek else ''}".strip())
    if n:
        ok.append(f"{n} JavaScript-bestand(en) gecontroleerd")


def check_json():
    n = 0
    for p in list(bestanden(".json", ".webmanifest")):
        if p.parts[0] == "data" and p.stat().st_size > 2_000_000:
            continue
        try:
            json.loads(p.read_text(encoding="utf-8"))
            n += 1
        except Exception as e:
            fouten.append(f"Ongeldige JSON in `{p}`: {e}")
    if n:
        ok.append(f"{n} JSON-bestand(en) geldig")


def check_pwa():
    manifesten = [p for p in ROOT.glob("manifest*.json")] + list(ROOT.glob("*.webmanifest"))
    pad = f"/{REPO}/"
    for p in manifesten:
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        for veld in ("id", "scope", "start_url"):
            waarde = m.get(veld)
            if waarde is None:
                fouten.append(f"`{p}` mist `{veld}` (moet `{pad}` zijn, anders botst de app met je andere apps)")
            elif waarde == "/":
                fouten.append(f"`{p}`: `{veld}` is `/` en claimt al je apps op ron78nl.github.io. Gebruik `{pad}`")
            elif waarde.lower() != pad.lower() and not waarde.startswith("./"):
                waarschuwingen.append(f"`{p}`: `{veld}` is `{waarde}`, verwacht `{pad}`")
        if not m.get("short_name"):
            waarschuwingen.append(f"`{p}` heeft geen `short_name` (naam onder het icoon)")
        for icoon in m.get("icons", []):
            if not (p.parent / icoon.get("src", "")).exists():
                fouten.append(f"`{p}` verwijst naar ontbrekend icoon `{icoon.get('src')}`")
    for sw in ROOT.glob("sw.js"):
        tekst = sw.read_text(encoding="utf-8")
        if "caches.delete" in tekst and "startsWith(" not in tekst:
            fouten.append("`sw.js` wist caches zonder eigen voorvoegsel: dat sloopt de opslag van je andere apps")
    if manifesten:
        ok.append("Installeerbare-app-regels gecontroleerd")


VERWIJZING = re.compile(r'(?:src|href)="([^"#?]+)')


def check_html():
    n = 0
    for p in bestanden(".html"):
        if "backup" in p.name:
            continue
        for ref in VERWIJZING.findall(p.read_text(encoding="utf-8", errors="ignore")):
            if re.match(r"^(https?:|data:|mailto:|tel:|javascript:|//|\$|\{)", ref) or ref.startswith("/"):
                continue
            doel = (p.parent / urllib.parse.unquote(ref)).resolve()
            if ref.endswith("/"):
                doel = doel / "index.html"
            if not doel.exists():
                fouten.append(f"`{p}` verwijst naar `{ref}`, maar dat bestand bestaat niet")
        n += 1
    if n:
        ok.append(f"{n} HTML-pagina('s): verwijzingen gecontroleerd")


def check_python():
    n = 0
    for p in bestanden(".py"):
        try:
            py_compile.compile(str(p), doraise=True)
            n += 1
        except py_compile.PyCompileError as e:
            fouten.append(f"Python-fout in `{p}`: {e.msg.strip().splitlines()[-1]}")
    if n:
        ok.append(f"{n} Python-bestand(en) zonder tikfouten")


def check_live():
    url = os.environ.get("SITE_URL")
    if not url:
        ok.append("Geen GitHub Pages-site: live controle overgeslagen")
        return
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "controle-robot"}), timeout=30) as r:
            if r.status != 200:
                fouten.append(f"Website {url} geeft status {r.status}")
            else:
                ok.append(f"Website online: {url}")
    except Exception as e:
        fouten.append(f"Website {url} niet bereikbaar: {e}")
    for m in ("manifest.json", "manifest.webmanifest"):
        if (ROOT / m).exists():
            try:
                with urllib.request.urlopen(url.rstrip("/") + "/" + m, timeout=30) as r:
                    json.loads(r.read())
                ok.append(f"Live manifest leesbaar ({m})")
            except Exception as e:
                fouten.append(f"Live manifest {m} niet leesbaar: {e}")
            break


def main():
    check_js(); check_json(); check_pwa(); check_html(); check_python()
    if "--live" in sys.argv:
        check_live()
    fouten[:] = list(dict.fromkeys(fouten))
    regels = [f"## Controle {REPO}", ""]
    regels += [f"- :x: {f}" for f in fouten]
    regels += [f"- :warning: {w}" for w in waarschuwingen]
    regels += [f"- :white_check_mark: {o}" for o in ok]
    if not fouten:
        regels += ["", "**Alles in orde.**"]
    rapport = "\n".join(regels)
    print(rapport)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(rapport + "\n")
    sys.exit(1 if fouten else 0)


if __name__ == "__main__":
    main()
