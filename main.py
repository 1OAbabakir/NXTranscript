from __future__ import annotations

import base64
import math
import os
import re
import subprocess
import tempfile
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from difflib import SequenceMatcher
from itertools import pairwise
from pathlib import Path
from typing import Any

import imageio_ffmpeg
from openai import OpenAI

# Die API akzeptiert Dateien bis 25 MB. Dezimale 24 MB lassen ausreichend Reserve
# für unterschiedliche MB-Definitionen und Multipart-Metadaten.
MAX_REQUEST_BYTES = 24_000_000
ZIEL_REQUEST_BYTES = 23_000_000

# Ein dicht gesprochenes zehnminütiges Gespräch kann bereits an das Textlimit des
# Diarisierungsmodells kommen. Daher begrenzen wir nicht nur nach Dateigröße.
MAX_TEIL_DAUER_SEKUNDEN = 10 * 60
MIN_TEIL_DAUER_SEKUNDEN = 60
SCHNITT_SUCHE_SEKUNDEN = 90
TEIL_UEBERLAPPUNG_SEKUNDEN = 1.0

AUDIO_BITRATE = "48k"
SPRACHBLOCK_MAX_SEKUNDEN = 90
SPRACHBLOCK_MAX_LUECKE_SEKUNDEN = 1.25
ZEITANKER_MAX_SEKUNDEN = 10.0
UNTERTITEL_MAX_SEKUNDEN = 8.0
UNTERTITEL_MAX_ZEICHEN = 110
UNTERTITEL_MAX_WOERTER = 20
UNTERTITEL_PAUSE_SEKUNDEN = 0.65
MAX_PARALLELE_SPRACHREQUESTS = 3
ERWARTETE_SPRACHEN = ("de", "fa")

MEHRSPRACHEN_PROMPT = (
    "Zweisprachiges Gespräch auf Deutsch und فارسی. "
    "Jede Passage wortgetreu in der tatsächlich gesprochenen Sprache schreiben; "
    "Persisch in persischer Schrift und Deutsch in deutscher Schrift. "
    "Nicht übersetzen und keine Inhalte ergänzen."
)

FortschrittCallback = Callable[[str], None] | None


@dataclass(frozen=True)
class AudioTeil:
    pfad: Path
    audio_start: float
    audio_ende: float
    behalten_start: float
    behalten_ende: float


@dataclass(frozen=True)
class Zeitanker:
    start: float
    ende: float
    fallback_text: str


@dataclass(frozen=True)
class Sprachblock:
    start: float
    ende: float
    speaker: str
    fallback_text: str
    zeitanker: tuple[Zeitanker, ...]


def _fortschritt_melden(callback: FortschrittCallback, nachricht: str) -> None:
    if callback:
        callback(nachricht)


def _feld(objekt: Any, name: str, standard: Any = None) -> Any:
    if isinstance(objekt, dict):
        return objekt.get(name, standard)
    return getattr(objekt, name, standard)


def _subprocess_optionen() -> dict[str, Any]:
    optionen: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }
    if os.name == "nt":
        optionen["creationflags"] = subprocess.CREATE_NO_WINDOW
    return optionen


def _ffmpeg_ausfuehren(
    befehl: list[str], fehlermeldung: str
) -> subprocess.CompletedProcess:
    ergebnis = subprocess.run(befehl, check=False, **_subprocess_optionen())
    if ergebnis.returncode != 0:
        details = ergebnis.stderr.strip() or "Unbekannter FFmpeg-Fehler"
        raise RuntimeError(f"{fehlermeldung}: {details}")
    return ergebnis


def _zeitwert_lesen(wert: str) -> float:
    stunden, minuten, sekunden = wert.strip().split(":")
    return int(stunden) * 3600 + int(minuten) * 60 + float(sekunden)


def _dauer_aus_ffmpeg(ausgabe: str) -> float:
    fortschritt = re.findall(
        r"^out_time=(\d{2}:\d{2}:\d{2}(?:\.\d+)?)$", ausgabe, re.MULTILINE
    )
    if fortschritt:
        return _zeitwert_lesen(fortschritt[-1])

    treffer = re.search(r"Duration:\s*(\d{2}:\d{2}:\d{2}(?:\.\d+)?)", ausgabe)
    return _zeitwert_lesen(treffer.group(1)) if treffer else 0.0


