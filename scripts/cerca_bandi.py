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
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    # Pacchetto attuale
    from ddgs import DDGS
except ImportError:  # pragma: no cover - fallback per versioni vecchie
    from duckduckgo_search import DDGS  # type: ignore

# --- Configurazione: modifica qui per affinare la ricerca ---------------------

# Query inviate al motore di ricerca. Aggiungine/modificane liberamente.
QUERIES = [
    '"avviso 95165" formatori',
    '"prot. 95165" 2026 selezione formatori scuola',
    'avviso 95165 PN Scuola e competenze selezione esperti formatori',
    'selezione formatori formazione personale docente PN Scuola e competenze 2021-2027',
    'avviso pubblico selezione esperti formatori potenziamento competenze docenti 2026',
    'bando reclutamento formatori formazione docenti PN scuola competenze avviso',
    'avviso selezione formatori competenze professionali docenti edu.it 2026',
]

# Il numero di protocollo: se compare, il risultato e' quasi certamente rilevante.
PROTOCOLLO = "95165"

# Parole che indicano la figura cercata (formatore/esperto).
KW_FIGURA = ["formator", "esperto formator", "esperti formator", "formazione formator"]

# Parole che indicano un bando/avviso di selezione.
KW_BANDO = ["bando", "avviso", "selezione", "reclutamento", "manifestazione di interesse",
            "procedura comparativa", "candidatura"]

# Parole che indicano il contesto/programma corretto.
KW_CONTESTO = ["pn scuola", "scuola e competenze", "potenziamento", "competenze professionali",
               "formazione del personale", "personale docente", "2021-2027", "95165"]

# Risultati massimi richiesti per ogni query.
MAX_PER_QUERY = 25

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


def e_rilevante(testo: str, url: str) -> bool:
    t = f"{testo} {url}".lower()
    if PROTOCOLLO in t:
        return True
    ha_figura = any(k in t for k in KW_FIGURA)
    ha_bando = any(k in t for k in KW_BANDO)
    ha_contesto = any(k in t for k in KW_CONTESTO)
    # Deve riguardare un formatore, in un bando, nel contesto giusto.
    return ha_figura and ha_bando and ha_contesto


def cerca() -> list[dict]:
    trovati: dict[str, dict] = {}
    with DDGS() as ddgs:
        for q in QUERIES:
            try:
                risultati = ddgs.text(q, region="it-it", safesearch="off",
                                      max_results=MAX_PER_QUERY)
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
    righe = [f"Trovati **{len(nuovi)}** nuovi bandi/avvisi per formatori "
             f"(ricerca del {quando}).", ""]
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
