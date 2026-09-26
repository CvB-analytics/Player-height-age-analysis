# Lokale volleybaltoernooi-app

Deze Streamlit-app leest CEV/WEVZA-achtige PDF-bulletins lokaal uit, laat de herkende spelers controleren en maakt een Excelrapport plus een deelbaar A4-PDF-overzicht. De app verstuurt niets naar internet en gebruikt geen AI of API-key.

## Eenmalige installatie (Windows)

1. Installeer Python 3.11 of nieuwer via python.org. Vink tijdens de installatie **Add Python to PATH** aan.
2. Dubbelklik op `setup_app.bat`.
3. Wacht tot **Installatie gereed** verschijnt.

Voor deze eenmalige installatie zijn de Python-pakketten uit `requirements.txt` nodig. Met internet worden ze automatisch opgehaald. In een volledig afgesloten omgeving kan een beheerder dezelfde pakketten vooraf als lokale wheels beschikbaar stellen. Na installatie doet de app tijdens normaal gebruik geen netwerkverzoeken.

## App starten

1. Dubbelklik op `run_app.bat`.
2. De app opent in de standaardbrowser.
3. Laat het zwarte venster open zolang de app wordt gebruikt.
4. Stop de app door het zwarte venster te sluiten of daar `Ctrl+C` te drukken.

## Eenvoudige werkwijze

1. Kies **Nieuw toernooi** en vul minimaal naam, categorie, locatie en startdatum in.
2. Kies **Import controleren**, selecteer het PDF-bulletin en klik **PDF verwerken**.
3. Controleer alle waarschuwingen en corrigeer de tabel. Datums gebruikt u als `JJJJ-MM-DD`.
4. Klik **Import goedkeuren en opslaan**. De app weigert opslag zolang er nog bekende waarschuwingen zijn.
5. Vul later onder **Resultaten** de eindranking in.
6. Download onder **Rapportage** het Excelbestand en/of het compacte A4-PDF-overzicht.

Het Excelrapport bevat drie tabbladen:

- **Overzicht**: alle kerncijfers, landen, posities, rankinganalyse en twee gekleurde staafdiagrammen op één liggende A4.
- **Spelers**: de volledige spelerslijst.
- **Resultaten**: eindranking en correlatieanalyse.

Alle opgeslagen gegevens staan in `data/app.db`. Maak een kopie van dit bestand als back-up. Technische foutdetails staan lokaal in `data/app.log`.

## Ondersteund in versie 0.1

- Tekstgebaseerde CEV/WEVZA-bulletins met `FINAL TEAM LIST AND DELEGATION`.
- Detectie van datumvolgorde op documentniveau, met verplichte keuze bij twijfel.
- Positienormalisatie, validatie, lokale SQLite-opslag, ranking, correlaties, Excel-export en A4-PDF-export.
- Een later uitbreidbaar `match`-datamodel; wedstrijdanalyse is nog niet aanwezig.

Niet ondersteund: OCR voor gescande PDF's en algemene automatische herkenning van iedere willekeurige bondslay-out.

## Privacy bij ontwikkeling

Zet geen echte bulletins, spelerslijsten, databases of exports in Git. De map `samples` negeert PDF- en Excelbestanden automatisch. De tests gebruiken uitsluitend een tijdens de testrun aangemaakt synthetisch bulletin met verzonnen spelers.

## Tests uitvoeren

Open een opdrachtprompt in deze map en voer uit:

```text
.venv\Scripts\python.exe -m pytest -q
```