def _stille_enden_aus_ffmpeg(ausgabe: str) -> list[float]:
    return [
        float(wert)
        for wert in re.findall(r"silence_end:\s*(-?\d+(?:\.\d+)?)", ausgabe)
        if float(wert) > 0
    ]


def _audio_normalisieren(
    dateipfad: Path, zielordner: Path
) -> tuple[Path, float, list[float]]:
    """Erzeugt ein berechenbares Mono-MP3 und erkennt dabei geeignete Sprechpausen."""
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    ausgabe = zielordner / "normalisiert.mp3"
    befehl = [
        ffmpeg,
        "-hide_banner",
        "-nostats",
        "-y",
        "-i",
        str(dateipfad),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-af",
        "silencedetect=noise=-35dB:d=0.6",
        "-c:a",
        "libmp3lame",
        "-b:a",
        AUDIO_BITRATE,
        "-progress",
        "pipe:1",
        str(ausgabe),
    ]
    ergebnis = _ffmpeg_ausfuehren(
        befehl,
        "Die Audiodatei konnte nicht normalisiert werden",
    )

    dauer = _dauer_aus_ffmpeg(ergebnis.stdout) or _dauer_aus_ffmpeg(ergebnis.stderr)
    if dauer <= 0:
        raise RuntimeError("Die Dauer der Audiodatei konnte nicht bestimmt werden.")
    if not ausgabe.is_file() or ausgabe.stat().st_size == 0:
        raise RuntimeError("FFmpeg hat keine normalisierte Audiodatei erzeugt.")

    return ausgabe, dauer, _stille_enden_aus_ffmpeg(ergebnis.stderr)


def _maximale_teildauer(dauer: float, dateigroesse: int) -> float:
    if dauer <= 0 or dateigroesse <= 0:
        return float(MAX_TEIL_DAUER_SEKUNDEN)
    bytes_pro_sekunde = dateigroesse / dauer
    byte_limit_dauer = ZIEL_REQUEST_BYTES / bytes_pro_sekunde
    return max(
        float(MIN_TEIL_DAUER_SEKUNDEN),
        min(float(MAX_TEIL_DAUER_SEKUNDEN), byte_limit_dauer),
    )


def _schnittpunkte_planen(
    dauer: float,
    stille_enden: Iterable[float],
    maximale_dauer: float,
) -> list[float]:
    """Plant ausgeglichene Teile und verschiebt Schnitte zu nahen Sprechpausen."""
    if dauer <= maximale_dauer:
        return [0.0, dauer]

    anzahl = max(1, math.ceil(dauer / maximale_dauer))
    ideale_laenge = dauer / anzahl
    pausen = sorted({float(wert) for wert in stille_enden if 0 < wert < dauer})
    punkte = [0.0]

    for index in range(1, anzahl):
        ziel = index * ideale_laenge
        restliche_teile = anzahl - index
        minimum = max(
            punkte[-1] + MIN_TEIL_DAUER_SEKUNDEN,
            ziel - SCHNITT_SUCHE_SEKUNDEN,
        )
        maximum = min(
            punkte[-1] + maximale_dauer,
            dauer - restliche_teile * MIN_TEIL_DAUER_SEKUNDEN,
            ziel + SCHNITT_SUCHE_SEKUNDEN,
        )
        kandidaten = [pause for pause in pausen if minimum <= pause <= maximum]
        schnitt = (
            min(kandidaten, key=lambda pause: abs(pause - ziel)) if kandidaten else ziel
        )
        punkte.append(max(punkte[-1], min(schnitt, dauer)))

    punkte.append(dauer)
    return punkte


def _audioabschnitt_exportieren(
    quellpfad: Path,
    zielpfad: Path,
    start: float,
    ende: float,
) -> None:
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    befehl = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{start:.3f}",
        "-i",
        str(quellpfad),
        "-t",
        f"{max(0.05, ende - start):.3f}",
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "libmp3lame",
        "-b:a",
        AUDIO_BITRATE,
        str(zielpfad),
    ]
    _ffmpeg_ausfuehren(befehl, "Ein Audioabschnitt konnte nicht erzeugt werden")


