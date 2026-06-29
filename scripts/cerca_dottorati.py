#!/usr/bin/env python3
"""Ricerca automatica di bandi di DOTTORATO di ricerca su materie umanistiche
(italiano, latino, letteratura, linguistica, didattica innovativa, pedagogia)
presso le universita' italiane, pubbliche e private.

I risultati gia' visti vengono salvati in dati/visti_dottorati.json. Solo i
risultati NUOVI vengono scritti in nuovi_dottorati.md, che il workflow usa per
aprire una issue di notifica.
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

try:
    from ddgs import DDGS
except ImportError:  # pragma: no cover - fallback per versioni vecchie
    from duckduckgo_search import DDGS  # type: ignore

# --- Configurazione: modifica qui per affinare la ricerca ---------------------

QUERIES = [
    'bando dottorato di ricerca italianistica letteratura italiana',
    'bando dottorato di ricerca filologia classica latino',
    'bando dottorato di ricerca linguistica didattica delle lingue',
    'bando dottorato di ricerca studi umanistici lettere',
    'bando dottorato di ricerca scienze pedagogiche pedagogia',
    'bando dottorato di ricerca didattica metodologie innovative',
    'concorso ammissione dottorato di ricerca lettere umanistico',
    'bando dottorato 41 ciclo umanistico italianistica',
    'bando dottorato 42 ciclo lettere filologia',
    'bando dottorato innovativo metodologie didattiche scuola',
]

# Profilo: deve emergere almeno una di queste aree.
KW_PROFILO = [
    "italianistica", "letteratura italiana", "latino", "filologia",
    "linguistica", "italiano", "didattica", "metodologie didattiche",
    "studi umanistici", "scienze umane", "scienze dell'educazione",
    "pedagogi", "lettere", "umanistic", "filosofi", "scienze della formazione",
]

# Deve riguardare un dottorato.
KW_DOTTORATO = ["dottorato", "phd", "ph.d", "doctorate"]

# Deve essere un bando/concorso/avviso pubblico.
KW_BANDO = ["bando", "concorso", "ammissione", "selezione", "avviso pubblico",
            "avviso di selezione", "call"]

# Domini di news/portali da escludere (NON sono bandi delle universita').
BLOCKLIST = [
    "orizzontescuola.it", "tecnicadellascuola.it", "skuola.net", "studenti.it",
    "tuttoscuola.com", "studentville.it", "wikipedia.org", "uninews24.it",
    "universita.it", "ilfattoquotidiano.it", "repubblica.it", "corriere.it",
    "lastampa.it", "ansa.it", "indeed", "infojobs", "monster.it", "linkedin.com",
    "scuolazoo.com", "miur.gov.it", "mim.gov.it", "istruzione.it",
]

# Indizi che il dominio appartiene a un'universita' italiana.
UNI_HINTS = [
    # pattern generico "uni"
    "uni",
    # scuole superiori e universita' private
    "gssi", "sissa", "iuss", "imtlucca", "scuolanormale", "sns.it",
    "santanna", "santannapisa", "iulm", "luiss", "lumsa", "humanitas",
    "bicocca", "vitaesalute", "vita-salute", "polimi", "polito", "polibz",
    "unicatt", "european-university", "europeanuniversity",
    # parole chiave nel path
    "dottorato", "phd", "doctoral", "phdschool", "scuoladidottorato",
]

MAX_PER_QUERY = 25

# Solo pagine indicizzate negli ultimi ~30 giorni: bandi tipicamente ancora aperti.
RECENZA = "m"

# Scarta URL con anno nel path piu' vecchio dell'anno scorso.
ANNO_MIN = datetime.now(timezone.utc).year - 1
_ANNO_NEL_PATH = re.compile(r"/(20\d{2})/\d{1,2}/")

# --- Percorsi -----------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
DATI_DIR = ROOT / "dati"
STATO_FILE = DATI_DIR / "visti_dottorati.json"
ARCHIVIO_FILE = DATI_DIR / "risultati_dottorati.md"
NUOVI_FILE = ROOT / "nuovi_dottorati.md"


def carica_stato() -> set[str]:
    if STATO_FILE.exists():
        data = json.loads(STATO_FILE.read_text(encoding="utf-8"))
        return set(data.get("urls", []))
    return set()


def salva_stato(urls: set[str]) -> None:
    DATI_DIR.mkdir(parents=True, exist_ok=True)
    STATO_FILE.write_text(
        json.dumps({"urls": sorted(urls)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def normalizza_url(url: str) -> str:
    return url.split("#", 1)[0].rstrip("/")


def dominio(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def url_troppo_vecchio(url: str) -> bool:
    m = _ANNO_NEL_PATH.search(url)
    return bool(m) and int(m.group(1)) < ANNO_MIN


def fonte_universita(url: str) -> bool:
    """True se l'URL e' di un sito universitario o di scuola di dottorato,
    escludendo i portali/news della blocklist."""
    dom = dominio(url)
    if not dom or any(b in dom for b in BLOCKLIST):
        return False
    u = url.lower()
    return any(h in dom for h in UNI_HINTS) or any(h in u for h in UNI_HINTS)


def e_rilevante(testo: str, url: str) -> bool:
    if not fonte_universita(url):
        return False
    if url_troppo_vecchio(url):
        return False
    t = f"{testo} {url}".lower()
    if not any(k in t for k in KW_DOTTORATO):
        return False
    if not any(k in t for k in KW_BANDO):
        return False
    if not any(k in t for k in KW_PROFILO):
        return False
    return True


def cerca() -> list[dict]:
    trovati: dict[str, dict] = {}
    with DDGS() as ddgs:
        for q in QUERIES:
            try:
                risultati = ddgs.text(q, region="it-it", safesearch="off",
                                      max_results=MAX_PER_QUERY,
                                      timelimit=RECENZA)
            except Exception as exc:
                print(f"[warn] query fallita: {q!r} -> {exc}", file=sys.stderr)
                time.sleep(3)
                continue
            for r in risultati or []:
                url = normalizza_url(r.get("href") or r.get("url") or "")
                if not url:
                    continue
                titolo = (r.get("title") or "").strip()
                snippet = (r.get("body") or "").strip()
                if not e_rilevante(f"{titolo} {snippet}", url):
                    continue
                trovati.setdefault(url, {
                    "url": url,
                    "titolo": titolo or url,
                    "snippet": snippet,
                    "query": q,
                })
            time.sleep(2)
    return list(trovati.values())


def scrivi_archivio(nuovi: list[dict], quando: str) -> None:
    DATI_DIR.mkdir(parents=True, exist_ok=True)
    nuovo_file = not ARCHIVIO_FILE.exists()
    with ARCHIVIO_FILE.open("a", encoding="utf-8") as f:
        if nuovo_file:
            f.write("# Archivio bandi di dottorato umanistico trovati\n\n")
        f.write(f"## Ricerca del {quando}\n\n")
        for r in nuovi:
            f.write(f"- [{r['titolo']}]({r['url']})\n")
            if r["snippet"]:
                f.write(f"  - {r['snippet']}\n")
        f.write("\n")


def scrivi_notifica(nuovi: list[dict], quando: str) -> None:
    righe = [f"@panpauline — trovati **{len(nuovi)}** nuovi bandi di "
             f"**dottorato** umanistico (ricerca del {quando}).", ""]
    for r in nuovi:
        righe.append(f"### [{r['titolo']}]({r['url']})")
        if r["snippet"]:
            righe.append(f"> {r['snippet']}")
        righe.append(f"`query: {r['query']}`")
        righe.append("")
    righe.append("---")
    righe.append("_Ricerca automatica. Verifica sempre la fonte ufficiale "
                 "dell'universita' e la data di scadenza prima di candidarti._")
    NUOVI_FILE.write_text("\n".join(righe), encoding="utf-8")


def main() -> int:
    quando = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    visti = carica_stato()

    risultati = cerca()
    nuovi = [r for r in risultati if r["url"] not in visti]

    print(f"Dottorati rilevanti: {len(risultati)} | nuovi: {len(nuovi)}")

    if nuovi:
        scrivi_archivio(nuovi, quando)
        scrivi_notifica(nuovi, quando)
        visti.update(r["url"] for r in nuovi)
        salva_stato(visti)
    else:
        if NUOVI_FILE.exists():
            NUOVI_FILE.unlink()
        salva_stato(visti)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
