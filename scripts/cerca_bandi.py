#!/usr/bin/env python3
"""Ricerca automatica di bandi/avvisi APERTI per la selezione di ESPERTI
FORMATORI di docenti nelle scuole della TOSCANA.

Cerca su DuckDuckGo (region it-it) avvisi pubblicati dalle scuole toscane
(DM 38, PN Scuola e competenze 2021-2027, PNRR/Scuola Futura, PR FSE+
Regione Toscana) che selezionano formatori/esperti per la formazione del
personale docente.

REGOLE (vedi istruzioni del progetto):
- SOLO Toscana: ricerca capillare per provincia; i risultati riferiti ad
  altre regioni vengono scartati; quelli senza indicazione geografica
  esplicita vengono segnalati con un avviso di verifica.
- SOLO avvisi a cui ci si puo' ancora candidare: graduatorie, esiti,
  decreti di individuazione/approvazione atti e nomine vengono scartati.
- Se nel testo compare una data di scadenza gia' passata, il risultato
  viene scartato.

I risultati gia' visti vengono salvati in dati/visti.json per non
segnalarli di nuovo. Solo i risultati NUOVI vengono scritti in
nuovi_bandi.md, che il workflow usa per aprire una issue di notifica.
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

try:
    from ddgs import DDGS
except ImportError:  # pragma: no cover - fallback per versioni vecchie
    from duckduckgo_search import DDGS  # type: ignore

# --- Configurazione: modifica qui per affinare la ricerca ---------------------

# Province toscane: usate per generare le query capillari.
PROVINCE_TOSCANA = [
    "Pisa", "Firenze", "Livorno", "Lucca", "Pistoia", "Prato",
    "Arezzo", "Siena", "Grosseto", "Massa-Carrara",
]

# Query capillari per provincia + query tematiche regionali.
QUERIES = [
    f'"avviso di selezione" "esperto formatore" site:edu.it {p}'
    for p in PROVINCE_TOSCANA
] + [
    f'avviso selezione esperti formatori docenti site:edu.it {p}'
    for p in ("Pisa", "Firenze", "Livorno", "Lucca")
] + [
    'avviso selezione esperti formatori "DM 38" site:edu.it Toscana',
    'avviso selezione formatori "PN Scuola e competenze 2021-2027" site:edu.it Toscana',
    'avviso selezione esperti formatori formazione docenti PNRR "scuola futura" Toscana',
    'avviso selezione esperto formatore docenti FSE+ Regione Toscana',
    'manifestazione di interesse formatori formazione docenti Toscana site:edu.it',
]

# Domini di news/portali/aziende da ESCLUDERE: non sono bandi delle scuole.
BLOCKLIST = [
    "orizzontescuola.it", "euroedizioni.it", "campustore.it", "deascuola.it",
    "anastasis.it", "qualificagroup.it", "giustoscuola.it", "notiziedellascuola.it",
    "opencup.gov.it", "consorzioulisse.net", "formasys.it",
    "sinergiediscuola.it", "elissrl.net", "formatori.eu", "pn20212027.istruzione.it",
    "istruzione.it", "miur.gov.it", "mim.gov.it", "adecco", "indeed", "infojobs",
    "tecnicadellascuola.it", "tuttoscuola.com",
]

# Indizi che la fonte e' una scuola o un suo albo/amministrazione trasparente.
FONTE_SCUOLA = ["edu.it", "albo", "trasparenza", "amministrazione-trasparente",
                "amministrazionetrasparente", "ckube", "scuolanext", "albopretorio"]

# Parole che indicano una procedura di selezione ANCORA CANDIDABILE.
# NB: rimossi "individuazione" e "conferimento incarico" (sono esiti).
KW_SELEZIONE = ["selezione", "reclutamento", "manifestazione di interesse",
                "procedura comparativa", "avviso pubblico", "avviso di selezione",
                "bando di selezione", "bando", "reperimento", "candidatur"]

# Parole che indicano la figura cercata (formatore/esperto).
KW_FIGURA = ["formator", "esperto", "esperti"]

# --- Esclusione di graduatorie, esiti e atti di selezioni concluse -----------
# Se una di queste espressioni compare nel titolo/snippet/URL, il risultato
# NON e' un avviso candidabile e viene scartato.
KW_ESITI = [
    "graduatoria", "graduatorie", "esito", "esiti",
    "vincitor", "idonei",
    "approvazione atti", "approvazione degli atti", "decreto di approvazione",
    "atti della selezione", "risultati selezion", "risultati della selezione",
    "decreto di individuazione", "determina di individuazione",
    "individuato quale", "individuati quali", "si e' provveduto all'individuazione",
    "verbale", "nomina", "aggiudicazione", "scorrimento",
    "pubblicazione graduatoria", "conferimento incarico a",
    "determina di affidamento", "bando scaduto", "termini scaduti",
]

# Avvisi rivolti ad ALUNNI/STUDENTI (es. esperti per corsi PON studenti):
# non riguardano la formazione dei docenti, quindi vengono scartati.
KW_TARGET_ALUNNI = [
    "rivolto agli alunni", "rivolti agli alunni", "per gli alunni",
    "destinatari: alunni", "alunni delle classi",
    "rivolto agli studenti", "rivolti agli studenti", "per gli studenti",
    "destinatari: studenti",
]

# --- Filtro geografico: SOLO TOSCANA -----------------------------------------
# Whitelist: se il testo/URL contiene uno di questi riferimenti, il risultato
# e' considerato toscano.
TOSCANA_KW = [
    "toscana", "usr toscana",
    # Capoluoghi e province
    "pisa", "firenze", "livorno", "lucca", "pistoia", "prato",
    "arezzo", "siena", "grosseto", "massa-carrara", "massa carrara", "carrara",
    # Comuni con istituti scolastici (elenco capillare, ampliabile)
    "empoli", "pontedera", "cascina", "san miniato", "santa croce sull'arno",
    "castelfranco di sotto", "volterra", "pomarance", "san giuliano terme",
    "cecina", "rosignano", "piombino", "portoferraio", "venturina",
    "viareggio", "camaiore", "pietrasanta", "capannori", "altopascio",
    "barga", "castelnuovo di garfagnana", "seravezza",
    "montecatini", "monsummano", "quarrata", "agliana", "pescia",
    "scandicci", "sesto fiorentino", "campi bisenzio", "lastra a signa",
    "signa", "bagno a ripoli", "pontassieve", "borgo san lorenzo",
    "figline", "incisa", "certaldo", "castelfiorentino", "fucecchio",
    "poggibonsi", "colle di val d'elsa", "montepulciano", "chiusi",
    "sinalunga", "chianciano", "cortona", "montevarchi",
    "san giovanni valdarno", "terranuova", "bibbiena", "poppi",
    "sansepolcro", "castiglion fiorentino", "follonica", "orbetello",
    "massa marittima", "gavorrano", "manciano", "pitigliano",
    "aulla", "pontremoli", "fivizzano",
]

# Sigle provincia tra parentesi, tipiche dei nomi di istituto: "(PI)", "(FI)"...
_SIGLA_TOSCANA = re.compile(r"\((pi|fi|li|lu|pt|po|ar|si|gr|ms)\)", re.I)

# Blocklist: riferimenti chiari ad ALTRE regioni/citta' -> scarta.
ALTRE_REGIONI_KW = [
    # Regioni non toscane
    "piemonte", "lombardia", "veneto", "liguria", "friuli", "trentino",
    "alto adige", "emilia", "romagna", "marche", "umbria", "lazio",
    "abruzzo", "campania", "molise", "puglia", "basilicata", "calabria",
    "sicilia", "sardegna", "valle d'aosta",
    # Citta' principali non toscane (Nord e Centro)
    "milano", "torino", "genova", "bologna", "modena", "parma",
    "reggio emilia", "ferrara", "ravenna", "rimini", "forlì", "cesena",
    "piacenza", "venezia", "padova", "verona", "vicenza", "treviso",
    "rovigo", "belluno", "brescia", "bergamo", "monza", "como", "varese",
    "pavia", "cremona", "mantova", "lodi", "lecco", "sondrio",
    "trieste", "udine", "pordenone", "gorizia", "trento", "bolzano",
    "aosta", "novara", "alessandria", "asti", "cuneo", "vercelli",
    "biella", "verbania", "la spezia", "savona", "imperia",
    "roma", "latina", "frosinone", "viterbo", "rieti",
    "perugia", "terni", "ancona", "pesaro", "urbino", "macerata",
    "ascoli", "fermo", "l'aquila", "pescara", "chieti", "teramo",
    # Sud e Isole (citta')
    "napoli", "salerno", "avellino", "benevento", "caserta",
    "campobasso", "isernia", "bari", "foggia", "taranto", "brindisi",
    "lecce", "barletta", "andria", "trani", "potenza", "matera",
    "cosenza", "catanzaro", "reggio calabria", "crotone", "vibo valentia",
    "palermo", "catania", "messina", "agrigento", "trapani",
    "caltanissetta", "ragusa", "siracusa", "enna",
    "cagliari", "sassari", "nuoro", "oristano", "olbia",
]


def geo_toscana(testo: str, url: str) -> str:
    """Ritorna 'si' se il risultato e' chiaramente toscano, 'no' se e'
    chiaramente di un'altra regione, '?' se non ci sono indicazioni."""
    t = f"{testo} {url}".lower()
    if any(k in t for k in ALTRE_REGIONI_KW):
        return "no"
    if any(k in t for k in TOSCANA_KW) or _SIGLA_TOSCANA.search(t):
        return "si"
    return "?"


