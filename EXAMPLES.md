# Use Cases & Examples — swiss-snb-mcp

Real-world queries by audience. Each example states whether an API key is required.

## 🏫 Bildung & Schule

Lehrpersonen, Schulbehörden, Fachreferent:innen

### Frankenschock im Wirtschaftsunterricht

«Wie stark hat sich der EUR/CHF-Kurs zwischen Januar und März 2015 verändert, und welche Monatsendwerte zeigen den Frankenschock am deutlichsten?»

**API-Key nötig:** Nein

→ `snb_get_exchange_rates(currencies=["EUR1"], from_date="2015-01", to_date="2015-03", include_month_end=True, lang="de")`

Warum nützlich: Lehrpersonen können den Wechselkursschock mit offiziellen Monatsmittel- und Monatsendwerten belegen. Die Klasse sieht konkret, wie ein geldpolitischer Entscheid in exportorientierten Betrieben, Einkaufspreisen und Löhnen sichtbar wird.

### Leitzins und SARON für eine Unterrichtsreihe zu Zinsen

«Wie haben sich SNB-Leitzins und SARON seit Anfang 2022 entwickelt, und wo sieht man die Zinswende in den Daten?»

**API-Key nötig:** Nein

→ `snb_get_cube_data(cube_id="snbgwdzid", from_date="2022-01", to_date="2025-12", lang="de")`
→ `snb_get_cube_data(cube_id="zirepo", from_date="2022-01", to_date="2025-12", lang="de")`

Warum nützlich: Fachreferent:innen können offizielle SNB-Zeitreihen statt vereinfachter Lehrbuchgrafiken verwenden. Die Daten eignen sich für Aufgaben zu Hypotheken, Sparzinsen und geldpolitischer Transmission.

### Geldmenge M3 im Vergleich zur Inflation erklären

«Wie hat sich die Geldmenge M3 von 2020 bis 2024 entwickelt, und welche Monate eignen sich für eine Diskussion über Pandemie, Teuerung und Zinswende?»

**API-Key nötig:** Nein

→ `snb_get_cube_data(cube_id="snbmonagg", from_date="2020-01", to_date="2024-12", lang="de")`
→ `snb_get_cube_metadata(cube_id="snbmonagg", lang="de")`

Warum nützlich: Schulen können makroökonomische Begriffe mit Schweizer Originaldaten verbinden. Die Metadaten helfen, M1, M2 und M3 sauber voneinander zu unterscheiden.

## 👨‍👩‍👧 Eltern & Schulgemeinde

Elternräte, interessierte Erziehungsberechtigte

### Budget für eine Klassenreise nach London

«Unsere Klasse plant im Mai 2025 eine Reise nach London. Wieviel entsprechen 18'500 GBP gemäss SNB-Monatsmittel ungefähr in CHF?»

**API-Key nötig:** Nein

→ `snb_convert_currency(amount=18500, currency_id="GBP1", reference_month="2025-05")`
→ `snb_get_exchange_rates(currencies=["GBP1"], from_date="2025-01", to_date="2025-05", include_month_end=False, lang="de")`

Warum nützlich: Elternräte können Reisebudgets transparent mit einer offiziellen Quelle plausibilisieren. Der Verlauf der letzten Monate zeigt, ob ein Währungsrisiko für Anzahlungen relevant war.

### Schulhausfinanzierung und Zinsumfeld einordnen

«Warum sind Finanzierungskosten für ein neues Schulhaus heute anders als 2021, und was zeigen SNB-Leitzins und SARON dazu?»

**API-Key nötig:** Nein

→ `snb_get_cube_data(cube_id="snbgwdzid", from_date="2021-01", to_date="2025-12", lang="de")`
→ `snb_get_cube_data(cube_id="zirepo", from_date="2021-01", to_date="2025-12", lang="de")`

