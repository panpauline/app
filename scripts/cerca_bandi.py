#!/usr/bin/env python3
"""Ricerca automatica di avvisi APERTI per la selezione di ESPERTI FORMATORI
di docenti nelle scuole della TOSCANA.

Cerca su DuckDuckGo (region it-it) avvisi pubblicati dalle scuole toscane
(DM 38, PN Scuola e competenze 2021-2027, PNRR/Scuola Futura, PR FSE+
Regione Toscana) che selezionano formatori/esperti per la formazione del
personale docente.

REGOLE (vedi istruzioni del progetto):
- SOLO Toscana, accertata. Se titolo/snippet/URL non bastano a stabilire la
  localita', lo script legge la pagina dell'avviso (e, se serve, la home del
  sito della scuola) e cerca il CAP toscano (50000-59999), il codice
  meccanografico (inizia con la sigla della provincia: PI, FI, LI, LU, PT,
  PO, AR, SI, GR, MS) o la sigla tra parentesi. Se la Toscana non e'
  accertata, il risultato viene SCARTATO.
- SOLO avvisi candidabili: graduatorie, esiti, decisioni/determine a
  contrarre, individuazioni, nomine, annullamenti e selezioni riservate al
  solo personale interno vengono scartati.
- Scadenza gia' passata o anno scolastico vecchio -> scartato.
- I risultati sono ordinati per prossimita' a PROVINCIA_CASA.

I risultati gia' visti vengono salvati in dati/visti.json. Solo i NUOVI
vengono scritti in nuovi_bandi.md, usato dal workflow per aprire la issue.
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

try:
    from ddgs import DDGS
except ImportError:  # pragma: no cover
    from duckduckgo_search import DDGS  # type: ignore

# --- Configurazione ------------------------------------------------------------

# Provincia di riferimento per l'ordinamento (la piu' vicina viene prima).
PROVINCIA_CASA = "Pisa"
ORDINE_PROVINCE = ["Pisa", "Livorno", "Lucca", "Firenze", "Pistoia", "Prato",
                   "Siena", "Arezzo", "Grosseto", "Massa-Carrara"]

# Sigle delle province toscane (codici meccanografici, "(PI)", ecc.).
SIGLE_TOSCANA = {"ar": "Arezzo", "fi": "Firenze", "gr": "Grosseto", "li": "Livorno",
                 "lu": "Lucca", "ms": "Massa-Carrara", "pi": "Pisa", "po": "Prato",
                 "pt": "Pistoia", "si": "Siena"}

# Tutte le sigle provincia italiane (per riconoscere le NON toscane).
SIGLE_ITALIA = set("""ag al an ao ap aq ar at av ba bg bi bl bn bo br bs bt bz ca cb
ce ch cl cn co cr cs ct cz en fc fe fg fi fm fr ge go gr im is kr lc le li lo lt lu
mb mc me mi mn mo ms mt na no nu or pa pc pd pe pg pi pn po pr pt pu pv pz ra rc re
rg ri rm rn ro sa si so sp sr ss su sv ta te tn to tp tr ts tv ud va vb vc ve vi vr
vt vv""".split())
SIGLE_NON_TOSCANE = SIGLE_ITALIA - set(SIGLE_TOSCANA)

# Comuni toscani (con \b: parola intera), per provincia.
COMUNI_TOSCANA = {
    "Pisa": ["pisa", "pontedera", "san miniato", "santa croce sull'arno",
             "castelfranco di sotto", "volterra", "pomarance", "san giuliano terme",
             "vecchiano", "vicopisano", "ponsacco", "peccioli", "capannoli", "bientina",
             "calcinaia", "santa maria a monte", "montopoli", "fauglia", "casciana",
             "crespina", "santa luce", "castellina marittima", "riparbella",
             "montescudaio", "guardistallo", "montecatini val di cecina", "chianni",
             "lajatico", "terricciola", "palaia", "cascina"],
    "Livorno": ["livorno", "cecina", "rosignano", "piombino", "portoferraio",
                "venturina", "campiglia marittima", "castagneto carducci", "bibbona",
                "san vincenzo", "suvereto", "collesalvetti", "capoliveri",
                "porto azzurro", "isola d'elba"],
    "Lucca": ["lucca", "viareggio", "camaiore", "pietrasanta", "capannori", "altopascio",
              "barga", "castelnuovo di garfagnana", "seravezza", "massarosa",
              "forte dei marmi", "porcari", "gallicano", "borgo a mozzano",
              "bagni di lucca", "stazzema", "garfagnana", "versilia"],
    "Firenze": ["firenze", "empoli", "scandicci", "sesto fiorentino", "campi bisenzio",
                "lastra a signa", "bagno a ripoli", "pontassieve", "borgo san lorenzo",
                "figline", "incisa", "certaldo", "castelfiorentino", "fucecchio",
                "fiesole", "calenzano", "impruneta", "greve in chianti", "san casciano",
                "montelupo", "cerreto guidi", "reggello", "rufina", "dicomano",
                "vicchio", "scarperia", "barberino di mugello", "montespertoli",
                "tavarnelle", "barberino val d'elsa", "rignano sull'arno", "mugello",
                "empolese", "valdarno"],
    "Pistoia": ["pistoia", "montecatini terme", "monsummano", "quarrata", "agliana",
                "pescia", "serravalle pistoiese", "lamporecchio", "larciano",
                "san marcello", "pieve a nievole", "buggiano", "uzzano",
                "chiesina uzzanese", "ponte buggianese", "massa e cozzile", "valdinievole"],
    "Prato": ["prato", "montemurlo", "carmignano", "poggio a caiano", "vaiano", "vernio",
              "cantagallo"],
    "Siena": ["siena", "poggibonsi", "colle di val d'elsa", "montepulciano", "chiusi",
              "sinalunga", "chianciano", "san gimignano", "monteriggioni", "asciano",
              "castelnuovo berardenga", "sovicille", "montalcino", "pienza",
              "abbadia san salvatore", "piancastagnaio", "radicofani", "torrita",
              "rapolano", "gaiole", "castellina in chianti", "val d'elsa", "valdelsa"],
    "Arezzo": ["arezzo", "cortona", "montevarchi", "san giovanni valdarno", "terranuova",
               "bibbiena", "sansepolcro", "castiglion fiorentino", "foiano", "lucignano",
               "monte san savino", "bucine", "cavriglia", "loro ciuffenna",
               "castiglion fibocchi", "subbiano", "capolona", "anghiari",
               "pieve santo stefano", "pratovecchio", "chiusi della verna", "casentino",
               "valtiberina"],
    "Grosseto": ["grosseto", "follonica", "orbetello", "massa marittima", "gavorrano",
                 "manciano", "pitigliano", "castiglione della pescaia", "scarlino",
                 "roccastrada", "monte argentario", "capalbio", "scansano", "arcidosso",
                 "castel del piano", "santa fiora", "cinigiano", "maremma"],
    "Massa-Carrara": ["massa-carrara", "massa carrara", "carrara", "aulla", "pontremoli",
                      "fivizzano", "montignoso", "villafranca in lunigiana", "licciana",
                      "bagnone", "filattiera", "mulazzo", "fosdinovo", "tresana",
                      "lunigiana", "massa (ms)", "citta' di massa", "comune di massa"],
}
_RE_COMUNI = {prov: re.compile(r"\b(" + "|".join(re.escape(c) for c in comuni) + r")\b")
              for prov, comuni in COMUNI_TOSCANA.items()}
_RE_TOSCANA_PAROLA = re.compile(r"\btoscan[ao]\b|\busr toscana\b")

# Riferimenti chiari ad altre regioni/citta' -> scarta.
ALTRE_REGIONI_KW = [
    "piemonte", "lombardia", "veneto", "liguria", "friuli", "trentino", "alto adige",
    "emilia", "romagna", "marche", "umbria", "lazio", "abruzzo", "campania", "molise",
    "puglia", "basilicata", "calabria", "sicilia", "sardegna", "valle d'aosta",
    "milano", "torino", "genova", "bologna", "modena", "parma", "reggio emilia",
    "ferrara", "ravenna", "rimini", "forlì", "cesena", "piacenza", "venezia", "padova",
    "verona", "vicenza", "treviso", "rovigo", "belluno", "brescia", "bergamo", "monza",
    "como", "varese", "pavia", "cremona", "mantova", "lodi", "lecco", "sondrio",
    "trieste", "udine", "pordenone", "gorizia", "trento", "bolzano", "aosta", "novara",
    "alessandria", "asti", "cuneo", "vercelli", "biella", "verbania", "la spezia",
    "savona", "imperia", "roma", "latina", "frosinone", "viterbo", "rieti", "perugia",
    "terni", "ancona", "pesaro", "urbino", "macerata", "ascoli", "fermo", "l'aquila",
    "pescara", "chieti", "teramo", "napoli", "salerno", "avellino", "benevento",
    "caserta", "campobasso", "isernia", "bari", "foggia", "taranto", "brindisi", "lecce",
    "barletta", "andria", "trani", "potenza", "matera", "cosenza", "catanzaro",
    "reggio calabria", "crotone", "vibo valentia", "palermo", "catania", "messina",
    "agrigento", "trapani", "caltanissetta", "ragusa", "siracusa", "enna", "cagliari",
    "sassari", "nuoro", "oristano", "olbia",
]
_RE_ALTRE = re.compile(r"\b(" + "|".join(re.escape(k) for k in ALTRE_REGIONI_KW) + r")\b")

# Sigla provincia tra parentesi: "(PI)", "(ME)".
_RE_SIGLA_PAR = re.compile(r"\(([a-z]{2})\)")
# Codice meccanografico: sigla provincia + tipo istituto + 5 cifre + 1 carattere.
_RE_MECC = re.compile(
    r"\b([a-z]{2})(aa|ee|ic|is|mm|pc|pl|pm|ps|ra|rc|rh|ri|sd|sl|ta|td|te|tf|tl|tn|vc|ct)"
    r"\d{5}[0-9a-z]\b")
# CAP toscano (50000-59999) seguito da comune toscano o sigla toscana.
_RE_CAP_TOSCANO = re.compile(
    r"\b5\d{4}\b[\s,\-\u2013]*(?:" + "|".join(
        re.escape(c) for comuni in COMUNI_TOSCANA.values() for c in comuni)
    + r"|[a-z\u00e0-\u00f9' ]{2,30}?\s*\((?:ar|fi|gr|li|lu|ms|pi|po|pt|si)\))")
# CAP NON toscano seguito da sigla non toscana: es. "85047 Moliterno (PZ)".
_RE_CAP_NON_TOSCANO = re.compile(r"\b(?:[0-46-9]\d{4})\b[\s,\-\u2013]*[a-z\u00e0-\u00f9' ]{2,30}?\s*\(([a-z]{2})\)")

# Domini di news/portali/aziende da ESCLUDERE.
BLOCKLIST = [
    "orizzontescuola.it", "euroedizioni.it", "campustore.it", "deascuola.it",
    "anastasis.it", "qualificagroup.it", "giustoscuola.it", "notiziedellascuola.it",
    "opencup.gov.it", "consorzioulisse.net", "formasys.it", "sinergiediscuola.it",
    "elissrl.net", "formatori.eu", "pn20212027.istruzione.it", "istruzione.it",
    "miur.gov.it", "mim.gov.it", "adecco", "indeed", "infojobs",
    "tecnicadellascuola.it", "tuttoscuola.com",
]
FONTE_SCUOLA = ["edu.it", "albo", "trasparenza", "amministrazione-trasparente",
                "amministrazionetrasparente", "ckube", "scuolanext", "albopretorio"]

# Segnali di procedura di selezione candidabile: devono comparire nel TITOLO
# o nell'URL (lo snippet da solo non basta: troppe pagine generiche).
KW_SELEZIONE = ["selezione", "reclutamento", "manifestazione di interesse",
                "procedura comparativa", "avviso pubblico", "avviso di selezione",
                "avviso-di-selezione", "avviso-selezione", "bando", "reperimento",
                "candidatur", "avviso"]
KW_FIGURA = ["formator", "esperto", "esperti"]

# Esiti / atti non candidabili -> scarta.
KW_ESITI = [
    "graduatoria", "graduatorie", "esito", "esiti", "vincitor", "idonei",
    "approvazione atti", "approvazione degli atti", "decreto di approvazione",
    "atti della selezione", "risultati selezion", "decreto di individuazione",
    "determina di individuazione", "individuato quale", "individuati quali",
    "provveduto all'individuazione", "verbale", "nomina", "aggiudicazione",
    "scorrimento", "pubblicazione graduatoria", "conferimento incarico a",
    "determina di affidamento", "decisione a contrarre", "determina a contrarre",
    "determina di avvio", "annullamento", "autotutela", "revoca",
    "bando scaduto", "termini scaduti",
]
# Avvisi rivolti ad alunni/studenti -> non e' formazione docenti.
KW_TARGET_ALUNNI = ["rivolto agli alunni", "rivolti agli alunni", "per gli alunni",
                    "destinatari: alunni", "alunni delle classi", "rivolto agli studenti",
                    "rivolti agli studenti", "per gli studenti", "destinatari: studenti"]
# Selezioni riservate al solo personale interno della scuola.
KW_INTERNO = ["selezione interna", "personale interno", "riservato al personale",
              "riservata al personale", "docenti interni", "solo interni"]
KW_ESTERNO = ["esterno", "esterni", "collaborazione plurima", "esterno/a"]

# --- Date ---------------------------------------------------------------------

_MESI = {"gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6,
         "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11,
         "dicembre": 12}
_SCAD_NUM = re.compile(
    r"(?:scadenza|entro(?:\s+il)?|termine(?:\s+ultimo)?(?:\s+di\s+presentazione)?)"
    r"[^\d]{0,40}(\d{1,2})[\/\.\-](\d{1,2})[\/\.\-](20\d{2})", re.I)
_SCAD_TXT = re.compile(
    r"(?:scadenza|entro(?:\s+il)?|termine)[^\d]{0,40}(\d{1,2})\u00b0?\s+"
    r"(gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|"
    r"novembre|dicembre)\s+(20\d{2})", re.I)
ANNO_MIN = datetime.now(timezone.utc).year - 1
_ANNO_NEL_PATH = re.compile(r"/(20\d{2})/\d{1,2}/")
_AS_RE = re.compile(r"a[\.\-\s]?[as][\.\-\s]*(20\d{2})\s*[/\-\u2013]\s*(?:20)?\d{2}", re.I)


def scadenza_passata(testo: str) -> bool:
    oggi = datetime.now(timezone.utc).date()
    t = testo.lower()
    for m in _SCAD_NUM.finditer(t):
        try:
            if date(int(m.group(3)), int(m.group(2)), int(m.group(1))) < oggi:
                return True
        except ValueError:
            continue
    for m in _SCAD_TXT.finditer(t):
        try:
            if date(int(m.group(3)), _MESI[m.group(2)], int(m.group(1))) < oggi:
                return True
        except (ValueError, KeyError):
            continue
    return False


def anno_scolastico_vecchio(testo: str) -> bool:
    return any(int(m.group(1)) < ANNO_MIN for m in _AS_RE.finditer(testo))


# --- Geolocalizzazione: SOLO TOSCANA ACCERTATA ---------------------------------

def _analizza_geo(t: str) -> tuple[str, str]:
    """Analizza un testo (gia' minuscolo). Ritorna ('si', provincia),
    ('no', motivo) oppure ('?', '')."""
    # 1) Codice meccanografico: la sigla iniziale decide.
    for m in _RE_MECC.finditer(t):
        sig = m.group(1)
        if sig in SIGLE_TOSCANA:
            return "si", SIGLE_TOSCANA[sig]
        if sig in SIGLE_NON_TOSCANE:
            return "no", f"codice {m.group(0).upper()}"
    # 2) CAP + comune/sigla.
    m = _RE_CAP_TOSCANO.search(t)
    if m:
        for prov, rx in _RE_COMUNI.items():
            if rx.search(m.group(0)):
                return "si", prov
        ms = _RE_SIGLA_PAR.search(m.group(0))
        if ms and ms.group(1) in SIGLE_TOSCANA:
            return "si", SIGLE_TOSCANA[ms.group(1)]
        return "si", "Toscana"
    m = _RE_CAP_NON_TOSCANO.search(t)
    if m and m.group(1) in SIGLE_NON_TOSCANE:
        return "no", f"CAP/sigla ({m.group(1).upper()})"
    # 3) Sigla tra parentesi.
    for m in _RE_SIGLA_PAR.finditer(t):
        if m.group(1) in SIGLE_TOSCANA:
            return "si", SIGLE_TOSCANA[m.group(1)]
        if m.group(1) in SIGLE_NON_TOSCANE:
            return "no", f"sigla ({m.group(1).upper()})"
    # 4) Altre regioni/citta' chiaramente non toscane.
    m = _RE_ALTRE.search(t)
    if m:
        return "no", m.group(1)
    # 5) Comuni toscani per parola intera; parola "toscana".
    for prov, rx in _RE_COMUNI.items():
        if rx.search(t):
            return "si", prov
    if _RE_TOSCANA_PAROLA.search(t):
        return "si", "Toscana"
    return "?", ""


_CACHE_PAGINE: dict[str, str] = {}
_FETCH_COUNT = 0
MAX_FETCH = 40


def scarica_pagina(url: str, timeout: int = 12) -> str:
    """Scarica il testo (minuscolo) di una pagina; '' se non possibile."""
    global _FETCH_COUNT
    if url in _CACHE_PAGINE:
        return _CACHE_PAGINE[url]
    if _FETCH_COUNT >= MAX_FETCH or url.lower().endswith(".pdf"):
        return ""
    _FETCH_COUNT += 1
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (ricerca-bandi-toscana)"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            ctype = (r.headers.get("Content-Type") or "").lower()
            if "pdf" in ctype:
                testo = ""
            else:
                raw = r.read(500_000)
                testo = re.sub(r"<[^>]+>", " ", raw.decode("utf-8", errors="ignore")).lower()
    except Exception as exc:
        print(f"[warn] pagina non scaricabile: {url} -> {exc}", file=sys.stderr)
        testo = ""
    _CACHE_PAGINE[url] = testo
    time.sleep(1)
    return testo


def geo_toscana(titolo: str, snippet: str, url: str) -> tuple[str, str]:
    """Ritorna ('si', provincia) solo se la Toscana e' ACCERTATA, altrimenti
    ('no', motivo). Ordine: testo -> pagina dell'avviso -> home del sito."""
    esito, dove = _analizza_geo(f"{titolo} {snippet} {url}".lower())
    if esito != "?":
        return esito, dove
    esito, dove = _analizza_geo(scarica_pagina(url))
    if esito != "?":
        return esito, dove
    dom = dominio(url)
    if dom:
        esito, dove = _analizza_geo(scarica_pagina(f"https://{dom}/"))
        if esito != "?":
            return esito, dove
    return "no", "localita' non accertabile"


# --- Filtri di pertinenza -------------------------------------------------------

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


def e_rilevante(titolo: str, snippet: str, url: str) -> bool:
    if not fonte_scuola(url) or url_troppo_vecchio(url):
        return False
    t = f"{titolo} {snippet} {url}".lower()
    tu = f"{titolo} {url}".lower()
    if any(k in t for k in KW_ESITI):
        return False
    if any(k in t for k in KW_TARGET_ALUNNI):
        return False
    if any(k in t for k in KW_INTERNO) and not any(k in t for k in KW_ESTERNO):
        return False
    if scadenza_passata(t) or anno_scolastico_vecchio(t):
        return False
    if not any(k in t for k in KW_FIGURA):
        return False
    # La selezione deve risultare dal titolo o dall'URL, non solo dallo snippet.
    return any(k in tu for k in KW_SELEZIONE)


# --- Ricerca ---------------------------------------------------------------------

PROVINCE_TOSCANA = ["Pisa", "Firenze", "Livorno", "Lucca", "Pistoia", "Prato",
                    "Arezzo", "Siena", "Grosseto", "Massa-Carrara"]
QUERIES = [
    f'"avviso di selezione" "esperto formatore" site:edu.it {p}' for p in PROVINCE_TOSCANA
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
MAX_PER_QUERY = 20
RECENZA = "m"

ROOT = Path(__file__).resolve().parent.parent
DATI_DIR = ROOT / "dati"
STATO_FILE = DATI_DIR / "visti.json"
ARCHIVIO_FILE = DATI_DIR / "risultati.md"
NUOVI_FILE = ROOT / "nuovi_bandi.md"


def carica_stato() -> set[str]:
    if STATO_FILE.exists():
        return set(json.loads(STATO_FILE.read_text(encoding="utf-8")).get("urls", []))
    return set()


def salva_stato(urls: set[str]) -> None:
    DATI_DIR.mkdir(parents=True, exist_ok=True)
    STATO_FILE.write_text(json.dumps({"urls": sorted(urls)}, ensure_ascii=False, indent=2),
                          encoding="utf-8")


def normalizza_url(url: str) -> str:
    return url.split("#", 1)[0].rstrip("/")


def cerca(visti: set[str]) -> list[dict]:
    trovati: dict[str, dict] = {}
    with DDGS() as ddgs:
        for q in QUERIES:
            try:
                risultati = ddgs.text(q, region="it-it", safesearch="off",
                                      max_results=MAX_PER_QUERY, timelimit=RECENZA)
            except Exception as exc:
                print(f"[warn] query fallita: {q!r} -> {exc}", file=sys.stderr)
                time.sleep(3)
                continue
            for r in risultati or []:
                url = normalizza_url(r.get("href") or r.get("url") or "")
                if not url or url in trovati or url in visti:
                    continue
                titolo = (r.get("title") or "").strip()
                snippet = (r.get("body") or "").strip()
                if not e_rilevante(titolo, snippet, url):
                    continue
                esito, dove = geo_toscana(titolo, snippet, url)
                if esito != "si":
                    print(f"[geo] scartato ({dove}): {titolo[:70]}", file=sys.stderr)
                    continue
                trovati[url] = {"url": url, "titolo": titolo or url, "snippet": snippet,
                                "query": q, "provincia": dove}
            time.sleep(2)
    return list(trovati.values())


def _rank(r: dict) -> tuple[int, str]:
    p = r.get("provincia", "")
    return (ORDINE_PROVINCE.index(p) if p in ORDINE_PROVINCE else len(ORDINE_PROVINCE),
            r["titolo"].lower())


def scrivi_archivio(nuovi: list[dict], quando: str) -> None:
    DATI_DIR.mkdir(parents=True, exist_ok=True)
    nuovo_file = not ARCHIVIO_FILE.exists()
    with ARCHIVIO_FILE.open("a", encoding="utf-8") as f:
        if nuovo_file:
            f.write("# Archivio avvisi esperti formatori (Toscana)\n\n")
        f.write(f"## Ricerca del {quando}\n\n")
        for r in sorted(nuovi, key=_rank):
            f.write(f"- \U0001f4cd {r['provincia']} \u2014 [{r['titolo']}]({r['url']})\n")
            if r["snippet"]:
                f.write(f"  - {r['snippet']}\n")
        f.write("\n")


def scrivi_notifica(nuovi: list[dict], quando: str) -> None:
    righe = [f"@panpauline \u2014 trovati **{len(nuovi)}** nuovi avvisi candidabili per "
             f"**esperti formatori** in scuole della **Toscana** (ricerca del {quando}).",
             f"Ordinati per vicinanza a {PROVINCIA_CASA}. Graduatorie, esiti, selezioni "
             "interne e scuole fuori Toscana sono esclusi.", ""]
    for r in sorted(nuovi, key=_rank):
        righe.append(f"### \U0001f4cd {r['provincia']} \u2014 [{r['titolo']}]({r['url']})")
        if r["snippet"]:
            righe.append(f"> {r['snippet']}")
        righe.append(f"`query: {r['query']}`")
        righe.append("")
    righe.append("---")
    righe.append("_Ricerca automatica limitata alla Toscana accertata. Verifica sempre "
                 "l'avviso sul sito della scuola e la scadenza prima di candidarti._")
    NUOVI_FILE.write_text("\n".join(righe), encoding="utf-8")


def main() -> int:
    quando = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    visti = carica_stato()
    nuovi = cerca(visti)
    print(f"Avvisi toscani candidabili nuovi: {len(nuovi)}")
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
