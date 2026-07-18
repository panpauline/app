#!/usr/bin/env python3
"""Ricerca automatica di bandi APERTI per DOCENZE A CONTRATTO e TUTORAGGI
nelle universita' italiane (pubbliche e private), su materie umanistiche
affini al profilo: italiano, latino, filologia, linguistica, didattica,
metodologie didattiche, pedagogia, studi umanistici.

I risultati gia' visti vengono salvati in dati/visti_universita.json. Solo i
risultati NUOVI vengono scritti in nuovi_universita.md, che il workflow usa
per aprire una issue di notifica.
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
except ImportError:  # pragma: no cover
    from duckduckgo_search import DDGS  # type: ignore

# --- Configurazione ----------------------------------------------------------

QUERIES = [
    'bando docenza a contratto italianistica letteratura italiana universita',
    'bando docenza a contratto latino filologia classica universita',
    'bando docenza a contratto linguistica didattica universita',
    'bando docenza a contratto studi umanistici lettere universita',
    'avviso selezione docente a contratto italiano latino universita',
    'bando tutoraggio universita italiano letteratura filologia',
    'bando tutor didattico universita lettere umanistiche',
    'selezione tutor universitario studi umanistici pedagogia didattica',
    'avviso pubblico attivita di tutorato universita italianistica linguistica',
    'bando collaborazione didattica universita lettere filologia',
]

# La figura cercata: docenza a contratto OPPURE tutoraggio universitario.
KW_FIGURA = [
    "docenza a contratto", "docente a contratto", "docenti a contratto",
    "docenze a contratto", "incarico di insegnamento",
    "collaborazione didattica", "affidamento didattico",
    "tutoraggio", "tutorato", "tutor didattico", "tutor universitario",
    "attivita di tutorato", "attivita' di tutorato", "attivita di tutoraggio",
    "supporto didattico",
]

# Deve essere un bando/avviso di selezione.
KW_BANDO = [
    "bando", "avviso", "concorso", "selezione", "manifestazione di interesse",
    "procedura comparativa", "avviso pubblico", "avviso di selezione",
    "call", "reclutamento", "affidamento",
]

# Profilo umanistico: almeno una di queste aree.
KW_PROFILO = [
    "italianistica", "letteratura italiana", "latino", "filologia",
    "linguistica", "italiano", "didattica", "metodologie didattiche",
    "studi umanistici", "scienze umane", "scienze dell'educazione",
    "pedagogi", "lettere", "umanistic", "scienze della formazione",
]

# Indica che il bando e' APERTO (o comunque non chiuso).
KW_APERTO = [
    "aperto", "aperti", "in scadenza", "scadenza", "candidature aperte",
    "termini per la presentazione", "presentazione domanda",
    "domande entro", "entro il", "termine ultimo", "termine di presentazione",
    "in corso", "attivo", "attiva",
]

# Parole che indicano un bando CHIUSO/PASSATO: se compaiono, scarta.
KW_CHIUSO = [
    "graduatoria definitiva", "esito finale", "esiti concorso",
    "bando scaduto", "concorso chiuso", "termini scaduti",
    "graduatoria di merito approvata", "aggiudicazione definitiva",
    "conclusa", "concluso", "esito della selezione",
]

# Domini di news/portali/aggregatori da escludere.
BLOCKLIST = [
    "orizzontescuola.it", "tecnicadellascuola.it", "skuola.net", "studenti.it",
    "tuttoscuola.com", "studentville.it", "wikipedia.org", "uninews24.it",
    "universita.it", "ilfattoquotidiano.it", "repubblica.it", "corriere.it",
    "lastampa.it", "ansa.it", "indeed", "infojobs", "monster.it",
    "linkedin.com", "scuolazoo.com", "miur.gov.it", "mim.gov.it",
    "istruzione.it", "concorsipubblici.com", "profilcultura.it",
    "academicjobsitaly.com", "academia.edu",
]

# Indizi che il dominio appartiene a un'universita' italiana.
UNI_HINTS = [
    "uni",
    "gssi", "sissa", "iuss", "imtlucca", "scuolanormale", "sns.it",
    "santanna", "santannapisa", "iulm", "luiss", "lumsa", "humanitas",
    "bicocca", "vitaesalute", "vita-salute", "polimi", "polito", "polibz",
    "unicatt", "european-university", "europeanuniversity",
    "concorsi", "bandi",
]

MAX_PER_QUERY = 25
RECENZA = "m"

ANNO_MIN = datetime.now(timezone.utc).year - 1
_ANNO_NEL_PATH = re.compile(r"/(20\d{2})/\d{1,2}/")

# --- Percorsi ---------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
DATI_DIR = ROOT / "dati"
STATO_FILE = DATI_DIR / "visti_universita.json"
ARCHIVIO_FILE = DATI_DIR / "risultati_universita.md"
NUOVI_FILE = ROOT / "nuovi_universita.md"


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
    if not any(k in t for k in KW_FIGURA):
        return False
    if not any(k in t for k in KW_BANDO):
        return False
    if not any(k in t for k in KW_PROFILO):
        return False
    # Segnali di bando chiuso -> scarta.
    if any(k in t for k in KW_CHIUSO):
        return False
    # Preferenza per bandi che appaiono APERTI: se non c'e' nessun segnale di
    # apertura, il risultato viene comunque tenuto (perche' la ricerca gia'
    # limita alle pagine indicizzate negli ultimi 30 giorni), ma segnali
    # espliciti di chiusura hanno la precedenza sopra.
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
            f.write("# Archivio docenze a contratto e tutoraggi universita'\n\n")
        f.write(f"## Ricerca del {quando}\n\n")
        for r in nuovi:
            f.write(f"- [{r['titolo']}]({r['url']})\n")
            if r["snippet"]:
                f.write(f"  - {r['snippet']}\n")
        f.write("\n")


def scrivi_notifica(nuovi: list[dict], quando: str) -> None:
    righe = [f"@panpauline — trovati **{len(nuovi)}** nuovi bandi per "
             f"**docenze a contratto / tutoraggi** universita' "
             f"(ricerca del {quando}).", ""]
    for r in nuovi:
        righe.append(f"### [{r['titolo']}]({r['url']})")
        if r["snippet"]:
            righe.append(f"> {r['snippet']}")
        righe.append(f"`query: {r['query']}`")
        righe.append("")
    righe.append("---")
    righe.append("_Ricerca automatica. Verifica sempre la fonte ufficiale "
                 "dell'universita' e che la scadenza sia futura prima di "
                 "candidarti._")
    NUOVI_FILE.write_text("\n".join(righe), encoding="utf-8")


def main() -> int:
    quando = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    visti = carica_stato()
    risultati = cerca()
    nuovi = [r for r in risultati if r["url"] not in visti]
    print(f"Universita' rilevanti: {len(risultati)} | nuovi: {len(nuovi)}")
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