Warum nützlich: Eltern können Gemeindebeschlüsse zu Investitionen besser nachvollziehen. Der Zinsverlauf macht sichtbar, warum Baukredite, Reserven und Etappierungen politisch diskutiert werden.

## 🗳️ Bevölkerung & öffentliches Interesse

Allgemeine Öffentlichkeit, politisch und gesellschaftlich Interessierte

### SNB, Fed und EZB im Zinsvergleich

«Wie unterscheiden sich die Leitzinsen von SNB, Fed und EZB seit 2022, und wann war der Abstand zur Schweiz am grössten?»

**API-Key nötig:** Nein

→ `snb_get_cube_data(cube_id="snboffzisa", from_date="2022-01", to_date="2025-12", lang="de")`
→ `snb_get_cube_metadata(cube_id="snboffzisa", lang="de")`

Warum nützlich: Interessierte können Schlagzeilen über Zinsentscheide international einordnen. Die offizielle Vergleichsreihe zeigt, ob die Schweiz synchron oder bewusst anders reagierte.

### Grösse der Bankengruppen vergleichen

«Wie hoch waren die Aktiven von Kantonalbanken, Grossbanken und Raiffeisenbanken seit 2020, und welche Bankengruppe ist am stärksten gewachsen?»

**API-Key nötig:** Nein

→ `snb_get_banking_balance_sheet(bank_groups=["G10", "G15", "G25"], side="assets", frequency="annual", currency="T", from_date="2020", to_date="2024", lang="de")`
→ `snb_list_bank_groups()`

Warum nützlich: Die Bevölkerung erhält einen faktenbasierten Blick auf die Struktur des Schweizer Bankensektors. Bankengruppen werden mit offiziellen IDs erklärt, statt nur mit einzelnen bekannten Instituten.

### Aussenwirtschaft der Schweiz verstehen

«Was zeigen Zahlungsbilanz und Auslandvermögen seit 2020 über die wirtschaftliche Verflechtung der Schweiz mit dem Ausland?»

**API-Key nötig:** Nein

→ `snb_get_balance_of_payments(category="overview", from_date="2020", to_date="2024", lang="de")`
→ `snb_get_balance_of_payments(category="iip", from_date="2020", to_date="2024", lang="de")`

Warum nützlich: Öffentliche Diskussionen über Export, Kapitalflüsse und Auslandvermögen lassen sich mit offiziellen Quartalsdaten prüfen. Das hilft, einzelne Nachrichten in einen längeren Kontext zu setzen.

## 🤖 KI-Interessierte & Entwickler:innen

MCP-Enthusiast:innen, Forscher:innen, Prompt Engineers, öffentliche Verwaltung

### Tool-Discovery für robuste Prompts

«Welche SNB-Cubes sind in diesem MCP-Server verifiziert, und welche Metadaten brauche ich, um Leitzins, SARON und Geldmenge nicht zu verwechseln?»

**API-Key nötig:** Nein

→ `snb_list_known_cubes()`
→ `snb_get_cube_metadata(cube_id="snbgwdzid", lang="de")`
→ `snb_get_cube_metadata(cube_id="zirepo", lang="de")`
→ `snb_get_cube_metadata(cube_id="snbmonagg", lang="de")`

Warum nützlich: Prompt Engineers können vor der Datenabfrage die verfügbaren Dimensionen prüfen. Das reduziert fehlerhafte Cube-Nutzung und macht Agenten zuverlässiger.

### Portfolio-Kombination: Schulstandorte und Finanzumfeld in Zürich

«Welche Zürcher Schulanlagen liegen in Gebieten mit vielen Investitionsdebatten, und wie hat sich parallel das Schweizer Zinsumfeld verändert?»

**API-Key nötig:** SNB: Nein; Zurich Open Data: Nein.

