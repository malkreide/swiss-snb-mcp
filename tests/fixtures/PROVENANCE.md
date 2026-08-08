# Herkunft der Fixtures

**Erzeugt von `scripts/record_fixtures.py`. Nicht von Hand pflegen.**

Aufgezeichnet am **2026-08-08** von `data.snb.ch`, unveraendert bis
auf die je Datei dokumentierte Auswahl.

Ohne Datum ist «aufgezeichnet» nach zwei Jahren von «ausgedacht» nicht
mehr zu unterscheiden — die Datei sieht gleich aus, und niemand weiss,
ob sie den Stand von gestern zeigt oder den von vor drei
Schema-Wechseln. Das Datum macht diesen Abstand zu einer lesbaren Zahl.

**Es sind Ausschnitte, keine Vollabzuege** — aber nicht nach Position
zugeschnitten. In jeder Datei bleiben **alle Reihen** erhalten und nur
die Wertelisten sind gekuerzt: Ueber die Dimensionen argumentiert der
Code, die Werte zeigt er an. Waeren stattdessen «die ersten N Reihen»
aufgezeichnet worden, liesse sich nicht mehr sehen, welche Waehrungen,
Positionen und Bankengruppen die Quelle ueberhaupt fuehrt — und genau
daran haengen drei der Befunde.

Eine Fixture belegt damit die *Form* der Antwort und einen datierten
Ausschnitt ihres Inhalts — nicht den Bestand. Aussagen ueber
Vollstaendigkeit gehoeren in Live-Tests (`pytest -m live`).

## `cube_devkum.json`

- **Quelle:** `https://data.snb.ch/api/cube/devkum/data/json/de`
- **Aufgezeichnet:** 2026-08-08
- **Auswahl:** alle 54 Reihen, je die letzten 24 Werte. Alle Reihen bleiben, weil die Fixture damit auch belegt, WELCHE Waehrungen der Cube fuehrt -- ein Zuschnitt nach Position haette genau das verdeckt
- **Groesse:** 123436 B
- **SHA-256:** `1d66958c4e4318ba8d42b5fa931bb3262576e3fb434b33d55799d211f3d22f3f`

## `cube_devkua_en.json`

- **Quelle:** `https://data.snb.ch/api/cube/devkua/data/json/en`
- **Aufgezeichnet:** 2026-08-08
- **Auswahl:** alle 26 Reihen, je die letzten 6 Werte; auf Englisch, weil der generische Cube-Zugriff die Sprache durchreicht und das sonst ungeprueft bleibt
- **Groesse:** 20181 B
- **SHA-256:** `c890df14334ee85b46ac57f09f2af532c830f814a20bb3654256a593763197da`

## `cube_snbbipo.json`

- **Quelle:** `https://data.snb.ch/api/cube/snbbipo/data/json/de`
- **Aufgezeichnet:** 2026-08-08
- **Auswahl:** alle 28 Positionen, je die letzten 24 Werte
- **Groesse:** 64295 B
- **SHA-256:** `5be824ef0abc9356ed80ab9bbe3b2bd0d89e332ef589e5e07bfdd99d511fe21c`

## `dimensions_bsta_snb_jahr_k_bil_akt_tot.json`

- **Quelle:** `https://data.snb.ch/api/warehouse/cube/BSTA.SNB.JAHR_K.BIL.AKT.TOT/dimensions/de`
- **Aufgezeichnet:** 2026-08-08
- **Auswahl:** vollstaendig — die Datei ist klein und jede Dimension zaehlt: aus ihrer Reihenfolge liest der Server, welche Position im Schluessel welche Dimension ist
- **Groesse:** 2394 B
- **SHA-256:** `31770ec172d9bd7c261d3ba475092f7d8498a3363e75a4ba34e568e26a1f609e`

## `warehouse_bil_aktiven_jahr.json`

- **Quelle:** `https://data.snb.ch/api/warehouse/cube/BSTA.SNB.JAHR_K.BIL.AKT.TOT/data/json/de`
- **Aufgezeichnet:** 2026-08-08
- **Auswahl:** alle 54 Reihen (Aktiven, Jahresdaten), je die letzten 6 Werte. Alle Reihen bleiben, weil erst die vollstaendige Besetzung der Dimension INLANDAUSLAND (['A', 'I', 'T'] bei Bankengruppe A30) sichtbar macht, dass der Server drei Aggregate unter einer Beschriftung fuehrt
- **Groesse:** 59584 B
- **SHA-256:** `f8d75a55014f68143f63c0975dbefb8e718d53fb11c7259b5a5d46f4cc4e655f`

