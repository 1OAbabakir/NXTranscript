from PIL import Image, ImageTk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import filedialog, messagebox
import threading
from pathlib import Path
from datetime import datetime
from main import transkribiere_audio


class TranskriptionsGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Transkript")
        self.api_key = ""
        self.log_eintraege = []
        self.output_fenster = None
        self.output_text = None
        self.current_theme = "flatly"
        self.style = ttk.Style(self.current_theme)
        
        
        self.taskbar = ttk.Frame(root, padding=(10, 5), bootstyle="secondary")
        self.taskbar.pack(side="top", fill="x")

        # App-Name oder Icon links
        self.title_label = ttk.Label(
            self.taskbar, text="📝", font=("Segoe UI", 13, "bold")
        )
        self.title_label.pack(side="left")

        # Dark/Light-Mode-Button RECHTS in die Taskbar!
        self.mode_button = ttk.Button(
            self.taskbar, text="🌙 Dunkelmodus", command=self.toggle_theme, bootstyle="dark-link"
        )
        self.mode_button.pack(side="right")

        self.options_button = ttk.Button(
            self.taskbar,
            text="⚙ Optionen",
            command=self.optionen_oeffnen,
            bootstyle="secondary-link",
        )
        self.options_button.pack(side="right", padx=(0, 8))

        self.output_button = ttk.Button(
            self.taskbar,
            text="📋 Output",
            command=self.output_oeffnen,
            bootstyle="secondary-link",
        )
        self.output_button.pack(side="right", padx=(0, 8))

        try:
            logo_pfad = Path(__file__).resolve().with_name("transkript-logo.png")
            bild = Image.open(logo_pfad)
            bild = bild.resize((240, 240))
            self.logo = ImageTk.PhotoImage(bild)
            self.logo_label = ttk.Label(root, image=self.logo)
            self.logo_label.pack(pady=(5, 0))
        except FileNotFoundError:
            print("⚠️ transkript-logo.png nicht gefunden – Logo wird übersprungen.")


        self.frame = ttk.Frame(root, padding=20)
        self.frame.pack()

        self.dateipfad = ttk.StringVar()
        self.entry = ttk.Entry(
            self.frame,
            textvariable=self.dateipfad,
            width=80,
        )
        self.entry.grid(row=0, column=0, columnspan=3, padx=5, pady=(0, 10), sticky="we")

        self.select_button = ttk.Button(self.frame, text="🎵 Datei auswählen", command=self.datei_auswaehlen, bootstyle="info")
        self.select_button.grid(row=1, column=1, padx=10)

        self.start_button = ttk.Button(self.frame, text="📝 Transkribieren", command=self.transkribieren, bootstyle="success")
        self.start_button.grid(row=1, column=0, pady=10)

        self.save_button = ttk.Button(self.frame, text="💾 Speichern", command=self.speichern, bootstyle="secondary")
        self.save_button.grid(row=1, column=2, pady=10)

        self.text_output = ttk.Text(root, height=20, width=80, font=("Segoe UI", 10))
        self.text_output.pack(padx=20, pady=10)

        self.progress = ttk.Progressbar(root, mode='indeterminate', length=300, bootstyle="info")
        self.progress.pack(pady=(0, 10))
        self.progress.stop()

        self.status_text = ttk.StringVar(value="Bereit")
        self.status_label = ttk.Label(
            root,
            textvariable=self.status_text,
            anchor="center",
            bootstyle="secondary",
        )
        self.status_label.pack(pady=(0, 10))

        self.transkript_text = ""
        
        self.footer = ttk.Label(
            root,
            text="von omed",
            font=("Segoe UI", 9, "italic"),
            anchor="center"
        )
        self.footer.pack(side="bottom", pady=(0, 8))
        self.log("Anwendung gestartet")

    def log(self, nachricht):
        zeit = datetime.now().strftime("%H:%M:%S")
        eintrag = f"[{zeit}] {nachricht}"
        self.log_eintraege.append(eintrag)

        try:
            if self.output_text and self.output_text.winfo_exists():
                self.output_text.config(state="normal")
                self.output_text.insert("end", eintrag + "\n")
                self.output_text.see("end")
                self.output_text.config(state="disabled")
        except Exception:
            self.output_text = None

    def output_oeffnen(self):
        if self.output_fenster and self.output_fenster.winfo_exists():
            self.output_fenster.deiconify()
            self.output_fenster.lift()
            self.output_fenster.focus_force()
            return

        fenster = ttk.Toplevel(self.root)
        fenster.title("Output")
        fenster.geometry("760x360")
        fenster.minsize(520, 240)
        fenster.transient(self.root)
        self.output_fenster = fenster

        inhalt = ttk.Frame(fenster, padding=12)
        inhalt.pack(fill="both", expand=True)

        ausgabe_frame = ttk.Frame(inhalt)
        ausgabe_frame.pack(fill="both", expand=True)

        scrollbar = ttk.Scrollbar(ausgabe_frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")

        self.output_text = ttk.Text(
            ausgabe_frame,
            wrap="word",
            font=("Consolas", 10),
            yscrollcommand=scrollbar.set,
        )
        self.output_text.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.output_text.yview)
        self.output_text.insert("end", "\n".join(self.log_eintraege) + "\n")
        self.output_text.config(state="disabled")

        buttons = ttk.Frame(inhalt)
        buttons.pack(fill="x", pady=(10, 0))

        def kopieren():
            self.root.clipboard_clear()
            self.root.clipboard_append("\n".join(self.log_eintraege))

        def leeren():
            self.log_eintraege.clear()
            self.output_text.config(state="normal")
            self.output_text.delete("1.0", "end")
            self.output_text.config(state="disabled")

        ttk.Button(buttons, text="Kopieren", command=kopieren).pack(side="left")
        ttk.Button(buttons, text="Leeren", command=leeren).pack(side="left", padx=8)
        ttk.Button(
            buttons,
            text="Schließen",
            command=lambda: beim_schliessen(),
        ).pack(side="right")

        def beim_schliessen():
            self.output_text = None
            self.output_fenster = None
            fenster.destroy()

        fenster.protocol("WM_DELETE_WINDOW", beim_schliessen)


    def datei_auswaehlen(self):
        pfad = filedialog.askopenfilename(
            parent=self.root,
            title="Wähle eine Audiodatei aus",
            filetypes=[
                (
                    "Alle unterstützten Audiodateien",
                    ("*.mp3", "*.wav", "*.m4a", "*.ogg", "*.flac"),
                ),
                ("MP3-Dateien", "*.mp3"),
                ("Wave-Dateien", "*.wav"),
                ("M4A-Dateien", "*.m4a"),
                ("Ogg-Dateien", "*.ogg"),
                ("FLAC-Dateien", "*.flac"),
                ("Alle Dateien", "*.*"),
            ],
        )
        if pfad:
            self.dateipfad.set(str(Path(pfad)))
            self.log(f"Datei ausgewählt: {pfad}")

    def transkribieren(self):
        pfad = self.dateipfad.get().strip()
        if not pfad:
            messagebox.showwarning("Fehler", "Bitte zuerst eine Datei auswählen.")
            return

        if not Path(pfad).is_file():
            messagebox.showerror(
                "Datei nicht gefunden",
                "Die ausgewählte Datei existiert nicht mehr. Bitte wähle sie erneut aus.",
            )
            return

        if not self.api_key:
            messagebox.showinfo(
                "OpenAI API-Key fehlt",
                "Bitte hinterlege deinen API-Key unter Optionen.",
            )
            if not self.optionen_oeffnen():
                return

        self.progress.start()
        self.status_text.set("Sprecher und Zeitstempel werden erkannt …")
        self.log(f"Transkription mit Sprechererkennung gestartet: {Path(pfad).name}")
        self.start_button.config(state="disabled")

        thread = threading.Thread(
            target=self.transkription_im_hintergrund,
            args=(pfad, self.api_key),
            daemon=True,
        )
        thread.start()

    def transkription_im_hintergrund(self, pfad, api_key):
        try:
            def fortschritt(meldung):
                self.root.after(
                    0,
                    lambda text=meldung: self.status_aktualisieren(text),
                )

            text = transkribiere_audio(pfad, api_key, fortschritt)
            self.transkript_text = text

            self.root.after(0, lambda: self.text_output.delete("1.0", "end"))
            self.root.after(0, lambda: self.text_output.insert("end", text))
            self.root.after(0, lambda: self.status_text.set("Transkription abgeschlossen"))
            self.root.after(0, lambda: self.log("Transkription erfolgreich abgeschlossen"))
            self.root.after(0, lambda: messagebox.showinfo("Fertig", "Transkription abgeschlossen."))
        except Exception as e:
            fehlermeldung = str(e)
            self.root.after(0, lambda: self.status_text.set("Transkription fehlgeschlagen"))
            self.root.after(
                0,
                lambda meldung=fehlermeldung: self.log(f"FEHLER: {meldung}"),
            )
            self.root.after(
                0,
                lambda meldung=fehlermeldung: messagebox.showerror(
                    "Transkription fehlgeschlagen",
                    meldung,
                ),
            )
        finally:
            self.root.after(0, self.progress.stop)
            self.root.after(0, lambda: self.start_button.config(state="normal"))

    def status_aktualisieren(self, meldung):
        self.status_text.set(meldung)
        self.log(meldung)

    def optionen_oeffnen(self):
        fenster = ttk.Toplevel(self.root)
        fenster.title("Optionen")
        fenster.resizable(False, False)
        fenster.transient(self.root)

        inhalt = ttk.Frame(fenster, padding=20)
        inhalt.pack(fill="both", expand=True)

        ttk.Label(
            inhalt,
            text="OpenAI API-Key",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            inhalt,
            text="Der Key bleibt nur bis zum Schließen der App im Speicher.",
        ).pack(anchor="w", pady=(2, 10))

        key_var = ttk.StringVar(value=self.api_key)
        key_entry = ttk.Entry(inhalt, textvariable=key_var, show="*", width=52)
        key_entry.pack(fill="x")

        anzeigen_var = ttk.BooleanVar(value=False)

        def sichtbarkeit_wechseln():
            key_entry.config(show="" if anzeigen_var.get() else "*")

        ttk.Checkbutton(
            inhalt,
            text="API-Key anzeigen",
            variable=anzeigen_var,
            command=sichtbarkeit_wechseln,
            bootstyle="round-toggle",
        ).pack(anchor="w", pady=(10, 16))

        buttons = ttk.Frame(inhalt)
        buttons.pack(fill="x")

        def speichern():
            api_key = key_var.get().strip()
            if not api_key:
                messagebox.showwarning(
                    "API-Key fehlt",
                    "Bitte gib einen gültigen OpenAI API-Key ein.",
                    parent=fenster,
                )
                return
            self.api_key = api_key
            self.log("API-Key für diese Sitzung übernommen")
            fenster.destroy()

        ttk.Button(
            buttons,
            text="Abbrechen",
            command=fenster.destroy,
            bootstyle="secondary",
        ).pack(side="right")
        ttk.Button(
            buttons,
            text="Speichern",
            command=speichern,
            bootstyle="success",
        ).pack(side="right", padx=(0, 8))

        fenster.protocol("WM_DELETE_WINDOW", fenster.destroy)
        fenster.grab_set()
        key_entry.focus_set()
        self.root.wait_window(fenster)
        return bool(self.api_key)

    def speichern(self):
        if not self.transkript_text:
            messagebox.showwarning("Kein Inhalt", "Bitte zuerst transkribieren.")
            return
        pfad = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Textdateien", "*.txt")],
            title="Speichern unter"
        )
        if pfad:
            with open(pfad, "w", encoding="utf-8") as f:
                f.write(self.transkript_text)
            messagebox.showinfo("Gespeichert", f"Gespeichert unter:\n{pfad}")

    def toggle_theme(self):
        if self.current_theme == "flatly":
            # Wechsel zu dunklem Theme
            self.current_theme = "superhero"
            self.style.theme_use("superhero")
            self.mode_button.config(text="☀️ Hellmodus", bootstyle="light-link")
        else:
            # Wechsel zu hellem Theme
            self.current_theme = "flatly"
            self.style.theme_use("flatly")
            self.mode_button.config(text="🌙 Dunkelmodus", bootstyle="dark-link")



if __name__ == "__main__":
    root = ttk.Window(themename="flatly")
    app = TranskriptionsGUI(root)
    root.mainloop()