# --- Filtro sulla data di scadenza -------------------------------------------

_MESI = {"gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5,
         "giugno": 6, "luglio": 7, "agosto": 8, "settembre": 9,
         "ottobre": 10, "novembre": 11, "dicembre": 12}

_SCAD_NUM = re.compile(
    r"(?:scadenza|entro(?:\s+il)?|termine(?:\s+ultimo)?(?:\s+di\s+presentazione)?)"
    r"[^\d]{0,40}(\d{1,2})[\/\.\-](\d{1,2})[\/\.\-](20\d{2})", re.I)
_SCAD_TXT = re.compile(
    r"(?:scadenza|entro(?:\s+il)?|termine)"
    r"[^\d]{0,40}(\d{1,2})\u00b0?\s+"
    r"(gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|"
    r"ottobre|novembre|dicembre)\s+(20\d{2})", re.I)


def scadenza_passata(testo: str) -> bool:
    """True se nel testo compare una data di scadenza gia' trascorsa."""
    oggi = datetime.now(timezone.utc).date()
    t = testo.lower()
    for m in _SCAD_NUM.finditer(t):
        try:
            g, me, a = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if date(a, me, g) < oggi:
                return True
        except ValueError:
            continue
    for m in _SCAD_TXT.finditer(t):
        try:
            g, a = int(m.group(1)), int(m.group(3))
            me = _MESI[m.group(2)]
            if date(a, me, g) < oggi:
                return True
        except (ValueError, KeyError):
            continue
    return False


