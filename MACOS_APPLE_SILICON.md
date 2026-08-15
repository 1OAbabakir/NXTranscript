# Transkript für Apple Silicon bauen

Voraussetzungen:

- ein Mac mit Apple Silicon (M1 oder neuer)
- Python 3 inklusive Tkinter
- eine Internetverbindung für die einmalige Installation der Python-Pakete

Im Terminal in den Projektordner wechseln und den Build starten:

```bash
bash build_macos_apple_silicon.sh
```

Das Skript prüft, ob es auf macOS mit `arm64` läuft, erstellt das `.icns`-App-Symbol und erzeugt:

```text
dist/Transkript.app
dist/Transkript-macOS-Apple-Silicon.zip
dist/Transkript-macOS-Apple-Silicon.dmg
```

Der OpenAI API-Key wird nach dem Start direkt in der App unter **Optionen** eingegeben. Er bleibt nur für die laufende Sitzung im Arbeitsspeicher und wird weder in der App noch in einer Konfigurationsdatei gespeichert.

Die App ist zunächst nicht mit einem Apple-Developer-Zertifikat signiert oder notarisiert. Für die Nutzung auf dem eigenen Mac kann sie über Finder mit Rechtsklick und **Öffnen** gestartet werden. Für die Weitergabe an andere Nutzer sollte sie zusätzlich signiert und von Apple notarisiert werden.
