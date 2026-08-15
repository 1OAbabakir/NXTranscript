# Transkript

Transkript ist eine Desktop-Anwendung zur Transkription von Audiodateien mit automatischer Sprechertrennung und Zeitstempeln. Die Verarbeitung erfolgt über die OpenAI Audio API. Die Anwendung besitzt eine grafische Oberfläche und kann alternativ über die Kommandozeile verwendet werden.

## Funktionen

- Transkription deutschsprachiger Audiodateien
- automatische Unterscheidung mehrerer Sprecher
- Start- und Endzeit für jeden erkannten Gesprächsabschnitt
- automatische Vorbereitung und Aufteilung großer Audiodateien
- Speichern des fertigen Transkripts als UTF-8-Textdatei
- helle und dunkle Oberfläche
- separates Output-Fenster für Status- und Fehlermeldungen
- API-Key-Eingabe direkt in der grafischen Oberfläche
- eigenständige Windows-Anwendung mit eingebettetem FFmpeg
- Build-Skript für Apple-Silicon-Macs

## Beispielausgabe

```text
Datei: gespraech.mp3
Dauer: 00:04:32

[00:00:00 – 00:00:07] Sprecher A: Guten Morgen und herzlich willkommen.
[00:00:08 – 00:00:15] Sprecher B: Vielen Dank für die Einladung.
```

Die Sprecher werden mit technischen Labels wie `A`, `B` oder `C` unterschieden. Die Anwendung erkennt nicht die wirklichen Namen oder Identitäten der Personen. Namen können anschließend im Text manuell ersetzt werden.

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

Mit **Output** lässt sich ein separates Protokollfenster öffnen. Dort können Status- und Fehlermeldungen angesehen, kopiert oder geleert werden.

## Unterstützte Audiodateien

Der Dateidialog bietet direkt folgende Formate an:

- MP3 (`.mp3`)
- WAV (`.wav`)
- M4A (`.m4a`)
- OGG (`.ogg`)
- FLAC (`.flac`)

Über **Alle Dateien** lassen sich auch weitere Audioformate auswählen. Ob diese verarbeitet werden können, hängt davon ab, ob das eingebettete FFmpeg und die OpenAI Audio API das jeweilige Format unterstützen. Die oben aufgeführten Formate sind daher die empfohlene Auswahl.

## Große Audiodateien

Dateien bis einschließlich 24 MiB werden direkt hochgeladen. Größere Dateien werden vor der Übertragung automatisch mit FFmpeg in Mono-MP3 mit 16 kHz und 48 kbit/s umgewandelt und in Abschnitte von jeweils 20 Minuten geteilt.

Jeder Abschnitt wird einzeln transkribiert. Die Anwendung addiert danach die Zeitversätze, sodass die Zeitstempel im fertigen Transkript wieder zur gesamten Originaldatei passen. Temporäre Abschnitte werden nach Abschluss automatisch entfernt.

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

Die EXE wird ohne zusätzliches Konsolenfenster gebaut. Laufzeitmeldungen sind in der Anwendung über **Output** erreichbar.

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
- Antwortformat `diarized_json`
- imageio-ffmpeg für das mitgelieferte FFmpeg
- PyInstaller für ausführbare Anwendungen

Die Transkription verwendet Deutsch als vorgegebene Sprache und aktiviert die automatische Chunking-Strategie der API.

## Datenschutz und API-Key

- Der API-Key wird nicht in das Repository oder die ausführbare Datei eingebettet.
- Der in der GUI eingegebene Key wird nur für die aktuelle Programmsitzung gehalten.
- Die ausgewählte Audiodatei beziehungsweise ihre vorbereiteten Abschnitte werden zur Transkription an die OpenAI API übertragen.
- Lokale temporäre Audioabschnitte werden nach der Verarbeitung gelöscht.
- API-Nutzung kann Kosten im zugehörigen OpenAI-Projekt verursachen.

Ein API-Key sollte niemals in Quellcode, Screenshots, Commits oder veröffentlichte Builds geschrieben werden. Falls ein Key versehentlich veröffentlicht wurde, sollte er im OpenAI-Dashboard sofort widerrufen und ersetzt werden.

## Fehlerbehebung

### Fehler 413 oder maximale Dateigröße überschritten

Die aktuelle Version teilt Dateien über 24 MiB automatisch auf. Falls der Fehler weiterhin erscheint, prüfen, ob wirklich die neueste EXE gestartet wurde. Im Output-Fenster sollte bei einer großen Datei die automatische Aufteilung angezeigt werden.

### Keine API-Nutzung und keine Transkription

- Unter **Optionen** prüfen, ob ein API-Key für die aktuelle Sitzung eingetragen wurde.
- Internetverbindung kontrollieren.
- Das Fenster **Output** öffnen und die konkrete Fehlermeldung prüfen.
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
├── transkript-logo.png             # Logo und macOS-Iconquelle
└── transkript-logo.ico             # Windows-Programmsymbol
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
