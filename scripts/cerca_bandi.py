#!/usr/bin/env python3
"""Ricerca automatica di bandi/avvisi per la selezione di FORMATORI.

Cerca su DuckDuckGo (region it-it) bandi pubblicati dalle scuole italiane
collegati all'Avviso prot. n. 95165 del 24/04/2026 (PN Scuola e competenze
2021-2027) e ad avvisi analoghi che selezionano formatori/esperti per la
formazione del personale docente.

I risultati gia' visti vengono salvati in dati/visti.json per non segnalarli
di nuovo. Solo i risultati NUOVI vengono scritti in nuovi_bandi.md, che il
workflow usa per aprire una issue di notifica.
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
    # Pacchetto attuale
    from ddgs import DDGS
except ImportError:  # pragma: no cover - fallback per versioni vecchie
    from duckduckgo_search import DDGS  # type: ignore

# --- Configurazione: modifica qui per affinare la ricerca ---------------------

# Query inviate al motore di ricerca. Privilegiano i portali e gli albi delle
# scuole e gli avvisi di SELEZIONE di formatori/esperti.
QUERIES = [
    'avviso selezione esperti formatori "DM 38/2026" site:edu.it',
    'avviso selezione formatori "PN Scuola e competenze 2021-2027" site:edu.it',
    'bando selezione esperti formatori "DM 38/2026" scuola',
    'avviso selezione esperti formatori "PN Scuola e competenze" formazione docenti site:edu.it',
    'reclutamento esperti formatori "DM 38/2026" "PN Scuola e competenze" site:edu.it',
    'avviso selezione esperti formatori formazione docenti avviso 95165 site:edu.it',
    'albo pretorio avviso selezione formatori "DM 38/2026"',
    'manifestazione di interesse formatori "PN Scuola e competenze" avviso 95165',
    'bando selezione esperto formatore potenziamento competenze docenti site:edu.it',
]

# Numero di protocollo dell'avviso di riferimento (usato come contesto, non basta
# da solo a includere un risultato).
PROTOCOLLO = "95165"

# Domini di news/portali/aziende da ESCLUDERE: non sono bandi delle scuole.
BLOCKLIST = [
    "orizzontescuola.it", "euroedizioni.it", "campustore.it", "deascuola.it",
    "anastasis.it", "qualificagroup.it", "giustoscuola.it", "notiziedellascuola.it",
    "opencup.gov.it", "regione.sicilia.it", "consorzioulisse.net", "formasys.it",
    "sinergiediscuola.it", "elissrl.net", "formatori.eu", "pn20212027.istruzione.it",
    "istruzione.it", "miur.gov.it", "mim.gov.it", "adecco", "indeed", "infojobs",
]

# Indizi che la fonte e' una scuola o un suo albo/amministrazione trasparente.
FONTE_SCUOLA = ["edu.it", "albo", "trasparenza", "amministrazione-trasparente",
                "amministrazionetrasparente", "ckube", "scuolanext", "albopretorio"]

# Parole che indicano una procedura di selezione/reclutamento.
KW_SELEZIONE = ["selezione", "reclutamento", "manifestazione di interesse",
                "procedura comparativa", "avviso pubblico", "avviso di selezione",
                "bando di selezione", "bando", "individuazione", "conferimento incarico",
                "reperimento", "candidatura", "albo"]

# Parole che indicano la figura cercata (formatore/esperto).
KW_FIGURA = ["formator", "esperto", "esperti"]

# --- Filtro geografico: solo Nord e Centro Italia ---------------------------
# Se il titolo/snippet/URL contiene una di queste parole, il risultato viene
# scartato perche' presumibilmente riferito al Sud/Isole.
SUD_KEYWORDS = [
    # Regioni del Sud e Isole
    "campania", "molise", "puglia", "basilicata", "calabria", "sicilia",
    "sardegna", "meridione", "meridionale", "sud italia",
    # Capoluoghi e principali comuni (Campania)
    "napoli", "salerno", "avellino", "benevento", "caserta",
    "torre del greco", "torredelgreco", "pozzuoli", "aversa", "sorrento",
    "capri", "ischia", "eboli", "battipaglia", "nocera", "angri",
    "castellabate", "agropoli", "vallo della lucania", "sapri",
    # Molise
    "campobasso", "isernia", "termoli", "larino", "venafro",
    # Puglia
    "bari", "foggia", "taranto", "brindisi", "lecce", "altamura",
    "barletta", "andria", "trani", "molfetta", "bitonto", "monopoli",
    "cerignola", "san severo", "manfredonia", "martina franca",
    "gallipoli", "otranto", "nardò", "copertino", "galatina",
    # Basilicata
    "potenza", "matera", "melfi", "policoro", "lauria",
    # Calabria
    "cosenza", "catanzaro", "reggio calabria", "crotone", "vibo valentia",
    "lamezia terme", "scalea", "corigliano", "rossano", "paola", "cirò",
    # Sicilia
    "palermo", "catania", "messina", "agrigento", "trapani",
    "caltanissetta", "ragusa", "siracusa", "enna", "linguaglossa",
    "acireale", "marsala", "mazara", "modica", "vittoria", "gela",
    "sciacca", "augusta", "noto", "milazzo", "misiliscemi", "alcamo",
    "favara", "canicattì", "canicatti", "licata",
    # Sardegna
    "cagliari", "sassari", "nuoro", "oristano", "olbia", "alghero",
    "carbonia", "iglesias", "porto torres", "quartu",
]


# Risultati massimi richiesti per ogni query.
MAX_PER_QUERY = 25

# Solo pagine indicizzate di recente: 'd'=giorno, 'w'=settimana, 'm'=mese,
# 'y'=anno, None = nessun limite. "m" tiene gli avvisi pubblicati negli
# ultimi ~30 giorni: tipicamente ancora aperti.
RECENZA = "m"

# Scarta URL il cui percorso contiene un anno piu' vecchio di questo. Tiene
# l'anno corrente e quello precedente (alcuni bandi a cavallo restano aperti).
ANNO_MIN = datetime.now(timezone.utc).year - 1
_ANNO_NEL_PATH = re.compile(r"/(20\d{2})/\d{1,2}/")

# --- Percorsi -----------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
DATI_DIR = ROOT / "dati"
STATO_FILE = DATI_DIR / "visti.json"
ARCHIVIO_FILE = DATI_DIR / "risultati.md"
NUOVI_FILE = ROOT / "nuovi_bandi.md"


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
    # Toglie eventuale frammento e slash finale per deduplicare meglio.
    url = url.split("#", 1)[0]
    return url.rstrip("/")


def dominio(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def fonte_scuola(url: str) -> bool:
    """True se l'URL e' di una scuola o di un suo albo/trasparenza, escludendo
    i portali/news della blocklist."""
    dom = dominio(url)
    if not dom or any(b in dom for b in BLOCKLIST):
        return False
    u = url.lower()
    return dom.endswith(".edu.it") or any(h in u for h in FONTE_SCUOLA)


def url_troppo_vecchio(url: str) -> bool:
    m = _ANNO_NEL_PATH.search(url)
    return bool(m) and int(m.group(1)) < ANNO_MIN


def e_sud(testo: str, url: str) -> bool:
    """True se il testo/URL contiene un riferimento chiaro al Sud o Isole."""
    t = f"{testo} {url}".lower()
    return any(k in t for k in SUD_KEYWORDS)


def e_rilevante(testo: str, url: str) -> bool:
    # Solo portali/albi delle scuole.
    if not fonte_scuola(url):
        return False
    # Scarta i bandi chiaramente vecchi (anno nel percorso URL).
    if url_troppo_vecchio(url):
        return False
    # Solo Nord + Centro Italia: scarta le scuole del Sud/Isole.
    if e_sud(testo, url):
        return False
    t = f"{testo} {url}".lower()
    ha_figura = any(k in t for k in KW_FIGURA)
    ha_selezione = any(k in t for k in KW_SELEZIONE)
    # Deve essere un avviso di selezione/reclutamento che riguarda formatori/esperti.
    return ha_figura and ha_selezione


def cerca() -> list[dict]:
    trovati: dict[str, dict] = {}
    with DDGS() as ddgs:
        for q in QUERIES:
            try:
                risultati = ddgs.text(q, region="it-it", safesearch="off",
                                      max_results=MAX_PER_QUERY,
                                      timelimit=RECENZA)
            except Exception as exc:  # rete/rate limit: prosegui con le altre query
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
                # Tieni la prima occorrenza (le query piu' specifiche vengono prima).
                trovati.setdefault(url, {
                    "url": url,
                    "titolo": titolo or url,
                    "snippet": snippet,
                    "query": q,
                })
            time.sleep(2)  # gentile col motore di ricerca
    return list(trovati.values())


def scrivi_archivio(nuovi: list[dict], quando: str) -> None:
    DATI_DIR.mkdir(parents=True, exist_ok=True)
    nuovo_file = not ARCHIVIO_FILE.exists()
    with ARCHIVIO_FILE.open("a", encoding="utf-8") as f:
        if nuovo_file:
            f.write("# Archivio bandi formatori trovati\n\n")
        f.write(f"## Ricerca del {quando}\n\n")
        for r in nuovi:
            f.write(f"- [{r['titolo']}]({r['url']})\n")
            if r["snippet"]:
                f.write(f"  - {r['snippet']}\n")
        f.write("\n")


def scrivi_notifica(nuovi: list[dict], quando: str) -> None:
    righe = [f"@panpauline — trovati **{len(nuovi)}** nuovi bandi/avvisi per "
             f"formatori (ricerca del {quando}).", ""]
    for r in nuovi:
        righe.append(f"### [{r['titolo']}]({r['url']})")
        if r["snippet"]:
            righe.append(f"> {r['snippet']}")
        righe.append(f"`query: {r['query']}`")
        righe.append("")
    righe.append("---")
    righe.append("_Ricerca automatica. Verifica sempre la fonte ufficiale "
                 "della scuola prima di candidarti._")
    NUOVI_FILE.write_text("\n".join(righe), encoding="utf-8")


def main() -> int:
    quando = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    visti = carica_stato()

    risultati = cerca()
    nuovi = [r for r in risultati if r["url"] not in visti]

    print(f"Risultati rilevanti: {len(risultati)} | nuovi: {len(nuovi)}")

    if nuovi:
        scrivi_archivio(nuovi, quando)
        scrivi_notifica(nuovi, quando)
        visti.update(r["url"] for r in nuovi)
        salva_stato(visti)
    else:
        # Nessun nuovo bando: assicurati che non resti un vecchio file di notifica.
        if NUOVI_FILE.exists():
            NUOVI_FILE.unlink()
        # Salva comunque lo stato (crea il file alla prima esecuzione).
        salva_stato(visti)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
