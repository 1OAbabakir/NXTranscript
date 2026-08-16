# Transkript

Transkript ist eine Desktop-Anwendung zur Transkription von Audiodateien mit automatischer Sprechertrennung und Zeitstempeln. Die Verarbeitung erfolgt über die OpenAI Audio API. Die Anwendung besitzt eine grafische Oberfläche und kann alternativ über die Kommandozeile verwendet werden.

## Funktionen

- zweisprachige Transkription für Deutsch und Persisch innerhalb derselben Audiodatei
- automatische Unterscheidung mehrerer Sprecher
- sekundengenaue Start- und Endzeit für kurze Gesprächsabschnitte
- automatische Vorbereitung und Aufteilung großer Audiodateien
- Speichern des fertigen Transkripts als UTF-8-Textdatei
- helle und dunkle Oberfläche
- separates Protokollfenster für Status- und Fehlermeldungen
- API-Key-Eingabe direkt in der grafischen Oberfläche
- eigenständige Windows-Anwendung mit eingebettetem FFmpeg
- Build-Skript für Apple-Silicon-Macs

## Beispielausgabe

```text
Datei: gespraech.mp3
Dauer: 00:04:32
Sprachen: Deutsch und Persisch

[00:00:00 – 00:00:07] Sprecher 1: Guten Morgen und herzlich willkommen.
[00:00:08 – 00:00:15] Sprecher 2: سلام، خیلی ممنون از دعوت شما.
```

Die Sprecher werden mit technischen Nummern unterschieden. Bis zu vier erkannte Stimmen werden über längere Dateien hinweg mit kurzen lokalen Referenzausschnitten stabilisiert. Die Anwendung ermittelt daraus keine wirklichen Namen oder Identitäten.

## Voraussetzungen

Für die fertige Windows-Anwendung wird keine separate Python-Installation benötigt. Erforderlich sind:

- eine Internetverbindung
- ein gültiger OpenAI API-Key
- verfügbares Guthaben beziehungsweise ein aktiver Abrechnungszugang für die OpenAI API

Für die Ausführung aus dem Quellcode oder den Bau einer neuen Version wird Python 3 benötigt. Unter macOS muss die Python-Installation außerdem Tkinter enthalten.

## Windows-Anwendung verwenden

1. `dist/Transkript.exe` starten.
2. Im Kopfbereich **Optionen** öffnen.
3. Den OpenAI API-Key eingeben und **Speichern** wählen.
4. Über **Datei auswählen** eine Audiodatei auswählen.
5. **Transkribieren** drücken.
6. Das fertige Ergebnis über **Speichern** als `.txt` sichern.

Der API-Key bleibt nur bis zum Schließen der Anwendung im Arbeitsspeicher. Er wird weder im Programm noch in einer `.env`- oder Konfigurationsdatei gespeichert.

Mit **Protokoll** lässt sich ein separates Fenster öffnen. Dort können Status- und Fehlermeldungen angesehen, kopiert oder geleert werden.

## Unterstützte Audiodateien

Der Dateidialog bietet direkt folgende Formate an:

- MP3 (`.mp3`)
- WAV (`.wav`)
- M4A (`.m4a`)
- OGG (`.ogg`)
- FLAC (`.flac`)
- MP4 (`.mp4`)
- WebM (`.webm`)

Über **Alle Dateien** lassen sich auch weitere Audioformate auswählen. Ob diese verarbeitet werden können, hängt davon ab, ob das eingebettete FFmpeg und die OpenAI Audio API das jeweilige Format unterstützen. Die oben aufgeführten Formate sind daher die empfohlene Auswahl.

## Intelligente Audioaufteilung

Jede Datei wird lokal mit FFmpeg in ein berechenbares Mono-MP3 mit 16 kHz und 48 kbit/s normalisiert. Die Aufteilung berücksichtigt gleichzeitig:

- höchstens 24.000.000 Byte pro API-Request als Sicherheitsabstand zum 25-MB-Limit,
- höchstens zehn Minuten pro Diarisierungsabschnitt, damit lange, dicht gesprochene Antworten nicht abgeschnitten werden,
- erkannte Sprechpausen innerhalb eines 90-Sekunden-Suchfensters,
- eine Sekunde Überlappung an den Grenzen gegen abgeschnittene Wörter.

Überlappende Segmente werden anhand ihres zeitlichen Mittelpunkts genau einem Abschnitt zugeordnet. Alle Zeitstempel werden anschließend auf die Originalzeit der vollständigen Datei zurückgerechnet. Temporäre Dateien werden nach Abschluss automatisch entfernt.

## Deutsch und Persisch

Die Verarbeitung besteht aus drei Stufen:

