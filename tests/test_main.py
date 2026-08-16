import math
import tempfile
import unittest
import wave
from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace

import main


class FakeTranscriptions:
    def __init__(self, antwort):
        self.antwort = antwort
        self.aufrufe = []

    def create(self, **parameter):
        self.aufrufe.append(parameter)
        return self.antwort


class FakeClient:
    def __init__(self, antwort):
        self.audio = SimpleNamespace(transcriptions=FakeTranscriptions(antwort))


class AudioPlanTests(unittest.TestCase):
    def test_ffmpeg_dauer_und_stille_werden_gelesen(self):
        self.assertAlmostEqual(
            main._dauer_aus_ffmpeg("out_time=00:02:03.500000\n"), 123.5
        )
        self.assertEqual(
            main._stille_enden_aus_ffmpeg("silence_end: 12.4 | x\nsilence_end: 42.0"),
            [12.4, 42.0],
        )

    def test_schnittpunkte_sind_ausgeglichen_und_liegen_an_pausen(self):
        punkte = main._schnittpunkte_planen(
            dauer=1300,
            stille_enden=[425, 438, 860, 875],
            maximale_dauer=600,
        )
        self.assertEqual(punkte, [0.0, 438.0, 860.0, 1300])
        self.assertTrue(all(ende - start <= 600 for start, ende in pairwise(punkte)))

    def test_byte_limit_begrenzt_maximale_dauer(self):
        dauer = main._maximale_teildauer(dauer=600, dateigroesse=46_000_000)
        self.assertAlmostEqual(dauer, 300.0)

    def test_normalisierung_und_export_laufen_mit_ffmpeg(self):
        with tempfile.TemporaryDirectory() as temp_name:
            temp = Path(temp_name)
            quelle = temp / "test.wav"
            samplerate = 16_000
            with wave.open(str(quelle), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(samplerate)
                frames = bytearray()
                for index in range(samplerate * 2):
                    wert = (
                        0
                        if index < samplerate
                        else int(
                            4000 * math.sin(2 * math.pi * 440 * index / samplerate)
                        )
                    )
                    frames.extend(
                        int(wert).to_bytes(2, byteorder="little", signed=True)
                    )
                wav.writeframes(frames)

            normalisiert, dauer, stille = main._audio_normalisieren(quelle, temp)
            self.assertTrue(normalisiert.is_file())
            self.assertAlmostEqual(dauer, 2.0, delta=0.1)
            self.assertTrue(stille)
            teile = main._audio_aufteilen(normalisiert, temp, dauer, stille)
            self.assertEqual(len(teile), 1)
            self.assertLess(teile[0].pfad.stat().st_size, main.MAX_REQUEST_BYTES)


class SprecherTests(unittest.TestCase):
    def test_bekannte_und_ueberlappende_sprecher_bleiben_stabil(self):
        vorherige = [
            {"start": 98.0, "end": 100.8, "speaker": "speaker_2", "text": "vorher"}
        ]
        segmente = [
            {"start": 99.5, "end": 101.0, "speaker": "A", "text": "weiter"},
            {"start": 102.0, "end": 104.0, "speaker": "speaker_1", "text": "bekannt"},
            {"start": 105.0, "end": 107.0, "speaker": "B", "text": "neu"},
        ]
        ergebnis, nummer = main._sprecher_globalisieren(
            segmente,
            bekannte_namen={"speaker_1"},
            vorherige_segmente=vorherige,
            grenze=100.0,
            naechste_nummer=3,
        )
        self.assertEqual(
            [segment["speaker"] for segment in ergebnis],
            ["speaker_2", "speaker_1", "speaker_3"],
        )
        self.assertEqual(nummer, 4)

    def test_chunk_ueberlappung_wird_nur_einmal_behalten(self):
        erster = main.AudioTeil(Path("eins.mp3"), 0, 101, 0, 100)
        zweiter = main.AudioTeil(Path("zwei.mp3"), 99, 200, 100, 200)
        segment = {"start": 100.2, "end": 100.8}
        self.assertFalse(main._segment_ist_im_hauptbereich(segment, erster))
        self.assertTrue(main._segment_ist_im_hauptbereich(segment, zweiter))

    def test_benachbarte_abschnitte_desselben_sprechers_werden_gebuendelt(self):
        bloecke = main._sprachbloecke_bilden(
            [
                {"start": 0.0, "end": 4.0, "speaker": "speaker_1", "text": "Guten Tag"},
                {"start": 4.5, "end": 8.0, "speaker": "speaker_1", "text": "سلام"},
                {"start": 8.2, "end": 10.0, "speaker": "speaker_2", "text": "Antwort"},
            ]
        )
        self.assertEqual(len(bloecke), 2)
        self.assertEqual(bloecke[0].fallback_text, "Guten Tag سلام")

    def test_lange_einzelrede_wird_in_sprachbloecke_geteilt(self):
        bloecke = main._sprachbloecke_bilden(
            [
                {
                    "start": 0.0,
                    "end": 200.0,
                    "speaker": "speaker_1",
                    "text": "eins zwei drei vier fünf sechs",
                }
            ]
        )
        self.assertEqual(len(bloecke), 3)
        self.assertTrue(
            all(
                block.ende - block.start <= main.SPRACHBLOCK_MAX_SEKUNDEN
                for block in bloecke
            )
        )
        self.assertEqual(
            " ".join(block.fallback_text for block in bloecke),
            "eins zwei drei vier fünf sechs",
        )

    def test_lange_rede_erhaelt_einen_zeitanker_pro_sekunde(self):
        bloecke = main._sprachbloecke_bilden(
            [
                {
                    "start": 1.0,
                    "end": 35.0,
                    "speaker": "speaker_1",
                    "text": "eins zwei drei vier fünf sechs sieben acht neun zehn",
                }
            ],
            stille_enden=[9.2, 17.8, 26.4],
        )
        anker = [anker for block in bloecke for anker in block.zeitanker]
        self.assertEqual(len(anker), 34)
        self.assertAlmostEqual(anker[0].ende, 2.0)
        self.assertTrue(
            all(
                eintrag.ende - eintrag.start <= main.ZEITANKER_MAX_SEKUNDEN
                for eintrag in anker
            )
        )

    def test_verfeinerter_text_wird_ohne_inhaltsverlust_zeitlich_verteilt(self):
        anker = tuple(
            main.Zeitanker(float(sekunde), float(sekunde + 1), "alt eins zwei")
            for sekunde in range(1, 35)
        )
        block = main.Sprachblock(
            1.0,
            35.0,
            "speaker_1",
            " ".join(eintrag.fallback_text for eintrag in anker),
            anker,
        )
        guter_text = (
            "Nein, das glaube ich nicht. چرا این را می‌گوید؟ "
            "Das wird er mir nicht sagen. او دقیقاً می‌داند."
        )
        segmente = main._text_auf_zeitanker_verteilen(block, guter_text, ["de", "fa"])

        self.assertLessEqual(len(segmente), 34)
        self.assertGreater(len(segmente), 1)
        self.assertEqual(
            " ".join(segment["text"] for segment in segmente), guter_text
        )
        self.assertEqual(segmente[0]["start"], 1.0)
        self.assertLessEqual(segmente[-1]["end"], 35.0)
        self.assertTrue(
            all(
                segment["end"] - segment["start"]
                <= main.ZEITANKER_MAX_SEKUNDEN
                for segment in segmente
            )
        )

    def test_formatierung_schreibt_genau_eine_zeile_pro_sekunde(self):
        text = main._transkript_formatieren(
            "mix.ogg",
            [
                {"start": 1.0, "end": 2.0, "speaker": "speaker_1", "text": "Hallo"},
                {"start": 2.0, "end": 3.0, "speaker": "speaker_1", "text": "سلام"},
            ],
            4.0,
        )
        zeitzeilen = [zeile for zeile in text.splitlines() if zeile.startswith("[")]
        self.assertEqual(
            zeitzeilen,
            [
                "[00:00:00] —",
                "[00:00:01] Sprecher 1: Hallo",
                "[00:00:02] Sprecher 1: سلام",
                "[00:00:03] —",
            ],
        )


class OpenAIParameterTests(unittest.TestCase):
    def test_diarisierung_sendet_keine_feste_sprache_und_nutzt_referenzen(self):
        antwort = SimpleNamespace(
            segments=[
                SimpleNamespace(start=0, end=3, speaker="speaker_1", text="Hallo")
            ],
            duration=3,
        )
        client = FakeClient(antwort)
        with tempfile.TemporaryDirectory() as temp_name:
            audio = Path(temp_name) / "audio.mp3"
            audio.write_bytes(b"audio")
            segmente, dauer = main._diarisiere_datei(
                client,
                audio,
                {"speaker_1": "data:audio/mpeg;base64,YQ=="},
            )

        parameter = client.audio.transcriptions.aufrufe[0]
        self.assertNotIn("language", parameter)
        self.assertEqual(parameter["model"], "gpt-4o-transcribe-diarize")
        self.assertEqual(parameter["known_speaker_names"], ["speaker_1"])
        self.assertEqual(dauer, 3)
        self.assertEqual(segmente[0]["text"], "Hallo")

    def test_sprachtranskription_sendet_deutsch_und_persisch(self):
        antwort = SimpleNamespace(
            text="Hallo سلام",
            languages=[SimpleNamespace(code="de"), SimpleNamespace(code="fa")],
            words=[
                SimpleNamespace(start=0.1, end=0.5, word="Hallo"),
                SimpleNamespace(start=0.6, end=1.0, word="سلام"),
            ],
        )
        client = FakeClient(antwort)
        with tempfile.TemporaryDirectory() as temp_name:
            audio = Path(temp_name) / "audio.mp3"
            audio.write_bytes(b"audio")
            text, sprachen, wortzeiten = main._sprachblock_transkribieren(client, audio)

        parameter = client.audio.transcriptions.aufrufe[0]
        self.assertEqual(parameter["model"], "gpt-transcribe")
        self.assertEqual(parameter["languages"], ["de", "fa"])
        self.assertEqual(parameter["response_format"], "verbose_json")
        self.assertEqual(parameter["timestamp_granularities"], ["word"])
        self.assertEqual(text, "Hallo سلام")
        self.assertEqual(sprachen, ["de", "fa"])
        self.assertEqual(wortzeiten[1]["word"], "سلام")

    def test_openai_wortzeiten_bestimmen_die_ausgabesekunde(self):
        anker = tuple(
            main.Zeitanker(float(sekunde), float(sekunde + 1), "fallback")
            for sekunde in range(10, 14)
        )
        block = main.Sprachblock(10.0, 14.0, "speaker_1", "fallback", anker)
        segmente = main._text_mit_wortzeiten_auf_sekunden_verteilen(
            block,
            "Hallo Welt سلام دوست",
            ["de", "fa"],
            [
                {"start": 0.1, "end": 0.4, "word": "Hallo"},
                {"start": 1.2, "end": 1.6, "word": "Welt"},
                {"start": 2.1, "end": 2.5, "word": "سلام"},
                {"start": 3.1, "end": 3.5, "word": "دوست"},
            ],
        )
        self.assertEqual([segment["start"] for segment in segmente], [10, 11, 12, 13])
        self.assertEqual(
            " ".join(segment["text"] for segment in segmente),
            "Hallo Welt سلام دوست",
        )

    def test_formatierung_bewahrt_persische_schrift(self):
        text = main._transkript_formatieren(
            "mix.mp3",
            [{"start": 0, "end": 2, "speaker": "speaker_1", "text": "سلام Welt"}],
            2,
        )
        self.assertIn("Sprecher 1: سلام Welt", text)
        self.assertIn("Sprachen: Deutsch und Persisch", text)


if __name__ == "__main__":
    unittest.main()