def _audio_aufteilen(
    normalisiert: Path,
    zielordner: Path,
    dauer: float,
    stille_enden: Iterable[float],
) -> list[AudioTeil]:
    max_dauer = _maximale_teildauer(dauer, normalisiert.stat().st_size)
    schnittpunkte = _schnittpunkte_planen(dauer, stille_enden, max_dauer)
    teile: list[AudioTeil] = []

    for index, (behalten_start, behalten_ende) in enumerate(
        pairwise(schnittpunkte),
        start=1,
    ):
        audio_start = max(0.0, behalten_start - TEIL_UEBERLAPPUNG_SEKUNDEN)
        audio_ende = min(dauer, behalten_ende + TEIL_UEBERLAPPUNG_SEKUNDEN)
        teilpfad = zielordner / f"teil_{index:03d}.mp3"
        _audioabschnitt_exportieren(normalisiert, teilpfad, audio_start, audio_ende)
        groesse = teilpfad.stat().st_size
        if groesse > MAX_REQUEST_BYTES:
            raise RuntimeError(
                f"Audioabschnitt {index} ist mit {groesse / 1_000_000:.1f} MB noch zu groß."
            )
        teile.append(
            AudioTeil(
                pfad=teilpfad,
                audio_start=audio_start,
                audio_ende=audio_ende,
                behalten_start=behalten_start,
                behalten_ende=behalten_ende,
            )
        )

    return teile


def _diarisiere_datei(
    client: OpenAI,
    dateipfad: Path,
    sprecherreferenzen: dict[str, str],
) -> tuple[list[dict[str, Any]], float]:
    parameter: dict[str, Any] = {
        "model": "gpt-4o-transcribe-diarize",
        "file": None,
        "response_format": "diarized_json",
        "chunking_strategy": "auto",
    }
    if sprecherreferenzen:
        parameter["known_speaker_names"] = list(sprecherreferenzen)
        parameter["known_speaker_references"] = list(sprecherreferenzen.values())

    with dateipfad.open("rb") as audio_file:
        parameter["file"] = audio_file
        transcript = client.audio.transcriptions.create(**parameter)

    segmente = []
    for segment in _feld(transcript, "segments", []) or []:
        text = str(_feld(segment, "text", "")).strip()
        start = float(_feld(segment, "start", 0.0) or 0.0)
        ende = float(_feld(segment, "end", start) or start)
        if text and ende > start:
            segmente.append(
                {
                    "start": start,
                    "end": ende,
                    "speaker": str(_feld(segment, "speaker", "?")).strip() or "?",
                    "text": text,
                }
            )

    dauer = float(_feld(transcript, "duration", 0.0) or 0.0)
    if not dauer and segmente:
        dauer = max(segment["end"] for segment in segmente)
    return segmente, dauer


def _sprecher_nummer(name: str) -> int | None:
    treffer = re.fullmatch(r"speaker_(\d+)", name)
    return int(treffer.group(1)) if treffer else None


def _sprecher_globalisieren(
    segmente: list[dict[str, Any]],
    bekannte_namen: set[str],
    vorherige_segmente: list[dict[str, Any]],
    grenze: float,
    naechste_nummer: int,
) -> tuple[list[dict[str, Any]], int]:
    lokale_zuordnung: dict[str, str] = {}
    bekannte_klein = {name.casefold(): name for name in bekannte_namen}

    # Bei überlappenden Chunkrändern kann derselbe Sprecher zeitlich zugeordnet werden.
    for segment in segmente:
        lokal = segment["speaker"]
        if lokal.casefold() in bekannte_klein:
            lokale_zuordnung[lokal] = bekannte_klein[lokal.casefold()]
            continue
        if lokal in lokale_zuordnung:
            continue

        beste_ueberlappung = 0.0
        bester_name = None
        if segment["start"] <= grenze + TEIL_UEBERLAPPUNG_SEKUNDEN:
            for vorherig in vorherige_segmente:
                if vorherig["end"] < grenze - TEIL_UEBERLAPPUNG_SEKUNDEN:
                    continue
                ueberlappung = min(segment["end"], vorherig["end"]) - max(
                    segment["start"], vorherig["start"]
                )
                if ueberlappung > beste_ueberlappung:
                    beste_ueberlappung = ueberlappung
                    bester_name = vorherig["speaker"]
        if bester_name and beste_ueberlappung >= 0.2:
            lokale_zuordnung[lokal] = bester_name

    for segment in segmente:
        lokal = segment["speaker"]
        if lokal not in lokale_zuordnung:
            lokale_zuordnung[lokal] = f"speaker_{naechste_nummer}"
            naechste_nummer += 1
        segment["speaker"] = lokale_zuordnung[lokal]

    return segmente, naechste_nummer