1. `gpt-4o-transcribe-diarize` ermittelt Sprecherwechsel und Zeitstempel, ohne eine einzelne Eingabesprache zu erzwingen.
2. Direkt benachbarte Abschnitte desselben Sprechers werden gebündelt und mit `gpt-transcribe` sowie den Sprachhinweisen `de` und `fa` erneut transkribiert. Dieser Text ist das qualitative Endergebnis.
3. `whisper-1` ermittelt separat Wort-Zeitstempel. Sein Text wird nicht ausgegeben; ein lokaler Sequenzabgleich überträgt ausschließlich seine Zeiten auf den hochwertigen Text aus Stufe 2.

Aus dem abgeglichenen Ergebnis bildet die Anwendung lesbare Untertitelabschnitte mit sekundengenauen Start- und Endzeiten. Bevorzugte Grenzen sind Satzenden, Sprechpausen und Sprachwechsel; lange Passagen werden spätestens nach acht Sekunden beziehungsweise einer gut lesbaren Textlänge getrennt. Falls Whisper keine Wortzeiten liefert, wird das Timing lokal geschätzt. So entstehen weder ein einziger riesiger Zeitblock noch unlesbare Einzelwortzeilen.

Der zweisprachige Pass bewahrt Deutsch in lateinischer und Persisch in persischer Schrift. Er übersetzt die Inhalte nicht. Falls ein einzelner Verfeinerungsrequest fehlschlägt, bleibt für diesen Abschnitt die Basistranskription erhalten und das Ergebnis enthält einen Hinweis.

## Aus dem Quellcode starten

### Windows PowerShell

```powershell
cd "C:\Pfad\zu\Transkript"
python -m venv .venv-windows
.\.venv-windows\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirement.txt
python gui.py
```

Falls PowerShell das Aktivierungsskript blockiert, kann die virtuelle Umgebung ohne Aktivierung verwendet werden:

```powershell
.\.venv-windows\Scripts\python.exe -m pip install -r requirement.txt
.\.venv-windows\Scripts\python.exe gui.py
```

### macOS oder Linux

```bash
cd /pfad/zu/Transkript
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirement.txt
python gui.py
```

## Kommandozeile verwenden

`main.py` kann ohne grafische Oberfläche gestartet werden. Der API-Key wird dabei verdeckt im Terminal abgefragt:

```powershell
python main.py --datei "C:\Pfad\aufnahme.mp3" --output "transkription.txt"
```

Unter macOS oder Linux funktioniert derselbe Aufruf mit den dort üblichen Dateipfaden:

```bash
python3 main.py --datei "/pfad/aufnahme.mp3" --output "transkription.txt"
```

## Tests ausführen

Die Tests senden keine echten OpenAI-Anfragen. Sie prüfen unter anderem das lokale FFmpeg-Chunking und die erzeugten API-Parameter:

```bash
python -m unittest discover -s tests -v
```

## Windows-EXE bauen

Der Build verwendet die Datei `Transkript.spec`. Sie bindet das Logo, die benötigten Daten von `ttkbootstrap` und die FFmpeg-Binärdatei von `imageio-ffmpeg` ein.

```powershell
cd "C:\Pfad\zu\Transkript"
python -m venv .venv-windows
.\.venv-windows\Scripts\python.exe -m pip install --upgrade pip
.\.venv-windows\Scripts\python.exe -m pip install -r requirement.txt
.\.venv-windows\Scripts\pyinstaller.exe --noconfirm --clean Transkript.spec
```

Das Ergebnis befindet sich anschließend hier:

```text
dist/Transkript.exe
```

Die EXE wird ohne zusätzliches Konsolenfenster gebaut. Laufzeitmeldungen sind in der Anwendung über **Protokoll** erreichbar.

## Apple-Silicon-App und DMG bauen

Der macOS-Build muss direkt auf einem Apple-Silicon-Mac mit `arm64` ausgeführt werden. Ein Windows-Rechner kann keine native, korrekt paketierte macOS-App erzeugen.

Voraussetzungen:

- Mac mit Apple Silicon, beispielsweise M1, M2, M3 oder neuer
- Python 3 inklusive Tkinter
- Internetverbindung für die Installation der Abhängigkeiten

Im Terminal:

```bash
cd /pfad/zu/Transkript
bash build_macos_apple_silicon.sh
```

Das Skript erzeugt:

```text
dist/Transkript.app
dist/Transkript-macOS-Apple-Silicon.zip
dist/Transkript-macOS-Apple-Silicon.dmg
```

Die App ist standardmäßig nicht mit einem Apple-Developer-Zertifikat signiert und nicht notarisiert. Auf dem eigenen Mac kann sie normalerweise über Rechtsklick und **Öffnen** gestartet werden. Für eine öffentliche Weitergabe sollte die App mit einem Apple-Developer-Zertifikat signiert und anschließend von Apple notarisiert werden.

## Verwendete Technik

- Python
- Tkinter und ttkbootstrap für die Oberfläche
- OpenAI Python SDK
- Modell `gpt-4o-transcribe-diarize`
- Modell `gpt-transcribe` mit `languages=["de", "fa"]`
- Antwortformat `diarized_json`
- imageio-ffmpeg für das mitgelieferte FFmpeg
- PyInstaller für ausführbare Anwendungen

