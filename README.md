# Volleybaltoernooi-analyse

Deze Streamlit-app leest CEV/WEVZA-achtige PDF-bulletins uit, laat de herkende spelers controleren en maakt een Excelrapport plus een deelbaar A4-PDF-overzicht. De app gebruikt geen AI of externe analyse-API.

De app bewaart toernooien en spelers uitsluitend in het geheugen van de huidige browsersessie. Iedere bezoeker krijgt een eigen, afgescheiden sessie. Na het beëindigen of handmatig wissen van de sessie zijn de gegevens weg. Bij online gebruik wordt het bulletin wel op de Streamlit-server verwerkt; het wordt niet permanent door de app opgeslagen. Tekst-PDF's worden rechtstreeks gelezen. Afbeeldings- en scanpagina's worden zo nodig lokaal op de Streamlit-server met Tesseract OCR verwerkt.

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
4. Klik **Import goedkeuren en gebruiken**. De app verwerkt de import pas wanneer er geen bekende waarschuwingen meer zijn.
5. Vul later onder **Resultaten** de eindranking in.
6. Download onder **Rapportage** het Excelbestand en/of het compacte A4-PDF-overzicht.

Het Excelrapport bevat drie tabbladen:

- **Overzicht**: alle kerncijfers, landen, posities, rankinganalyse en twee gekleurde staafdiagrammen op één liggende A4.
- **Spelers**: de volledige spelerslijst.
- **Resultaten**: eindranking en correlatieanalyse.

Download de gewenste rapporten voordat u de browser sluit. De app heeft bewust geen database of back-upfunctie. Via **Sessiedata wissen** kan de volledige tijdelijke werksessie direct worden verwijderd.

## Ondersteund in versie 0.1

- Tekstgebaseerde en afbeeldingsgebaseerde CEV/WEVZA-rosters met herkenbare kolommen voor speler, positie, geboortedatum en lengte.
- Detectie van datumvolgorde op documentniveau, met verplichte keuze bij twijfel.
- Positienormalisatie, validatie, tijdelijke sessieverwerking, ranking, correlaties, Excel-export en A4-PDF-export.
- Een later uitbreidbaar `match`-datamodel; wedstrijdanalyse is nog niet aanwezig.

Niet iedere willekeurige bondslay-out kan foutloos worden herkend. De app toont een duidelijke melding wanneer geen betrouwbare spelersregels worden gevonden; gegevens worden dan niet geïmporteerd.

## Privacy bij ontwikkeling

Zet geen echte bulletins, spelerslijsten, databases of exports in Git. De map `samples` negeert PDF- en Excelbestanden automatisch. De tests gebruiken uitsluitend een tijdens de testrun aangemaakt synthetisch bulletin met verzonnen spelers.

## Tests uitvoeren

Open een opdrachtprompt in deze map en voer uit:

```text
.venv\Scripts\python.exe -m pytest -q
```