def _segment_ist_im_hauptbereich(segment: dict[str, Any], teil: AudioTeil) -> bool:
    mitte = (segment["start"] + segment["end"]) / 2
    ist_letztes_ende = math.isclose(teil.behalten_ende, teil.audio_ende, abs_tol=0.01)
    return teil.behalten_start <= mitte and (
        mitte < teil.behalten_ende or (ist_letztes_ende and mitte <= teil.behalten_ende)
    )


def _referenz_data_url(
    normalisiert: Path,
    zielordner: Path,
    name: str,
    segment: dict[str, Any],
) -> str:
    dauer = min(8.0, segment["end"] - segment["start"])
    start = segment["start"] + max(0.0, (segment["end"] - segment["start"] - dauer) / 2)
    referenzpfad = zielordner / f"referenz_{name}.mp3"
    _audioabschnitt_exportieren(normalisiert, referenzpfad, start, start + dauer)
    daten = base64.b64encode(referenzpfad.read_bytes()).decode("ascii")
    return f"data:audio/mpeg;base64,{daten}"


def _sprecherreferenzen_ergaenzen(
    normalisiert: Path,
    zielordner: Path,
    segmente: list[dict[str, Any]],
    referenzen: dict[str, str],
) -> None:
    if len(referenzen) >= 4:
        return
    kandidaten = sorted(
        (
            segment
            for segment in segmente
            if segment["speaker"] not in referenzen
            and segment["end"] - segment["start"] >= 2.0
        ),
        key=lambda segment: segment["end"] - segment["start"],
        reverse=True,
    )
    for segment in kandidaten:
        name = segment["speaker"]
        if name in referenzen:
            continue
        referenzen[name] = _referenz_data_url(normalisiert, zielordner, name, segment)
        if len(referenzen) >= 4:
            break


def _zeitanker_fuer_segment(
    segment: dict[str, Any], _stille_enden: Iterable[float]
) -> list[Zeitanker]:
    start = float(segment["start"])
    ende = float(segment["end"])
    dauer = max(0.0, ende - start)
    if dauer <= ZEITANKER_MAX_SEKUNDEN:
        return [Zeitanker(start, ende, str(segment.get("text", "")))]

    anzahl = math.ceil(dauer / ZEITANKER_MAX_SEKUNDEN)
    grenzen = [start + index * dauer / anzahl for index in range(anzahl)]
    grenzen.append(ende)

    text = str(segment.get("text", "")).strip()
    woerter = text.split()
    anker: list[Zeitanker] = []
    for index, (anker_start, anker_ende) in enumerate(pairwise(grenzen)):
        wort_start = round((anker_start - start) / dauer * len(woerter))
        wort_ende = round((anker_ende - start) / dauer * len(woerter))
        if index == len(grenzen) - 2:
            wort_ende = len(woerter)
        anker.append(
            Zeitanker(
                anker_start,
                anker_ende,
                " ".join(woerter[wort_start:wort_ende]),
            )
        )
    return anker


def _sprachbloecke_bilden(
    segmente: list[dict[str, Any]], stille_enden: Iterable[float] = ()
) -> list[Sprachblock]:
    vorbereitete_segmente: list[dict[str, Any]] = []
    for segment in segmente:
        for anker in _zeitanker_fuer_segment(segment, stille_enden):
            vorbereitete_segmente.append(
                {
                    **segment,
                    "start": anker.start,
                    "end": anker.ende,
                    "text": anker.fallback_text,
                    "zeitanker": anker,
                }
            )

    bloecke: list[Sprachblock] = []
    for segment in sorted(
        vorbereitete_segmente,
        key=lambda eintrag: (eintrag["start"], eintrag["end"]),
    ):
        if not bloecke:
            bloecke.append(
                Sprachblock(
                    segment["start"],
                    segment["end"],
                    segment["speaker"],
                    segment["text"],
                    (segment["zeitanker"],),
                )
            )
            continue

        vorherig = bloecke[-1]
        luecke = segment["start"] - vorherig.ende
        gemeinsame_dauer = segment["end"] - vorherig.start
        if (
            segment["speaker"] == vorherig.speaker
            and luecke <= SPRACHBLOCK_MAX_LUECKE_SEKUNDEN
            and gemeinsame_dauer <= SPRACHBLOCK_MAX_SEKUNDEN
        ):
            bloecke[-1] = Sprachblock(
                start=vorherig.start,
                ende=max(vorherig.ende, segment["end"]),
                speaker=vorherig.speaker,
                fallback_text=" ".join(
                    text for text in (vorherig.fallback_text, segment["text"]) if text
                ),
                zeitanker=vorherig.zeitanker + (segment["zeitanker"],),
            )
        else:
            bloecke.append(
                Sprachblock(
                    segment["start"],
                    segment["end"],
                    segment["speaker"],
                    segment["text"],
                    (segment["zeitanker"],),
                )
            )
    return bloecke