→ `zurich_geo_features(layer_id="schulanlagen")` via https://github.com/malkreide/zurich-opendata-mcp
→ `zurich_parliament_search(query="Schulhaus Bau Kredit")` via https://github.com/malkreide/zurich-opendata-mcp
→ `snb_get_cube_data(cube_id="snbgwdzid", from_date="2021-01", to_date="2025-12", lang="de")`

Warum nützlich: Die Kombination verbindet lokale Infrastrukturfragen mit nationalem Zinsumfeld. Eine Verwaltung oder Redaktion kann räumliche Daten, politische Geschäfte und SNB-Zeitreihen in einem Arbeitsfluss vergleichen.

### Portfolio-Kombination: Klassenreise, Wechselkurs und ÖV-Verbindung

«Für eine Schulreise von Zürich nach Bern mit internationalem Gastbudget: Welche Verbindung passt, und wie rechne ich ein Budget von 2'000 EUR in CHF um?»

**API-Key nötig:** SNB: Nein; Swiss Transport: Ja, sofern OJP/Transport-API genutzt wird.

→ `transport_trip_plan(origin="Zürich HB", destination="Bern", date="2026-05-12", time="08:30")` via https://github.com/malkreide/swiss-transport-mcp
→ `snb_convert_currency(amount=2000, currency_id="EUR1", reference_month="2026-04")`
→ `snb_get_exchange_rates(currencies=["EUR1"], from_date="2025-10", to_date="2026-04", include_month_end=False, lang="de")`

Warum nützlich: Ein Agent kann Reiseplanung und Budgetprüfung in einem Dialog verbinden. Die SNB-Daten liefern eine nachvollziehbare Umrechnung, während der Transport-Server operative Verbindungsdaten beisteuert.

## 🔧 Technische Referenz: Tool-Auswahl nach Anwendungsfall

| Ich möchte… | Tool(s) | Auth nötig? |
|---|---|---|
| Monatskurse für eine oder mehrere Währungen in CHF abrufen | `snb_get_exchange_rates` | Nein |
| Jahresdurchschnitte für Wechselkurse ab 1980 vergleichen | `snb_get_annual_exchange_rates` | Nein |
| SNB-Bilanzpositionen wie Gold, Devisenanlagen oder Notenumlauf analysieren | `snb_get_balance_sheet` | Nein |
| Einen Fremdwährungsbetrag mit einem SNB-Monatsmittel in CHF umrechnen | `snb_convert_currency` | Nein |
| Gültige Währungs-IDs und Einheiten nachschlagen | `snb_list_currencies` | Nein |
| Gültige SNB-Bilanzpositionen und ihre IDs nachschlagen | `snb_list_balance_sheet_positions` | Nein |
| Einen bekannten SNB-Cube wie Leitzins, SARON oder Geldmenge abrufen | `snb_get_cube_data` | Nein |
| Dimensionen und Filterwerte eines SNB-Cubes verstehen | `snb_get_cube_metadata` | Nein |
| Verifizierte SNB-Cubes und passende Einstiegstools finden | `snb_list_known_cubes` | Nein |
| Bankbilanzen nach Bankengruppe, Seite, Frequenz und Währung vergleichen | `snb_get_banking_balance_sheet` | Nein |
| Erfolgsrechnungen von Bankengruppen wie Kantonalbanken oder Grossbanken abrufen | `snb_get_banking_income` | Nein |
| Zahlungsbilanz oder Auslandvermögen der Schweiz auswerten | `snb_get_balance_of_payments` | Nein |
| Rohdaten aus einem SNB-Warehouse-Cube abrufen | `snb_get_warehouse_data` | Nein |
| Dimensionen und Aktualisierungsdatum eines Warehouse-Cubes prüfen | `snb_get_warehouse_metadata` | Nein |
| Verfügbare Warehouse-Cubes für Bankenstatistik entdecken | `snb_list_warehouse_cubes` | Nein |
| Bankengruppen-IDs wie `G10`, `G15` oder `G25` nachschlagen | `snb_list_bank_groups` | Nein |