# Risultati massimi richiesti per ogni query.
MAX_PER_QUERY = 20

# Solo pagine indicizzate di recente: 'm' = ultimo mese.
RECENZA = "m"

# Scarta URL il cui percorso contiene un anno piu' vecchio di questo.
ANNO_MIN = datetime.now(timezone.utc).year - 1
_ANNO_NEL_PATH = re.compile(r"/(20\d{2})/\d{1,2}/")
# Anno scolastico/accademico nel testo o nell'URL: "a.s. 2024/2025", "a.s. 2024-25".
_AS_RE = re.compile(r"a[\.\-\s]?[as][\.\-\s]*(20\d{2})\s*[/\-\u2013]\s*(?:20)?\d{2}", re.I)


def anno_scolastico_vecchio(testo: str) -> bool:
    """True se il testo/URL cita un anno scolastico chiaramente passato."""
    return any(int(m.group(1)) < ANNO_MIN for m in _AS_RE.finditer(testo))

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
    url = url.split("#", 1)[0]
    return url.rstrip("/")


def dominio(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def fonte_scuola(url: str) -> bool:
    dom = dominio(url)
    if not dom or any(b in dom for b in BLOCKLIST):
        return False
    u = url.lower()
    return dom.endswith(".edu.it") or any(h in u for h in FONTE_SCUOLA)


def url_troppo_vecchio(url: str) -> bool:
    m = _ANNO_NEL_PATH.search(url)
    return bool(m) and int(m.group(1)) < ANNO_MIN


def e_rilevante(testo: str, url: str) -> bool:
    """True se il risultato e' un avviso di selezione per formatori di docenti,
    candidabile e non riconducibile a esiti/graduatorie."""
    if not fonte_scuola(url):
        return False
    if url_troppo_vecchio(url):
        return False
    t = f"{testo} {url}".lower()
    # Esiti/graduatorie/nomine -> non candidabile, scarta.
    if any(k in t for k in KW_ESITI):
        return False
    # Avvisi rivolti ad alunni/studenti -> non e' formazione docenti, scarta.
    if any(k in t for k in KW_TARGET_ALUNNI):
        return False
    # Data di scadenza gia' passata nel testo -> scarta.
    if scadenza_passata(t) or anno_scolastico_vecchio(t):
        return False
    ha_figura = any(k in t for k in KW_FIGURA)
    ha_selezione = any(k in t for k in KW_SELEZIONE)
    return ha_figura and ha_selezione


def cerca() -> list[dict]:
    trovati: dict[str, dict] = {}
    with DDGS() as ddgs:
        for q in QUERIES:
            try:
                risultati = ddgs.text(q, region="it-it", safesearch="off",
                                      max_results=MAX_PER_QUERY,
                                      timelimit=RECENZA)
            except Exception as exc:  # rete/rate limit: prosegui con le altre
                print(f"[warn] query fallita: {q!r} -> {exc}", file=sys.stderr)
                time.sleep(3)
                continue
            for r in risultati or []:
                url = normalizza_url(r.get("href") or r.get("url") or "")
                if not url:
                    continue
                titolo = (r.get("title") or "").strip()
                snippet = (r.get("body") or "").strip()
                testo = f"{titolo} {snippet}"
                if not e_rilevante(testo, url):
                    continue
                geo = geo_toscana(testo, url)
                if geo == "no":
                    continue  # altra regione: fuori ambito
                trovati.setdefault(url, {
                    "url": url,
                    "titolo": titolo or url,
                    "snippet": snippet,
                    "query": q,
                    "geo": geo,  # 'si' oppure '?'
                })
            time.sleep(2)  # gentile col motore di ricerca
    return list(trovati.values())


def scrivi_archivio(nuovi: list[dict], quando: str) -> None:
    DATI_DIR.mkdir(parents=True, exist_ok=True)
    nuovo_file = not ARCHIVIO_FILE.exists()
    with ARCHIVIO_FILE.open("a", encoding="utf-8") as f:
        if nuovo_file:
            f.write("# Archivio bandi formatori trovati (Toscana)\n\n")
        f.write(f"## Ricerca del {quando}\n\n")
        for r in nuovi:
            flag = "" if r.get("geo") == "si" else " \u26a0\ufe0f localita' da verificare"
            f.write(f"- [{r['titolo']}]({r['url']}){flag}\n")
            if r["snippet"]:
                f.write(f"  - {r['snippet']}\n")
        f.write("\n")


def scrivi_notifica(nuovi: list[dict], quando: str) -> None:
    certi = [r for r in nuovi if r.get("geo") == "si"]
    incerti = [r for r in nuovi if r.get("geo") != "si"]
    righe = [f"@panpauline \u2014 trovati **{len(nuovi)}** nuovi avvisi per "
             f"**esperti formatori** in Toscana (ricerca del {quando}).",
             "Solo avvisi candidabili: graduatorie ed esiti sono esclusi.", ""]
    for r in certi:
        righe.append(f"### [{r['titolo']}]({r['url']})")
        if r["snippet"]:
            righe.append(f"> {r['snippet']}")
        righe.append(f"`query: {r['query']}`")
        righe.append("")
    if incerti:
        righe.append("---")
        righe.append("#### \u26a0\ufe0f Localita' non esplicita nel testo "
                     "(verificare che la scuola sia in Toscana):")
        righe.append("")
        for r in incerti:
            righe.append(f"### [{r['titolo']}]({r['url']})")
            if r["snippet"]:
                righe.append(f"> {r['snippet']}")
            righe.append(f"`query: {r['query']}`")
            righe.append("")
    righe.append("---")
    righe.append("_Ricerca automatica limitata alla Toscana. Verifica sempre "
                 "la fonte ufficiale della scuola e la scadenza prima di "
                 "candidarti._")
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
        if NUOVI_FILE.exists():
            NUOVI_FILE.unlink()
        salva_stato(visti)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