def _text_auf_zeitanker_verteilen(
    block: Sprachblock, text: str, sprachen: list[str]
) -> list[dict[str, Any]]:
    tokens = text.split()
    if not tokens:
        return []
    dauer = max(0.01, block.ende - block.start)
    geschaetzte_zeiten = [
        {
            "start": index * dauer / len(tokens),
            "end": (index + 1) * dauer / len(tokens),
            "word": token,
        }
        for index, token in enumerate(tokens)
    ]
    return _guten_text_mit_wortzeiten_abgleichen(
        block, text, sprachen, geschaetzte_zeiten
    )


def _sprachblock_transkribieren(
    client: OpenAI, dateipfad: Path
) -> tuple[str, list[str]]:
    with dateipfad.open("rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model="gpt-transcribe",
            file=audio_file,
            prompt=MEHRSPRACHEN_PROMPT,
            languages=list(ERWARTETE_SPRACHEN),
        )

    sprachen = []
    for sprache in _feld(transcript, "languages", []) or []:
        code = str(_feld(sprache, "code", "")).strip()
        if code:
            sprachen.append(code)
    return str(_feld(transcript, "text", "")).strip(), sprachen


def _wortzeiten_erkennen(client: OpenAI, dateipfad: Path) -> list[dict[str, Any]]:
    with dateipfad.open("rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="verbose_json",
            timestamp_granularities=["word"],
        )
    wortzeiten = []
    for wort in _feld(transcript, "words", []) or []:
        worttext = str(_feld(wort, "word", "")).strip()
        start = float(_feld(wort, "start", 0.0))
        ende = float(_feld(wort, "end", start))
        if worttext and ende >= start:
            wortzeiten.append({"start": start, "end": ende, "word": worttext})
    return wortzeiten


def _token_normalisieren(token: str) -> str:
    token = token.casefold().replace("ي", "ی").replace("ك", "ک").replace("‌", "")
    return "".join(zeichen for zeichen in token if zeichen.isalnum())


def _zeitindizes_abgleichen(gute_tokens: list[str], zeit_tokens: list[str]) -> list[int]:
    if not gute_tokens or not zeit_tokens:
        return []
    gute_normalisiert = [_token_normalisieren(token) for token in gute_tokens]
    zeit_normalisiert = [_token_normalisieren(token) for token in zeit_tokens]
    zuordnung: list[int | None] = [None] * len(gute_tokens)
    for block in SequenceMatcher(
        None, gute_normalisiert, zeit_normalisiert, autojunk=False
    ).get_matching_blocks():
        for versatz in range(block.size):
            zuordnung[block.a + versatz] = block.b + versatz

    bekannte = [(-1, -1)]
    bekannte.extend(
        (index, zeitindex)
        for index, zeitindex in enumerate(zuordnung)
        if zeitindex is not None
    )
    bekannte.append((len(gute_tokens), len(zeit_tokens)))
    for (links_text, links_zeit), (rechts_text, rechts_zeit) in pairwise(bekannte):
        textspanne = rechts_text - links_text
        for index in range(links_text + 1, rechts_text):
            anteil = (index - links_text) / textspanne
            zeitindex = round(links_zeit + anteil * (rechts_zeit - links_zeit))
            zuordnung[index] = min(len(zeit_tokens) - 1, max(0, zeitindex))
    return [int(index) for index in zuordnung]