## `dimensions_bsta_snb_jahr_k_bil_pas_tot.json`

- **Quelle:** `https://data.snb.ch/api/warehouse/cube/BSTA.SNB.JAHR_K.BIL.PAS.TOT/dimensions/de`
- **Aufgezeichnet:** 2026-08-08
- **Auswahl:** vollstaendig — die Datei ist klein und jede Dimension zaehlt: aus ihrer Reihenfolge liest der Server, welche Position im Schluessel welche Dimension ist
- **Groesse:** 2394 B
- **SHA-256:** `b1c8e901d232d9c4ea3b4937deec3fc6d1dbde3b33cb8d7cd7ac045d5b65cb8f`

## `warehouse_bil_passiven_jahr.json`

- **Quelle:** `https://data.snb.ch/api/warehouse/cube/BSTA.SNB.JAHR_K.BIL.PAS.TOT/data/json/de`
- **Aufgezeichnet:** 2026-08-08
- **Auswahl:** alle 54 Reihen (Passiven, Jahresdaten), je die letzten 6 Werte. Alle Reihen bleiben, weil erst die vollstaendige Besetzung der Dimension INLANDAUSLAND (['A', 'I', 'T'] bei Bankengruppe A30) sichtbar macht, dass der Server drei Aggregate unter einer Beschriftung fuehrt
- **Groesse:** 59545 B
- **SHA-256:** `779b9d39b5f8da577c22b4ee80bc8ce142aed4c909035e6999fe7d9d5b0db758`

## `dimensions_bsta_snb_mona_us_bil_akt_tot.json`

- **Quelle:** `https://data.snb.ch/api/warehouse/cube/BSTA.SNB.MONA_US.BIL.AKT.TOT/dimensions/de`
- **Aufgezeichnet:** 2026-08-08
- **Auswahl:** vollstaendig — die Datei ist klein und jede Dimension zaehlt: aus ihrer Reihenfolge liest der Server, welche Position im Schluessel welche Dimension ist
- **Groesse:** 2629 B
- **SHA-256:** `79a9dc03a255cd55c9ce820e77ca7d4aa43a11f0ce63ece93e33eb1380d711d1`

## `warehouse_bil_aktiven_monat.json`

- **Quelle:** `https://data.snb.ch/api/warehouse/cube/BSTA.SNB.MONA_US.BIL.AKT.TOT/data/json/de`
- **Aufgezeichnet:** 2026-08-08
- **Auswahl:** alle 36 Reihen, je die letzten 24 Werte. Der Schluessel traegt hier 5 Dimensionen statt vier (Konsolidierungsstufe, Inland und Ausland, Währung, Sektorale Gliederung nach ESVG, Bankengruppe)
- **Groesse:** 100060 B
- **SHA-256:** `5f45329ffeeaf3a654ebca090828aaef693f21c2e5458a4d9503e1abda69e2c2`

## `dimensions_bsta_snb_jahr_k_efr_ger.json`

- **Quelle:** `https://data.snb.ch/api/warehouse/cube/BSTA.SNB.JAHR_K.EFR.GER/dimensions/de`
- **Aufgezeichnet:** 2026-08-08
- **Auswahl:** vollstaendig — die Datei ist klein und jede Dimension zaehlt: aus ihrer Reihenfolge liest der Server, welche Position im Schluessel welche Dimension ist
- **Groesse:** 1431 B
- **SHA-256:** `715ff344d38316320dde29bb1ef5feb26ed6bbdf2c22b15332e0183f69f7267b`

## `warehouse_efr_ger.json`

- **Quelle:** `https://data.snb.ch/api/warehouse/cube/BSTA.SNB.JAHR_K.EFR.GER/data/json/de`
- **Aufgezeichnet:** 2026-08-08
- **Auswahl:** alle 12 Reihen (Geschaeftsertrag), je die letzten 6 Werte
- **Groesse:** 10845 B
- **SHA-256:** `86507b9aba51b2abf995e548704bed0d658856b97ea992264bbad10728f76329`
