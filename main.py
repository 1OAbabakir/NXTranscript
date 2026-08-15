from openai import OpenAI
import os
from pathlib import Path
import subprocess
import tempfile

import imageio_ffmpeg


MAX_DIREKT_BYTES = 24 * 1024 * 1024
TEIL_LAENGE_SEKUNDEN = 20 * 60


def _fortschritt_melden(callback, nachricht):
    if callback:
        callback(nachricht)


def _feld(objekt, name, standard=None):
    if isinstance(objekt, dict):
        return objekt.get(name, standard)
    return getattr(objekt, name, standard)


def _transkribiere_datei(client, dateipfad):
    with open(dateipfad, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model="gpt-4o-transcribe-diarize",
            file=audio_file,
            language="de",
            response_format="diarized_json",
            chunking_strategy="auto",
        )

    segmente = []
    for segment in _feld(transcript, "segments", []) or []:
        segmente.append(
            {
                "start": float(_feld(segment, "start", 0.0)),
                "end": float(_feld(segment, "end", 0.0)),
                "speaker": str(_feld(segment, "speaker", "?")),
                "text": str(_feld(segment, "text", "")).strip(),
            }
        )

    dauer = float(_feld(transcript, "duration", 0.0) or 0.0)
    if not dauer and segmente:
        dauer = max(segment["end"] for segment in segmente)

    return segmente, dauer


def _zeit_formatieren(sekunden):
    gesamt = max(0, int(round(sekunden)))
    stunden, rest = divmod(gesamt, 3600)
    minuten, sekunden = divmod(rest, 60)
    return f"{stunden:02d}:{minuten:02d}:{sekunden:02d}"


def _transkript_formatieren(dateiname, segmente, dauer):
    zeilen = [
        f"Datei: {dateiname}",
        f"Dauer: {_zeit_formatieren(dauer)}",
        "",
    ]

    for segment in segmente:
        start = _zeit_formatieren(segment["start"])
        ende = _zeit_formatieren(segment["end"])
        sprecher = segment["speaker"].strip() or "?"
        text = segment["text"].strip()
        zeilen.append(f"[{start} – {ende}] Sprecher {sprecher}: {text}")

    return "\n".join(zeilen).strip()


def _audio_aufteilen(dateipfad, zielordner):
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    ausgabe_muster = str(Path(zielordner) / "teil_%03d.mp3")
    befehl = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(dateipfad),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "libmp3lame",
        "-b:a",
        "48k",
        "-f",
        "segment",
        "-segment_time",
        str(TEIL_LAENGE_SEKUNDEN),
        "-reset_timestamps",
        "1",
        ausgabe_muster,
    ]

    optionen = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }
    if os.name == "nt":
        optionen["creationflags"] = subprocess.CREATE_NO_WINDOW

    ergebnis = subprocess.run(befehl, **optionen)
    if ergebnis.returncode != 0:
        details = ergebnis.stderr.strip() or "Unbekannter FFmpeg-Fehler"
        raise RuntimeError(f"Die Audiodatei konnte nicht vorbereitet werden: {details}")

    teile = sorted(Path(zielordner).glob("teil_*.mp3"))
    if not teile:
        raise RuntimeError("Die Audiodatei konnte nicht in Abschnitte aufgeteilt werden.")

    if any(teil.stat().st_size > MAX_DIREKT_BYTES for teil in teile):
        raise RuntimeError("Ein vorbereiteter Audioabschnitt überschreitet weiterhin 24 MB.")

    return teile


def transkribiere_audio(dateipfad: str, api_key: str, fortschritt=None) -> str:
    """Transkribiert eine Audiodatei und teilt große Dateien automatisch auf."""
    dateipfad = Path(dateipfad)
    if not dateipfad.is_file():
        raise FileNotFoundError(f"Datei nicht gefunden: {dateipfad}")

    api_key = api_key.strip()
    if not api_key:
        raise RuntimeError("OpenAI API-Key fehlt.")

    client = OpenAI(api_key=api_key)

    try:
        if dateipfad.stat().st_size <= MAX_DIREKT_BYTES:
            _fortschritt_melden(
                fortschritt,
                "Sprecher und Zeitstempel werden erkannt …",
            )
            segmente, dauer = _transkribiere_datei(client, dateipfad)
            return _transkript_formatieren(dateipfad.name, segmente, dauer)

        groesse_mb = dateipfad.stat().st_size / (1024 * 1024)
        _fortschritt_melden(
            fortschritt,
            f"Datei ist {groesse_mb:.1f} MB groß und wird automatisch aufgeteilt …",
        )

        with tempfile.TemporaryDirectory(prefix="transkript-") as temp_ordner:
            teile = _audio_aufteilen(dateipfad, temp_ordner)
            alle_segmente = []
            zeit_offset = 0.0

            for nummer, teil in enumerate(teile, start=1):
                _fortschritt_melden(
                    fortschritt,
                    f"Teil {nummer} von {len(teile)}: Sprecher und Zeiten werden erkannt …",
                )
                segmente, dauer = _transkribiere_datei(client, teil)
                for segment in segmente:
                    alle_segmente.append(
                        {
                            **segment,
                            "start": segment["start"] + zeit_offset,
                            "end": segment["end"] + zeit_offset,
                        }
                    )
                zeit_offset += dauer

        return _transkript_formatieren(dateipfad.name, alle_segmente, zeit_offset)
    except Exception as e:
        if isinstance(e, RuntimeError):
            raise
        raise RuntimeError(f"Fehler bei der Transkription: {e}") from e


if __name__ == "__main__":
    import argparse
    import getpass

    parser = argparse.ArgumentParser(
        description="Transkribiere eine Audiodatei mit Sprechern und Zeitstempeln."
    )
    parser.add_argument("-d", "--datei", required=True, help="Pfad zur Audiodatei")
    parser.add_argument("-o", "--output", default="transkription.txt", help="Pfad zur Ausgabedatei")
    args = parser.parse_args()

    api_key = getpass.getpass("OpenAI API-Key: ")
    text = transkribiere_audio(args.datei, api_key, print)

    print("Transkription:\n", text)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(text)

    print(f"\n✅ Transkription gespeichert in: {os.path.abspath(args.output)}")