Die Sprechertranskription erkennt die Sprache ohne feste Vorgabe. Der zweite Pass setzt Deutsch und Persisch gemeinsam als erwartete Eingabesprachen. Die Diarisierung verwendet zusätzlich die automatische VAD-Chunking-Strategie der API.

## Datenschutz und API-Key

- Der API-Key wird nicht in das Repository oder die ausführbare Datei eingebettet.
- Der in der GUI eingegebene Key wird nur für die aktuelle Programmsitzung gehalten.
- Die lokal vorbereiteten Diarisierungsabschnitte und zweisprachigen Sprecherblöcke werden zur Transkription an die OpenAI API übertragen.
- Lokale temporäre Audioabschnitte werden nach der Verarbeitung gelöscht.
- API-Nutzung kann Kosten im zugehörigen OpenAI-Projekt verursachen.

Ein API-Key sollte niemals in Quellcode, Screenshots, Commits oder veröffentlichte Builds geschrieben werden. Falls ein Key versehentlich veröffentlicht wurde, sollte er im OpenAI-Dashboard sofort widerrufen und ersetzt werden.

## Fehlerbehebung

### Fehler 413 oder maximale Dateigröße überschritten

Die aktuelle Version kontrolliert jeden erzeugten Abschnitt gegen ein Limit von 24.000.000 Byte. Falls der Fehler weiterhin erscheint, prüfen, ob wirklich die neueste EXE gestartet wurde. Im Protokollfenster wird die Anzahl der erzeugten Abschnitte angezeigt.

### Keine API-Nutzung und keine Transkription

- Unter **Optionen** prüfen, ob ein API-Key für die aktuelle Sitzung eingetragen wurde.
- Internetverbindung kontrollieren.
- Das Fenster **Protokoll** öffnen und die konkrete Fehlermeldung prüfen.
- Im OpenAI-Konto kontrollieren, ob das API-Projekt aktiv ist und über Guthaben beziehungsweise Abrechnung verfügt.

### Datei lässt sich nicht auswählen

Im Dateidialog **Alle Dateien** auswählen. Bei ungewöhnlichen Container- oder Codecformaten die Datei gegebenenfalls vorher in MP3, WAV, M4A, OGG oder FLAC umwandeln.

### Windows-Build meldet eine fehlende `bootstrap.ttf`

Die Anwendung muss mit der aktuellen `Transkript.spec` gebaut werden. Diese sammelt die erforderlichen `ttkbootstrap`-Daten automatisch ein.

### macOS blockiert die App

Bei einem nicht signierten privaten Build im Finder Rechtsklick auf die App und **Öffnen** wählen. Für eine reguläre Verteilung sind Codesignierung und Notarisierung erforderlich.

## Projektstruktur

```text
Transkript/
├── gui.py                          # grafische Oberfläche
├── main.py                         # Transkription und Kommandozeile
├── requirement.txt                 # Python-Abhängigkeiten
├── Transkript.spec                 # Windows-PyInstaller-Konfiguration
├── build_macos_apple_silicon.sh    # Apple-Silicon-Buildskript
├── MACOS_APPLE_SILICON.md          # zusätzliche macOS-Buildhinweise
├── transkript-logo.png             # ursprüngliche Logo-Datei
├── transkript-logo-transparent.png # transparentes GUI-Logo und macOS-Iconquelle
├── transkript-logo-transparent.ico # transparentes Windows-Programmsymbol
├── transkript-logo.ico             # ursprüngliches Windows-Programmsymbol
└── tests/test_main.py              # Offline-Tests für Audio- und API-Logik
```

Virtuelle Umgebungen sowie die Ordner `build` und `dist` sollten nicht in Git eingecheckt werden.

## Privates GitHub-Repository

Auf GitHub zuerst ein leeres Repository erstellen und die Sichtbarkeit auf **Private** stellen. Anschließend in PowerShell:

```powershell
cd "C:\Pfad\zu\Transkript"
git init -b main
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/DEIN-NAME/DEIN-REPO.git
git push -u origin main
```

Vor dem ersten Commit sollte eine `.gitignore` mindestens diese Einträge enthalten:

```gitignore
.venv*/
__pycache__/
*.py[cod]
build/
dist/
.env
.env.*
*.env
.DS_Store
Thumbs.db
```

Spätere Änderungen werden so hochgeladen:

```powershell
git add .
git commit -m "Änderungen beschreiben"
git push
```

## Abhängigkeiten

Die Python-Abhängigkeiten stehen in `requirement.txt`:

- `openai`
- `Pillow`
- `ttkbootstrap`
- `PyInstaller`
- `imageio-ffmpeg`

## Hinweise

Die Qualität von Transkription, Sprechertrennung und Zeitstempeln hängt von Aufnahmequalität, Hintergrundgeräuschen, gleichzeitigem Sprechen, Mikrofonabstand und Sprache ab. Die Ausgabe sollte vor einer weiteren Verwendung kontrolliert werden.
