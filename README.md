# licei-trend-iscrizioni

## Ricerca automatica bandi (formatori + dottorati umanistici)

Strumento che cerca periodicamente sul web:

1. **Bandi delle scuole italiane per la selezione di formatori** collegati
   all'**Avviso prot. n. 95165 del 24/04/2026** (PN Scuola e competenze
   2021-2027) e ad avvisi analoghi per la formazione del personale docente.
2. **Bandi di dottorato di ricerca** delle universita' italiane (pubbliche e
   private) su materie umanistiche affini al profilo: italianistica, latino,
   filologia, linguistica, didattica, metodologie didattiche, pedagogia,
   studi umanistici.

### Come funziona

- **`scripts/cerca_bandi.py`** — ricerca dei bandi formatori (stato in
  `dati/visti.json`, archivio in `dati/risultati.md`).
- **`scripts/cerca_dottorati.py`** — ricerca dei bandi di dottorato umanistici
  (stato in `dati/visti_dottorati.json`, archivio in
  `dati/risultati_dottorati.md`).
- **`.github/workflows/ricerca-bandi.yml`** — GitHub Action che:
  - gira automaticamente **ogni 4 giorni** (cron `0 5 */4 * *`, ore 05:00 UTC);
  - esegue entrambe le ricerche;
  - apre **due issue separate** su GitHub (una per i formatori, una per i
    dottorati) quando ci sono novita' — GitHub ti invia un'email di notifica.

### Come attivarla

> [!IMPORTANT]
> Le Action schedulate di GitHub si attivano **solo dal branch principale
> (`main`)**. Per far partire la pianificazione automatica, questo branch va
> unito a `main`.

1. Unisci le modifiche a `main`.
2. Vai su **Settings → Actions → General** e assicurati che i workflow abbiano
   permessi di **lettura e scrittura** ("Read and write permissions").
3. Puoi lanciare una ricerca subito a mano da **Actions → Ricerca bandi
   formatori → Run workflow**.

### Personalizzare le ricerche

Le parole chiave e le query sono in cima a ciascuno script
(`scripts/cerca_bandi.py`, `scripts/cerca_dottorati.py`), nella sezione
*Configurazione*: puoi aggiungerne o modificarle liberamente.