def _schrift_von_token(token: str) -> str | None:
    if re.search(r"[\u0600-\u06ff]", token):
        return "fa"
    if re.search(r"[A-Za-zÄÖÜäöüß]", token):
        return "de"
    return None


def _guten_text_mit_wortzeiten_abgleichen(
    block: Sprachblock,
    text: str,
    sprachen: list[str],
    wortzeiten: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    tokens = text.split()
    if not tokens or not wortzeiten:
        return []

    zeit_tokens = [str(wortzeit["word"]) for wortzeit in wortzeiten]
    zeitindizes = _zeitindizes_abgleichen(tokens, zeit_tokens)
    getaktete_tokens: list[dict[str, Any]] = []
    for token, zeitindex in zip(tokens, zeitindizes):
        wortzeit = wortzeiten[zeitindex]
        start = min(
            block.ende,
            max(block.start, block.start + float(wortzeit["start"])),
        )
        ende = min(
            block.ende,
            max(start, block.start + float(wortzeit["end"])),
        )
        getaktete_tokens.append({"text": token, "start": start, "end": ende})

    satzende = re.compile(r"[.!?؟]+[\"'»”)]*$")
    segmente: list[dict[str, Any]] = []
    gruppe: list[dict[str, Any]] = []
    for index, token in enumerate(getaktete_tokens):
        gruppe.append(token)
        ist_letztes = index == len(getaktete_tokens) - 1
        if ist_letztes:
            abschliessen = True
        else:
            naechstes = getaktete_tokens[index + 1]
            dauer = float(token["end"]) - float(gruppe[0]["start"])
            pause = float(naechstes["start"]) - float(token["end"])
            zeichen = sum(len(str(eintrag["text"])) for eintrag in gruppe)
            aktuelle_schrift = _schrift_von_token(str(token["text"]))
            naechste_schrift = _schrift_von_token(str(naechstes["text"]))
            sprachwechsel = (
                aktuelle_schrift is not None
                and naechste_schrift is not None
                and aktuelle_schrift != naechste_schrift
            )
            abschliessen = (
                (bool(satzende.search(str(token["text"]))) and len(gruppe) >= 2)
                or (pause >= UNTERTITEL_PAUSE_SEKUNDEN and len(gruppe) >= 2)
                or dauer >= UNTERTITEL_MAX_SEKUNDEN
                or zeichen >= UNTERTITEL_MAX_ZEICHEN
                or len(gruppe) >= UNTERTITEL_MAX_WOERTER
                or (sprachwechsel and dauer >= 1.5 and len(gruppe) >= 4)
            )
        if abschliessen:
            segmente.append(
                {
                    "start": float(gruppe[0]["start"]),
                    "end": float(gruppe[-1]["end"]),
                    "speaker": block.speaker,
                    "text": " ".join(str(eintrag["text"]) for eintrag in gruppe),
                    "languages": sprachen,
                }
            )
            gruppe = []

    if len(segmente) >= 2:
        letzter = segmente[-1]
        if (
            len(letzter["text"].split()) <= 2
            and letzter["end"] - letzter["start"] < 1
            and not satzende.search(letzter["text"])
        ):
            vorheriger = segmente[-2]
            vorheriger["text"] = f"{vorheriger['text']} {letzter['text']}"
            vorheriger["end"] = letzter["end"]
            segmente.pop()
    return segmente


def _sprachbloecke_transkribieren(
    client: OpenAI,
    normalisiert: Path,
    zielordner: Path,
    bloecke: list[Sprachblock],
    fortschritt: FortschrittCallback,
) -> tuple[list[dict[str, Any]], list[str]]:
    dateien: list[Path] = []
    for index, block in enumerate(bloecke, start=1):
        blockpfad = zielordner / f"sprachblock_{index:04d}.mp3"
        _audioabschnitt_exportieren(normalisiert, blockpfad, block.start, block.ende)
        if blockpfad.stat().st_size > MAX_REQUEST_BYTES:
            raise RuntimeError(f"Sprachblock {index} überschreitet das Uploadlimit.")
        dateien.append(blockpfad)

    text_ergebnisse: list[tuple[str, list[str]] | Exception | None] = [None] * len(
        bloecke
    )
    zeit_ergebnisse: list[list[dict[str, Any]] | Exception | None] = [None] * len(
        bloecke
    )
    worker = min(MAX_PARALLELE_SPRACHREQUESTS, max(1, len(bloecke)))
    with ThreadPoolExecutor(max_workers=worker) as executor:
        aufgaben = {
            executor.submit(_sprachblock_transkribieren, client, datei): index
            for index, datei in enumerate(dateien)
        }
        for erledigt, aufgabe in enumerate(as_completed(aufgaben), start=1):
            index = aufgaben[aufgabe]
            try:
                text_ergebnisse[index] = aufgabe.result()
            except Exception as fehler:  # noqa: BLE001 - Fallback soll jeden Requestfehler abfangen.
                text_ergebnisse[index] = fehler
            _fortschritt_melden(
                fortschritt,
                f"Pipeline 1/3 – Deutsch/Persisch: {erledigt} von {len(bloecke)} …",
            )

    with ThreadPoolExecutor(max_workers=worker) as executor:
        aufgaben = {
            executor.submit(_wortzeiten_erkennen, client, datei): index
            for index, datei in enumerate(dateien)
        }
        for erledigt, aufgabe in enumerate(as_completed(aufgaben), start=1):
            index = aufgaben[aufgabe]
            try:
                zeit_ergebnisse[index] = aufgabe.result()
            except Exception as fehler:  # noqa: BLE001 - lokaler Timing-Fallback.
                zeit_ergebnisse[index] = fehler
            _fortschritt_melden(
                fortschritt,
                f"Pipeline 2/3 – Wortzeiten: {erledigt} von {len(bloecke)} …",
            )

    segmente: list[dict[str, Any]] = []
    hinweise: list[str] = []
    _fortschritt_melden(fortschritt, "Pipeline 3/3 – Text und Wortzeiten abgleichen …")
    for index, (block, text_ergebnis, zeit_ergebnis) in enumerate(
        zip(bloecke, text_ergebnisse, zeit_ergebnisse), start=1
    ):
        if isinstance(text_ergebnis, Exception) or text_ergebnis is None:
            text = block.fallback_text
            details = str(text_ergebnis) if text_ergebnis else "unbekannter Fehler"
            hinweise.append(f"Sprachblock {index} wurde nicht verfeinert: {details}")
            sprachen: list[str] = []
        else:
            text, sprachen = text_ergebnis
            text = text or block.fallback_text
        if isinstance(zeit_ergebnis, Exception) or not zeit_ergebnis:
            segmente.extend(_text_auf_zeitanker_verteilen(block, text, sprachen))
            details = str(zeit_ergebnis) if zeit_ergebnis else "keine Wortzeiten"
            hinweise.append(f"Sprachblock {index} nutzt geschätzte Zeiten: {details}")
        else:
            segmente.extend(
                _guten_text_mit_wortzeiten_abgleichen(
                    block, text, sprachen, zeit_ergebnis
                )
            )
    return segmente, hinweise


def _zeit_formatieren(sekunden: float) -> str:
    gesamt = max(0, round(sekunden))
    stunden, rest = divmod(gesamt, 3600)
    minuten, sekunden = divmod(rest, 60)
    return f"{stunden:02d}:{minuten:02d}:{sekunden:02d}"


def _sprecher_anzeigen(speaker: str) -> str:
    nummer = _sprecher_nummer(speaker)
    return str(nummer) if nummer is not None else (speaker.strip() or "?")


def _transkript_formatieren(
    dateiname: str,
    segmente: list[dict[str, Any]],
    dauer: float,
    hinweise: list[str] | None = None,
) -> str:
    zeilen = [
        f"Datei: {dateiname}",
        f"Dauer: {_zeit_formatieren(dauer)}",
        "Sprachen: Deutsch und Persisch",
    ]
    if hinweise:
        zeilen.extend(["", f"Hinweis: {len(hinweise)} Verarbeitungshinweis(e)."])
    zeilen.append("")

    for segment in sorted(segmente, key=lambda eintrag: (eintrag["start"], eintrag["end"])):
        text = segment["text"].strip()
        if not text:
            continue
        start_sekunde = max(0, math.floor(float(segment["start"])))
        ende_sekunde = max(start_sekunde + 1, math.ceil(float(segment["end"])))
        start = _zeit_formatieren(start_sekunde)
        ende = _zeit_formatieren(ende_sekunde)
        sprecher = _sprecher_anzeigen(segment["speaker"])
        zeilen.append(f"[{start} – {ende}] Sprecher {sprecher}: {text}")

    return "\n".join(zeilen).strip()


def transkribiere_audio(
    dateipfad: str, api_key: str, fortschritt: FortschrittCallback = None
) -> str:
    """Transkribiert deutsche und persische Passagen mit Sprechern und Zeitstempeln."""
    quellpfad = Path(dateipfad)
    if not quellpfad.is_file():
        raise FileNotFoundError(f"Datei nicht gefunden: {quellpfad}")

    api_key = api_key.strip()
    if not api_key:
        raise RuntimeError("OpenAI API-Key fehlt.")

    client = OpenAI(api_key=api_key)

    try:
        with tempfile.TemporaryDirectory(prefix="transkript-") as temp_name:
            temp_ordner = Path(temp_name)
            _fortschritt_melden(
                fortschritt, "Audio wird normalisiert und auf Sprechpausen geprüft …"
            )
            normalisiert, dauer, stille_enden = _audio_normalisieren(
                quellpfad, temp_ordner
            )
            teile = _audio_aufteilen(normalisiert, temp_ordner, dauer, stille_enden)
            _fortschritt_melden(
                fortschritt,
                f"Audio wurde in {len(teile)} sicheren Abschnitt(e) eingeteilt.",
            )

            alle_segmente: list[dict[str, Any]] = []
            referenzen: dict[str, str] = {}
            naechste_sprechernummer = 1

            for nummer, teil in enumerate(teile, start=1):
                _fortschritt_melden(
                    fortschritt,
                    f"Teil {nummer} von {len(teile)}: Sprecher und Zeiten erkennen …",
                )
                lokale_segmente, _ = _diarisiere_datei(client, teil.pfad, referenzen)
                absolute_segmente = [
                    {
                        **segment,
                        "start": segment["start"] + teil.audio_start,
                        "end": segment["end"] + teil.audio_start,
                    }
                    for segment in lokale_segmente
                ]
                absolute_segmente, naechste_sprechernummer = _sprecher_globalisieren(
                    absolute_segmente,
                    set(referenzen),
                    alle_segmente,
                    teil.behalten_start,
                    naechste_sprechernummer,
                )
                hauptsegmente = [
                    segment
                    for segment in absolute_segmente
                    if _segment_ist_im_hauptbereich(segment, teil)
                ]
                alle_segmente.extend(hauptsegmente)
                _sprecherreferenzen_ergaenzen(
                    normalisiert,
                    temp_ordner,
                    hauptsegmente,
                    referenzen,
                )

            if not alle_segmente:
                raise RuntimeError("Die API hat keine gesprochenen Abschnitte erkannt.")

            bloecke = _sprachbloecke_bilden(alle_segmente, stille_enden)
            _fortschritt_melden(
                fortschritt,
                f"{len(bloecke)} Sprecherabschnitt(e) werden für Deutsch/Persisch verfeinert …",
            )
            genaue_segmente, hinweise = _sprachbloecke_transkribieren(
                client,
                normalisiert,
                temp_ordner,
                bloecke,
                fortschritt,
            )

        return _transkript_formatieren(quellpfad.name, genaue_segmente, dauer, hinweise)
    except Exception as fehler:
        if isinstance(fehler, (RuntimeError, FileNotFoundError)):
            raise
        raise RuntimeError(f"Fehler bei der Transkription: {fehler}") from fehler


if __name__ == "__main__":
    import argparse
    import getpass

    parser = argparse.ArgumentParser(
        description="Transkribiere Deutsch und Persisch mit Sprechern und Zeitstempeln."
    )
    parser.add_argument("-d", "--datei", required=True, help="Pfad zur Audiodatei")
    parser.add_argument(
        "-o", "--output", default="transkription.txt", help="Pfad zur Ausgabedatei"
    )
    args = parser.parse_args()

    schluessel = getpass.getpass("OpenAI API-Key: ")
    ausgabe_text = transkribiere_audio(args.datei, schluessel, print)

    print("Transkription:\n", ausgabe_text)
    with open(args.output, "w", encoding="utf-8") as ausgabedatei:
        ausgabedatei.write(ausgabe_text)
    print(f"\n✅ Transkription gespeichert in: {os.path.abspath(args.output)}")
