import atexit
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import tkinter as tk
import wave
from tkinter import messagebox, ttk


# =============================================================
# SOUND ENGINE
# Generates small WAV tones at start-up (no extra files or
# packages needed) and plays them with the system's audio tools.
# =============================================================

class SoundManager:
    # name -> list of (frequency in Hz, duration in ms). 0 Hz = silence.
    SOUNDS = {
        "click": [(880, 40)],
        "start": [(392, 90), (523, 90), (659, 90), (784, 200)],
        "message": [(440, 50), (554, 80)],
        "point": [(660, 70), (880, 70), (1175, 120)],
        "evidence": [(523, 80), (659, 80), (784, 80), (1047, 160)],
        "hint": [(988, 80), (1319, 180)],
        "wrong": [(220, 160), (165, 280)],
        "win": [(523, 110), (659, 110), (784, 110), (1047, 140),
                (784, 90), (1047, 380)],
        "lose": [(392, 190), (349, 190), (311, 190), (262, 450)],
        "thanks": [(784, 90), (988, 90), (1175, 240)],
        "tick": [(1300, 35)],
    }

    def __init__(self):
        self.enabled = True
        self.available = False
        self.files = {}
        self.cmd = None
        self.winsound = None
        self.tmpdir = None

        try:
            self._setup()
        except Exception:
            self.available = False

    def _setup(self):
        if sys.platform.startswith("win"):
            try:
                import winsound
                self.winsound = winsound
            except ImportError:
                return
        elif sys.platform == "darwin":
            exe = shutil.which("afplay")
            if exe:
                self.cmd = [exe]
        else:
            for exe, extra in (("paplay", []), ("aplay", ["-q"]), ("play", ["-q"])):
                found = shutil.which(exe)
                if found:
                    self.cmd = [found] + extra
                    break

        if self.winsound is None and self.cmd is None:
            return

        self.tmpdir = tempfile.mkdtemp(prefix="midnight_sounds_")
        atexit.register(shutil.rmtree, self.tmpdir, True)

        for name, notes in self.SOUNDS.items():
            path = os.path.join(self.tmpdir, name + ".wav")
            self._make_wav(path, notes)
            self.files[name] = path

        self.available = True

    @staticmethod
    def _make_wav(path, notes, volume=0.4, rate=22050):
        frames = bytearray()

        for freq, ms in notes:
            count = int(rate * ms / 1000)

            for i in range(count):
                if freq == 0:
                    value = 0.0
                else:
                    t = i / rate
                    attack = min(1.0, i / (rate * 0.005))
                    release = min(1.0, (count - i) / (rate * 0.02))
                    envelope = attack * release
                    value = (
                        math.sin(2 * math.pi * freq * t) * 0.8
                        + math.sin(2 * math.pi * freq * 2 * t) * 0.2
                    ) * envelope

                sample = int(max(-1.0, min(1.0, value * volume)) * 32767)
                frames += struct.pack("<h", sample)

        with wave.open(path, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            wav.writeframes(bytes(frames))

    def play(self, name):
        if not self.enabled or not self.available:
            return

        path = self.files.get(name)
        if not path:
            return

        try:
            if self.winsound is not None:
                self.winsound.PlaySound(
                    path,
                    self.winsound.SND_FILENAME | self.winsound.SND_ASYNC
                )
            elif self.cmd:
                subprocess.Popen(
                    self.cmd + [path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
        except Exception:
            pass


# =============================================================
# GAME
# =============================================================

class MurderMysteryGame:

    def __init__(self, root):
        self.root = root

        # ---------- Bright theme ----------
        self.bg = "#1b2250"
        self.dark = "#141a40"
        self.panel = "#27306b"
        self.panel2 = "#3a4590"
        self.border = "#4f5bb5"
        self.input_bg = "#161c47"
        self.note_bg = "#14532d"
        self.neutral = "#4a5399"
        self.neutral2 = "#2f3878"
        self.gold = "#ffd23f"
        self.red = "#e11d48"
        self.red2 = "#be123c"
        self.red_text = "#ff7b93"
        self.white = "#ffffff"
        self.gray = "#c7d0f5"
        self.muted = "#9aa6e8"
        self.green = "#4ade80"
        self.blue = "#2563eb"
        self.purple = "#7c3aed"
        self.orange = "#ffb703"

        self.root.title("The Midnight Mansion - Murder Mystery")
        self.root.configure(bg=self.bg)

        # Fullscreen
        self.root.attributes("-fullscreen", True)

        self.root.bind("<F11>", self.toggle_fullscreen)
        self.root.bind("<Escape>", self.exit_fullscreen)

        # Sounds
        self.sounds = SoundManager()
        self.sound_btn = None

        # Player information
        self.detective_name = ""
        self.username = ""
        self.difficulty = "Medium"

        # Game information
        self.score = 0
        self.lives = 3
        self.time_left = 300

        self.current_suspect = None
        self.visited_suspects = []
        self.collected_evidence = []
        self.used_hints = 0
        self.asked = set()      # (suspect, question index) already rewarded
        self.chat_logs = {}     # suspect -> list of (tag, text)

        self.game_started = False
        self.game_finished = False
        self.correct = False

        self.timer_job = None

        # Feedback
        self.feedback_submitted = False
        self.feedback_rating = 0
        self.feedback_category = ""
        self.final_score_label = None
        self.rank_label = None

        # Game data
        # "qa" = (question, answer, keywords used to understand typed questions)
        self.suspects = {
            "Victoria": {
                "role": "Mansion Owner",
                "color": "#c4b5fd",
                "description": "The wealthy owner of Midnight Mansion.",
                "qa": [
                    ("Where were you this evening?",
                     "I was in the dining room most of the evening.",
                     ["where", "kahan", "evening", "tonight", "raat", "location", "were you"]),
                    ("Did you hear anything around midnight?",
                     "I heard a loud noise around midnight.",
                     ["hear", "noise", "sound", "midnight", "suna", "awaz", "aawaz"]),
                    ("How was your relationship with the victim?",
                     "The victim and I had some disagreements.",
                     ["relationship", "relation", "victim", "argue", "argument", "fight",
                      "disagree", "enemy", "jhagra"]),
                    ("Do you know about the missing documents?",
                     "I don't know anything about the missing documents.",
                     ["document", "papers", "missing", "file"]),
                ],
                "secret": "Victoria had an argument with the victim earlier that evening."
            },

            "Marcus": {
                "role": "Business Partner",
                "color": "#7dd3fc",
                "description": "The victim's long-time business partner.",
                "qa": [
                    ("What were you doing tonight?",
                     "I was checking some business papers.",
                     ["doing", "busy", "papers", "work", "business", "tonight", "kya kar"]),
                    ("How were the victim's finances?",
                     "The victim had financial problems.",
                     ["financ", "money", "debt", "paisa", "paise", "loan", "bankrupt"]),
                    ("When did you leave the study?",
                     "I left the study before midnight.",
                     ["leave", "left", "study", "when", "time", "midnight", "kab"]),
                    ("Did you have a reason to hurt him?",
                     "I had no reason to hurt him.",
                     ["reason", "motive", "hurt", "why", "enemy"]),
                ],
                "secret": "Marcus was secretly hiding financial problems from the victim."
            },

            "Evelyn": {
                "role": "Family Member",
                "color": "#f9a8d4",
                "description": "A close family member of the victim.",
                "qa": [
                    ("Where were you during the incident?",
                     "I was upstairs.",
                     ["where", "kahan", "location", "upstairs", "were you"]),
                    ("Did you hear anything?",
                     "I heard footsteps near the study.",
                     ["hear", "footstep", "steps", "noise", "sound", "suna", "study"]),
                    ("What did you see?",
                     "Someone was carrying something strange.",
                     ["see", "saw", "carry", "carrying", "strange", "object", "dekha", "something"]),
                    ("Do you know who it was?",
                     "I don't know who it was.",
                     ["who", "know", "identify", "recognize", "kaun", "person"]),
                ],
                "secret": "Evelyn saw someone carrying a strange object near the study."
            },

            "Daniel": {
                "role": "Security Guard",
                "color": "#6ee7b7",
                "description": "The mansion's security guard.",
                "qa": [
                    ("What were you doing tonight?",
                     "I was monitoring the cameras.",
                     ["doing", "monitor", "watch", "duty", "where", "kahan", "were you"]),
                    ("Did the cameras show anything odd?",
                     "One camera stopped working.",
                     ["camera", "footage", "cctv", "stopped", "working", "odd"]),
                    ("Which camera was affected?",
                     "The study camera was disabled manually.",
                     ["study", "disable", "manual", "switch", "off", "which", "log", "turn"]),
                    ("Did you disable it?",
                     "I did not disable it.",
                     ["you", "tamper", "blame", "did you"]),
                ],
                "secret": "Daniel knows that the study camera was manually disabled."
            },

            "Oliver": {
                "role": "Family Friend",
                "color": "#fca5a5",
                "description": "A close family friend of the victim.",
                "qa": [
                    ("Where were you tonight?",
                     "I was outside for some fresh air.",
                     ["where", "kahan", "outside", "garden", "air", "tonight", "were you"]),
                    ("When did you come back inside?",
                     "I came back around midnight.",
                     ["return", "back", "came", "when", "midnight", "kab", "time"]),
                    ("Did you enter the study?",
                     "I didn't enter the study.",
                     ["study", "enter", "entered", "room", "went", "inside"]),
                    ("Do you know about the documents?",
                     "I know nothing about the documents.",
                     ["document", "papers", "file", "missing"]),
                ],
                "secret": "Oliver was connected to the victim's missing documents."
            }
        }

        # Ideas shown in "Ask Your Own Question" mode
        self.question_ideas = [
            "Where were you tonight?",
            "Did you hear anything strange?",
            "What do you know about the documents?",
            "Did you argue with the victim?",
            "Did you go into the study?",
            "What about the security cameras?",
            "Did you see anyone suspicious?",
        ]

        self.murderer = "Oliver"

        self.evidence = {
            "Broken Watch": {
                "description": "A broken watch was found near the victim.",
                "detail": "The watch stopped exactly at 11:47 PM.",
                "points": 15
            },

            "Wet Footprints": {
                "description": "Wet footprints were discovered near the study.",
                "detail": "The footprints lead from the garden directly to the study.",
                "points": 15
            },

            "Torn Document": {
                "description": "A torn business document was found under a table.",
                "detail": "It contains information about hidden financial problems.",
                "points": 15
            },

            "Silver Button": {
                "description": "A silver button was found near the study door.",
                "detail": "It appears to have been torn from someone's jacket.",
                "points": 20
            },

            "Security Log": {
                "description": "The mansion's security log was recovered.",
                "detail": "The study camera was manually disabled at 11:42 PM.",
                "points": 20
            },

            "Hidden Note": {
                "description": "A small hidden note was found inside a drawer.",
                "detail": "\"Meet me in the study before midnight.\"",
                "points": 20
            }
        }

        self.difficulty_settings = {
            "Easy": {"lives": 5, "time": 420},
            "Medium": {"lives": 3, "time": 300},
            "Hard": {"lives": 2, "time": 240}
        }

        self.show_login_page()

    # =========================================================
    # GENERAL FUNCTIONS
    # =========================================================

    def clear_screen(self):
        for widget in self.root.winfo_children():
            widget.destroy()

    def toggle_fullscreen(self, event=None):
        current = self.root.attributes("-fullscreen")
        self.root.attributes("-fullscreen", not current)

    def exit_fullscreen(self, event=None):
        self.root.attributes("-fullscreen", False)

    def cancel_timer(self):
        if self.timer_job is not None:
            try:
                self.root.after_cancel(self.timer_job)
            except Exception:
                pass

            self.timer_job = None

    @staticmethod
    def lighten(color, amount=0.18):
        color = color.lstrip("#")
        r = int(color[0:2], 16)
        g = int(color[2:4], 16)
        b = int(color[4:6], 16)

        r = int(r + (255 - r) * amount)
        g = int(g + (255 - g) * amount)
        b = int(b + (255 - b) * amount)

        return f"#{r:02x}{g:02x}{b:02x}"

    def create_button(
        self,
        parent,
        text,
        command,
        bg=None,
        fg=None,
        width=None,
        font=("Arial", 12, "bold"),
        pady=10,
        wraplength=0,
        sound="click"
    ):
        """All buttons share the same font/padding so they look uniform.
        Pass width=None and pack with fill='x' for full-width buttons."""
        if bg is None:
            bg = self.panel2

        if fg is None:
            fg = self.white

        def handler():
            if sound:
                self.sounds.play(sound)
            command()

        options = dict(
            text=text,
            command=handler,
            bg=bg,
            fg=fg,
            activebackground=self.gold,
            activeforeground="#000000",
            font=font,
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=pady,
            wraplength=wraplength,
            bd=0
        )

        if width is not None:
            options["width"] = width

        button = tk.Button(parent, **options)

        hover = self.lighten(bg)

        def on_enter(event):
            if str(button.cget("state")) == "normal":
                button.config(bg=hover)

        def on_leave(event):
            if str(button.cget("state")) == "normal":
                button.config(bg=bg)

        button.bind("<Enter>", on_enter)
        button.bind("<Leave>", on_leave)

        return button

    def sound_label(self):
        return "🔊 Sound: ON" if self.sounds.enabled else "🔇 Sound: OFF"

    def toggle_sound(self):
        self.sounds.enabled = not self.sounds.enabled

        if self.sound_btn is not None:
            try:
                self.sound_btn.config(text=self.sound_label())
            except tk.TclError:
                pass

        self.sounds.play("click")

    def reset_state(self):
        self.detective_name = ""
        self.username = ""
        self.difficulty = "Medium"

        self.score = 0
        self.lives = 3
        self.time_left = 300

        self.current_suspect = None
        self.visited_suspects = []
        self.collected_evidence = []
        self.used_hints = 0
        self.asked = set()
        self.chat_logs = {}

        self.game_started = False
        self.game_finished = False
        self.correct = False

        self.feedback_submitted = False
        self.feedback_rating = 0
        self.feedback_category = ""
        self.final_score_label = None
        self.rank_label = None

    # =========================================================
    # PAGE 1 - SIGN IN
    # =========================================================

    def show_login_page(self):
        self.cancel_timer()
        self.clear_screen()

        self.game_started = False
        self.game_finished = False

        main = tk.Frame(self.root, bg=self.bg)
        main.pack(fill="both", expand=True)

        # Sound toggle (top right)
        self.sound_btn = self.create_button(
            main,
            self.sound_label(),
            self.toggle_sound,
            bg=self.panel2,
            pady=6,
            sound=None
        )
        self.sound_btn.place(relx=1.0, x=-25, y=20, anchor="ne")

        tk.Label(
            main,
            text="🕵  THE MIDNIGHT MANSION",
            bg=self.bg,
            fg=self.gold,
            font=("Georgia", 38, "bold")
        ).pack(pady=(55, 5))

        tk.Label(
            main,
            text="A Murder Mystery Investigation",
            bg=self.bg,
            fg=self.gray,
            font=("Arial", 18, "italic")
        ).pack()

        card = tk.Frame(
            main,
            bg=self.panel,
            highlightbackground=self.gold,
            highlightthickness=2
        )
        card.pack(pady=30)

        inner = tk.Frame(card, bg=self.panel)
        inner.pack(padx=60, pady=30)

        tk.Label(
            inner,
            text="DETECTIVE SIGN IN",
            bg=self.panel,
            fg=self.white,
            font=("Arial", 20, "bold")
        ).pack(pady=(0, 25))

        tk.Label(
            inner,
            text="Detective Name",
            bg=self.panel,
            fg=self.gray,
            font=("Arial", 12, "bold")
        ).pack(anchor="w")

        self.name_entry = tk.Entry(
            inner,
            bg=self.input_bg,
            fg=self.white,
            insertbackground=self.gold,
            font=("Arial", 14),
            width=32,
            relief="flat"
        )
        self.name_entry.pack(fill="x", pady=(5, 18), ipady=8)

        tk.Label(
            inner,
            text="Username",
            bg=self.panel,
            fg=self.gray,
            font=("Arial", 12, "bold")
        ).pack(anchor="w")

        self.username_entry = tk.Entry(
            inner,
            bg=self.input_bg,
            fg=self.white,
            insertbackground=self.gold,
            font=("Arial", 14),
            width=32,
            relief="flat"
        )
        self.username_entry.pack(fill="x", pady=(5, 18), ipady=8)

        tk.Label(
            inner,
            text="Select Difficulty",
            bg=self.panel,
            fg=self.gray,
            font=("Arial", 12, "bold")
        ).pack(anchor="w")

        self.difficulty_var = tk.StringVar(value="Medium")

        ttk.Combobox(
            inner,
            textvariable=self.difficulty_var,
            values=["Easy", "Medium", "Hard"],
            state="readonly",
            font=("Arial", 12)
        ).pack(fill="x", pady=(5, 25), ipady=5)

        self.create_button(
            inner,
            "START INVESTIGATION",
            self.start_game,
            bg=self.red,
            sound=None
        ).pack(fill="x", pady=(0, 10))

        self.create_button(
            inner,
            "EXIT GAME",
            self.root.destroy,
            bg=self.neutral2
        ).pack(fill="x")

        self.name_entry.bind("<Return>", lambda e: self.username_entry.focus_set())
        self.username_entry.bind("<Return>", lambda e: self.start_game())
        self.name_entry.focus_set()

        tk.Label(
            main,
            text="F11 = Toggle Fullscreen     |     ESC = Exit Fullscreen",
            bg=self.bg,
            fg=self.muted,
            font=("Arial", 10)
        ).pack(side="bottom", pady=15)

    def start_game(self):
        name = self.name_entry.get().strip()
        username = self.username_entry.get().strip()
        difficulty = self.difficulty_var.get()

        if not name:
            self.sounds.play("wrong")
            messagebox.showwarning(
                "Missing Information",
                "Please enter your detective name."
            )
            return

        if not username:
            self.sounds.play("wrong")
            messagebox.showwarning(
                "Missing Information",
                "Please enter your username."
            )
            return

        self.reset_state()

        self.detective_name = name
        self.username = username
        self.difficulty = difficulty

        settings = self.difficulty_settings[difficulty]
        self.lives = settings["lives"]
        self.time_left = settings["time"]

        self.game_started = True

        self.sounds.play("start")

        self.show_case_file()
        self.start_timer()

    # =========================================================
    # TIMER
    # =========================================================

    def start_timer(self):
        self.cancel_timer()

        if self.game_started and not self.game_finished:
            self.update_timer()

    def update_timer(self):
        if not self.game_started or self.game_finished:
            return

        if self.time_left <= 0:
            self.time_left = 0
            self.finish_game(False)
            return

        self.update_header()

        # Warning ticks during the last 10 seconds
        if self.time_left <= 10:
            self.sounds.play("tick")

        self.time_left -= 1

        self.timer_job = self.root.after(1000, self.update_timer)

    def format_time(self):
        minutes = self.time_left // 60
        seconds = self.time_left % 60
        return f"{minutes:02d}:{seconds:02d}"

    # =========================================================
    # GAME PAGE LAYOUT (header + sidebar + content)
    # =========================================================

    def create_game_header(self, parent):
        header = tk.Frame(parent, bg=self.dark, height=75)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(
            header,
            text="🕵 THE MIDNIGHT MANSION",
            bg=self.dark,
            fg=self.gold,
            font=("Georgia", 20, "bold")
        ).pack(side="left", padx=25)

        self.sound_btn = self.create_button(
            header,
            self.sound_label(),
            self.toggle_sound,
            bg=self.panel2,
            pady=5,
            sound=None
        )
        self.sound_btn.pack(side="right", padx=(0, 25))

        self.header_info = tk.Label(
            header,
            text="",
            bg=self.dark,
            fg=self.white,
            font=("Arial", 12, "bold")
        )
        self.header_info.pack(side="right", padx=20)

        # Gold accent line under the header
        tk.Frame(parent, bg=self.gold, height=3).pack(fill="x")

    def update_header(self):
        if not hasattr(self, "header_info"):
            return

        try:
            self.header_info.config(
                text=(
                    f"Detective: {self.detective_name}   |   "
                    f"Score: {self.score}   |   "
                    f"Lives: {'♥ ' * self.lives}  |   "
                    f"Time: {self.format_time()}"
                )
            )
        except tk.TclError:
            pass

    def create_sidebar(self, parent):
        sidebar = tk.Frame(parent, bg=self.dark, width=270)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        tk.Label(
            sidebar,
            text="CASE MENU",
            bg=self.dark,
            fg=self.gold,
            font=("Arial", 15, "bold")
        ).pack(pady=(22, 12))

        # (text, command, background, text colour)
        menu_items = [
            ("📁  Case File", self.show_case_file, None, None),
            ("👥  Suspects", self.show_suspects, None, None),
            ("🔎  Evidence", self.show_evidence, None, None),
            ("📓  Notebook", self.show_notebook, None, None),
            ("💡  Hint", self.show_hint, self.orange, "#1b2250"),
            ("⭐  Submit Feedback", self.show_feedback_page, self.purple, None),
            ("⚖  Final Accusation", self.show_accusation, self.red, None),
        ]

        for text, command, color, text_color in menu_items:
            self.create_button(
                sidebar,
                text,
                command,
                bg=color,
                fg=text_color
            ).pack(fill="x", padx=18, pady=4)

        # Exit stays at the bottom (Logout is only on the final page)
        self.create_button(
            sidebar,
            "❌  Exit Game",
            self.root.destroy,
            bg=self.neutral2
        ).pack(side="bottom", fill="x", padx=18, pady=18)

    def setup_game_page(self, page_title):
        self.clear_screen()

        container = tk.Frame(self.root, bg=self.bg)
        container.pack(fill="both", expand=True)

        self.create_game_header(container)

        body = tk.Frame(container, bg=self.bg)
        body.pack(fill="both", expand=True)

        self.create_sidebar(body)

        content = tk.Frame(body, bg=self.bg)
        content.pack(side="left", fill="both", expand=True, padx=30, pady=20)

        tk.Label(
            content,
            text=page_title,
            bg=self.bg,
            fg=self.gold,
            font=("Georgia", 28, "bold")
        ).pack(anchor="w")

        self.update_header()

        return content

    # =========================================================
    # CASE FILE
    # =========================================================

    def show_case_file(self):
        content = self.setup_game_page("CASE FILE")

        self.create_button(
            content,
            "👥  Start Investigating Suspects",
            self.show_suspects,
            bg=self.red,
            width=32,
            pady=8
        ).pack(side="bottom", anchor="w", pady=(8, 0))

        settings = self.difficulty_settings[self.difficulty]

        intro = tk.Frame(
            content,
            bg=self.panel,
            highlightbackground=self.border,
            highlightthickness=1
        )
        intro.pack(fill="x", pady=(15, 10))

        tk.Label(
            intro,
            text="CASE #047 — THE MIDNIGHT MANSION MURDER",
            bg=self.panel,
            fg=self.white,
            font=("Arial", 19, "bold")
        ).pack(anchor="w", padx=25, pady=(20, 10))

        case_text = (
            "A mysterious murder has occurred inside Midnight Mansion.\n\n"
            "The victim was discovered inside the study shortly before midnight. "
            "Five people were inside or near the mansion at the time of the incident.\n\n"
            "Your mission is to investigate the suspects, collect evidence, "
            "discover contradictions, and identify the murderer.\n\n"
            f"Difficulty: {self.difficulty}     |     "
            f"Time Limit: {settings['time'] // 60} minutes     |     "
            f"Starting Lives: {settings['lives']}"
        )

        tk.Label(
            intro,
            text=case_text,
            bg=self.panel,
            fg=self.gray,
            font=("Arial", 13),
            justify="left",
            wraplength=900
        ).pack(anchor="w", padx=25, pady=(0, 22))

        obj = tk.Frame(content, bg=self.panel)
        obj.pack(fill="x", pady=10)

        tk.Label(
            obj,
            text="INVESTIGATION OBJECTIVES",
            bg=self.panel,
            fg=self.gold,
            font=("Arial", 16, "bold")
        ).pack(anchor="w", padx=20, pady=(15, 10))

        objectives = [
            "✓ Investigate all suspects (quick questions or your own typed questions)",
            "✓ Collect useful evidence",
            "✓ Read the notebook carefully",
            "✓ Use hints only when necessary",
            "✓ Make the final accusation before time runs out"
        ]

        for item in objectives:
            tk.Label(
                obj,
                text=item,
                bg=self.panel,
                fg=self.white,
                font=("Arial", 12),
                anchor="w"
            ).pack(anchor="w", padx=25, pady=3)

        tk.Frame(obj, bg=self.panel, height=12).pack()

    # =========================================================
    # SUSPECTS
    # =========================================================

    def show_suspects(self):
        content = self.setup_game_page("SUSPECT INVESTIGATION")

        tk.Label(
            content,
            text="Choose a suspect, then Interrogate them or Ask Your Own Question:",
            bg=self.bg,
            fg=self.gray,
            font=("Arial", 13)
        ).pack(anchor="w", pady=(12, 10))

        grid = tk.Frame(content, bg=self.bg)
        grid.pack(fill="both", expand=True)

        for col in range(3):
            grid.grid_columnconfigure(col, weight=1, uniform="suspect")
        for row in range(2):
            grid.grid_rowconfigure(row, weight=1, uniform="suspect_row")

        for index, (name, data) in enumerate(self.suspects.items()):

            card = tk.Frame(
                grid,
                bg=self.panel,
                highlightbackground=data["color"],
                highlightthickness=2
            )
            card.grid(
                row=index // 3,
                column=index % 3,
                padx=10,
                pady=10,
                sticky="nsew"
            )

            tk.Label(
                card,
                text=name,
                bg=self.panel,
                fg=data["color"],
                font=("Georgia", 20, "bold")
            ).pack(pady=(16, 4))

            tk.Label(
                card,
                text=data["role"],
                bg=self.panel,
                fg=self.white,
                font=("Arial", 12, "bold")
            ).pack()

            tk.Label(
                card,
                text=data["description"],
                bg=self.panel,
                fg=self.gray,
                font=("Arial", 10),
                wraplength=240,
                justify="center"
            ).pack(padx=15, pady=8)

            if name in self.visited_suspects:
                status, status_color = "✓ INVESTIGATED", self.green
            else:
                status, status_color = "NOT INVESTIGATED", self.orange

            tk.Label(
                card,
                text=status,
                bg=self.panel,
                fg=status_color,
                font=("Arial", 10, "bold")
            ).pack(pady=3)

            # Packed from the bottom: "Ask" first so it sits under "Interrogate"
            self.create_button(
                card,
                "✍  Ask Own Question",
                lambda n=name: self.interrogate(n, "custom"),
                bg=self.gold,
                fg="#000000",
                pady=8
            ).pack(side="bottom", fill="x", padx=20, pady=(4, 14))

            self.create_button(
                card,
                "🕵  Interrogate",
                lambda n=name: self.interrogate(n, "quick"),
                bg=data["color"],
                fg="#000000",
                pady=8
            ).pack(side="bottom", fill="x", padx=20, pady=(4, 0))

    # =========================================================
    # INTERROGATION
    # mode "quick"  = preset question buttons
    # mode "custom" = type your own questions (with ideas)
    # =========================================================

    def interrogate(self, name, mode="quick"):
        self.current_suspect = name

        if name not in self.visited_suspects:
            self.visited_suspects.append(name)
            self.score += 5

        data = self.suspects[name]

        if name not in self.chat_logs:
            self.chat_logs[name] = [
                ("system",
                 f"You are now interrogating {name} ({data['role']}). "
                 "Use the quick questions or type your own question below.")
            ]

        if mode == "custom":
            page_title = f"ASK YOUR OWN QUESTION — {name.upper()}"
        else:
            page_title = f"INTERROGATION — {name.upper()}"

        content = self.setup_game_page(page_title)

        # Suspect info bar
        top = tk.Frame(content, bg=self.panel)
        top.pack(fill="x", pady=(12, 10))

        tk.Label(
            top,
            text=name,
            bg=self.panel,
            fg=data["color"],
            font=("Georgia", 22, "bold")
        ).pack(side="left", padx=(25, 15), pady=14)

        tk.Label(
            top,
            text=f"{data['role']}  —  {data['description']}",
            bg=self.panel,
            fg=self.white,
            font=("Arial", 12)
        ).pack(side="left", pady=14)

        # Two columns: questions | conversation
        middle = tk.Frame(content, bg=self.bg)
        middle.pack(fill="both", expand=True)
        middle.grid_columnconfigure(0, weight=0, minsize=330)
        middle.grid_columnconfigure(1, weight=1)
        middle.grid_rowconfigure(0, weight=1)

        # ---- Left column. A scrollable inner panel keeps every question idea reachable.
        left = tk.Frame(middle, bg=self.bg)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 15))

        if mode == "custom":
            ideas_canvas = tk.Canvas(left, bg=self.bg, highlightthickness=0, bd=0)
            ideas_scrollbar = tk.Scrollbar(left, orient="vertical", command=ideas_canvas.yview)
            ideas_canvas.configure(yscrollcommand=ideas_scrollbar.set)
            ideas_scrollbar.pack(side="right", fill="y")
            ideas_canvas.pack(side="left", fill="both", expand=True)
            ideas_inner = tk.Frame(ideas_canvas, bg=self.bg)
            ideas_window = ideas_canvas.create_window((0, 0), window=ideas_inner, anchor="nw")

            def update_ideas_scrollregion(event=None):
                ideas_canvas.configure(scrollregion=ideas_canvas.bbox("all"))
                ideas_canvas.itemconfigure(ideas_window, width=ideas_canvas.winfo_width())

            ideas_inner.bind("<Configure>", update_ideas_scrollregion)
            ideas_canvas.bind("<Configure>", update_ideas_scrollregion)
            tk.Label(
                ideas_inner,
                text="Question Ideas",
                bg=self.bg,
                fg=self.gold,
                font=("Arial", 14, "bold")
            ).pack(anchor="w", pady=(0, 4))

            tk.Label(
                ideas_inner,
                text="Click an idea to fill the box, edit it if you like, then press Ask.",
                bg=self.bg,
                fg=self.gray,
                font=("Arial", 10),
                wraplength=300,
                justify="left"
            ).pack(anchor="w", pady=(0, 8))

            for idea in self.question_ideas:
                self.create_button(
                    ideas_inner,
                    idea,
                    lambda t=idea: self.fill_question(t),
                    wraplength=290,
                    pady=7
                ).pack(fill="x", pady=3)

            self.create_button(
                ideas_inner,
                "📋  Quick Questions",
                lambda: self.interrogate(name, "quick"),
                bg=self.neutral,
                pady=8
            ).pack(fill="x", pady=(12, 0))
        else:
            tk.Label(
                left,
                text="Quick Questions",
                bg=self.bg,
                fg=self.gold,
                font=("Arial", 14, "bold")
            ).pack(anchor="w", pady=(0, 8))

            for i, (question, answer, keywords) in enumerate(data["qa"]):
                self.create_button(
                    left,
                    question,
                    lambda idx=i: self.ask_preset(idx),
                    wraplength=290
                ).pack(fill="x", pady=5)

            self.create_button(
                left,
                "✍  Ask Your Own Question",
                lambda: self.interrogate(name, "custom"),
                bg=self.gold,
                fg="#000000"
            ).pack(fill="x", pady=(14, 0))

        # ---- Right: conversation + typing box
        right = tk.Frame(middle, bg=self.panel)
        right.grid(row=0, column=1, sticky="nsew")

        big = (mode == "custom")

        # Keep the typing field above the expanding conversation log so it cannot
        # disappear below the visible screen area.
        if big:
            tk.Label(
                right,
                text="TYPE YOUR OWN QUESTION",
                bg=self.panel,
                fg=self.gold,
                font=("Arial", 13, "bold")
            ).pack(anchor="w", padx=15, pady=(10, 3))

        entry_row = tk.Frame(right, bg=self.panel)
        entry_row.pack(fill="x", padx=15, pady=(5, 8))

        self.question_entry = tk.Entry(
            entry_row,
            bg=self.input_bg,
            fg=self.white,
            insertbackground=self.gold,
            font=("Arial", 15 if big else 13),
            relief="flat",
            highlightthickness=2 if big else 0,
            highlightbackground=self.gold,
            highlightcolor=self.gold
        )
        self.question_entry.pack(
            side="left",
            fill="x",
            expand=True,
            ipady=10 if big else 7
        )
        self.question_entry.bind("<Return>", lambda e: self.ask_custom())
        self.question_entry.focus_set()

        self.create_button(
            entry_row,
            "Ask ➤",
            self.ask_custom,
            bg=self.gold,
            fg="#000000",
            width=12,
            pady=10 if big else 8,
            sound="message"
        ).pack(side="left", padx=(10, 0))

        tk.Label(
            right,
            text="Conversation",
            bg=self.panel,
            fg=self.gold,
            font=("Arial", 14, "bold")
        ).pack(anchor="w", padx=15, pady=(2, 5))

        log_frame = tk.Frame(right, bg=self.panel)
        log_frame.pack(fill="both", expand=True, padx=15, pady=(0, 8))

        scrollbar = tk.Scrollbar(log_frame)
        scrollbar.pack(side="right", fill="y")

        self.chat_box = tk.Text(
            log_frame,
            bg=self.input_bg,
            fg=self.white,
            font=("Arial", 12),
            relief="flat",
            wrap="word",
            state="disabled",
            yscrollcommand=scrollbar.set,
            padx=10,
            pady=10
        )
        self.chat_box.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.chat_box.yview)

        self.chat_box.tag_configure("you", foreground=self.gold)
        self.chat_box.tag_configure("suspect", foreground=data["color"])
        self.chat_box.tag_configure("system", foreground=self.muted)
        self.chat_box.tag_configure("points", foreground=self.green)

        for tag, text in self.chat_logs[name]:
            self.write_chat(tag, text, save=False)

        # ---- Bottom: detective note + back button
        bottom = tk.Frame(content, bg=self.bg)
        bottom.pack(fill="x", pady=(10, 0))

        secret_frame = tk.Frame(bottom, bg=self.note_bg)
        secret_frame.pack(side="left", fill="x", expand=True, padx=(0, 15))

        tk.Label(
            secret_frame,
            text="🔐 Detective Note:",
            bg=self.note_bg,
            fg=self.green,
            font=("Arial", 12, "bold")
        ).pack(side="left", padx=(15, 8), pady=12)

        tk.Label(
            secret_frame,
            text=data["secret"],
            bg=self.note_bg,
            fg=self.white,
            font=("Arial", 11),
            wraplength=600,
            justify="left"
        ).pack(side="left", pady=12)

        self.create_button(
            bottom,
            "← Back to Suspects",
            self.show_suspects,
            bg=self.neutral,
            width=22
        ).pack(side="right")

    def fill_question(self, text):
        self.question_entry.delete(0, "end")
        self.question_entry.insert(0, text)
        self.question_entry.focus_set()
        self.question_entry.icursor("end")

    def write_chat(self, tag, text, save=True):
        self.chat_box.config(state="normal")
        self.chat_box.insert("end", text + "\n\n", tag)
        self.chat_box.config(state="disabled")
        self.chat_box.see("end")

        if save and self.current_suspect:
            self.chat_logs[self.current_suspect].append((tag, text))

    def give_answer(self, idx, question_text):
        """Show the question + answer, reward points once per question."""
        name = self.current_suspect
        answer = self.suspects[name]["qa"][idx][1]

        self.write_chat("you", f"You: {question_text}")
        self.write_chat("suspect", f"{name}: {answer}")

        if (name, idx) not in self.asked:
            self.asked.add((name, idx))
            self.score += 10
            self.write_chat("points", "+10 Investigation Points")
            self.update_header()
            self.sounds.play("point")
        else:
            self.sounds.play("message")

    def ask_preset(self, idx):
        question = self.suspects[self.current_suspect]["qa"][idx][0]
        self.give_answer(idx, question)

    def ask_custom(self):
        text = self.question_entry.get().strip()

        if not text:
            messagebox.showinfo("Type a Question", "Please type a question first.")
            self.question_entry.focus_set()
            return

        self.question_entry.delete(0, "end")
        name = self.current_suspect
        lowered = text.lower()
        # Normalize common Roman Urdu and natural-language variations so typed
        # questions can match the suspect's existing answers more reliably.
        normalized = lowered.replace("where's", "where is").replace("what's", "what is")
        normalized = normalized.replace("didn't", "did not").replace("wasn't", "was not")
        normalized = normalized.replace("weren't", "were not").replace("can't", "cannot")
        word_groups = [
            ("where", "location", "place", "kahan", "kidhar", "located", "stay", "staying"),
            ("hear", "heard", "sound", "noise", "awaz", "aawaz", "suna", "sunai"),
            ("see", "saw", "seen", "witness", "dekha", "notice", "noticed"),
            ("document", "documents", "paper", "papers", "file", "files", "kaghaz"),
            ("study", "office", "room", "kamra"),
            ("camera", "cctv", "footage", "recording", "security"),
            ("money", "finance", "financial", "debt", "loan", "paisa", "paise"),
            ("victim", "murdered", "murder", "kill", "killed", "death", "dead", "qatil"),
            ("argue", "argument", "fight", "disagreement", "jhagra", "larai"),
            ("return", "came back", "come back", "arrive", "returned", "wapas"),
            ("doing", "do", "busy", "work", "activity", "kya kar"),
            ("who", "person", "someone", "anyone", "kaun", "kisne"),
            ("enter", "entered", "went inside", "inside", "go into"),
            ("disable", "disabled", "switch off", "turned off", "turn off", "band"),
            ("reason", "motive", "why", "purpose", "wajah"),
        ]
        expanded = set()
        for group in word_groups:
            if any(term in normalized for term in group):
                expanded.update(group)

        best_idx = None
        best_score = 0
        qa_list = self.suspects[name]["qa"]
        for i, (question, answer, keywords) in enumerate(qa_list):
            terms = list(keywords) + question.lower().replace("?", "").split()
            score = sum(2 for term in terms if term and term in normalized)
            score += sum(2 for term in keywords if term in expanded)
            # Avoid matching short generic words such as "when" inside unrelated words.
            if score > best_score:
                best_score = score
                best_idx = i

        self.write_chat("you", f"You: {text}")
        self.sounds.play("message")

        if best_idx is not None and best_score >= 2:
            answer = qa_list[best_idx][1]
            self.write_chat("suspect", f"{name}: {answer}")
            if (name, best_idx) not in self.asked:
                self.asked.add((name, best_idx))
                self.score += 10
                self.write_chat("points", "+10 Investigation Points")
                self.update_header()
                self.sounds.play("point")
            return

        if any(word in normalized for word in
               ["kill", "murder", "guilty", "did it", "culprit", "killer", "qatil"]):
            reply = "I did not do this! You're looking at the wrong person."
        else:
            # Give a relevant in-game response instead of failing silently when
            # the wording is different from the preset question.
            reply = (
                "I can answer questions about my whereabouts, the victim, "
                "the study, the documents, or anything suspicious I noticed. "
                "Could you ask me about one of those?"
            )
        self.write_chat("suspect", f"{name}: {reply}")

    # =========================================================
    # EVIDENCE
    # =========================================================

    def show_evidence(self):
        content = self.setup_game_page("EVIDENCE ROOM")

        tk.Label(
            content,
            text="Collect evidence to strengthen your case.",
            bg=self.bg,
            fg=self.gray,
            font=("Arial", 13)
        ).pack(anchor="w", pady=(12, 10))

        # Back button first so it is always visible at the bottom
        self.create_button(
            content,
            "← Back to Case File",
            self.show_case_file,
            bg=self.neutral,
            width=22
        ).pack(side="bottom", anchor="w", pady=(10, 0))

        holder = tk.Frame(content, bg=self.bg)
        holder.pack(fill="both", expand=True)

        canvas = tk.Canvas(holder, bg=self.bg, highlightthickness=0)
        scrollbar = tk.Scrollbar(holder, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        frame = tk.Frame(canvas, bg=self.bg)
        window_id = canvas.create_window((0, 0), window=frame, anchor="nw")

        frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfig(window_id, width=e.width)
        )

        def on_wheel(event):
            if event.num == 4:
                canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                canvas.yview_scroll(1, "units")
            else:
                canvas.yview_scroll(int(-event.delta / 120), "units")

        def bind_wheel(event):
            canvas.bind_all("<MouseWheel>", on_wheel)
            canvas.bind_all("<Button-4>", on_wheel)
            canvas.bind_all("<Button-5>", on_wheel)

        def unbind_wheel(event):
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        canvas.bind("<Enter>", bind_wheel)
        canvas.bind("<Leave>", unbind_wheel)

        for name, data in self.evidence.items():

            collected = name in self.collected_evidence

            card = tk.Frame(
                frame,
                bg=self.panel,
                highlightbackground=self.gold if collected else self.border,
                highlightthickness=1
            )
            card.pack(fill="x", padx=(0, 10), pady=7)

            card.grid_columnconfigure(1, weight=1)

            tk.Label(
                card,
                text=("✓ " if collected else "🔎 ") + name,
                bg=self.panel,
                fg=self.green if collected else self.gold,
                font=("Arial", 15, "bold"),
                width=18,
                anchor="w"
            ).grid(row=0, column=0, padx=20, pady=15, sticky="w")

            tk.Label(
                card,
                text=data["description"],
                bg=self.panel,
                fg=self.white,
                font=("Arial", 11),
                anchor="w",
                justify="left",
                wraplength=450
            ).grid(row=0, column=1, padx=10, sticky="w")

            if collected:
                self.create_button(
                    card,
                    "Collected",
                    lambda d=data: self.show_evidence_detail(d),
                    bg="#15803d",
                    width=16
                ).grid(row=0, column=2, padx=15, pady=10)
            else:
                self.create_button(
                    card,
                    f"Collect +{data['points']}",
                    lambda n=name: self.collect_evidence(n),
                    bg=self.red,
                    width=16
                ).grid(row=0, column=2, padx=15, pady=10)

    def collect_evidence(self, name):
        if name in self.collected_evidence:
            return

        self.collected_evidence.append(name)

        points = self.evidence[name]["points"]
        self.score += points

        self.sounds.play("evidence")

        messagebox.showinfo(
            "Evidence Collected",
            f"{name} added to your evidence file.\n\n"
            f"+{points} points"
        )

        self.show_evidence()

    def show_evidence_detail(self, data):
        messagebox.showinfo(
            "Evidence Detail",
            f"{data['description']}\n\n"
            f"Detail:\n{data['detail']}\n\n"
            f"Evidence Value: +{data['points']} points"
        )

    # =========================================================
    # NOTEBOOK
    # =========================================================

    def show_notebook(self):
        content = self.setup_game_page("DETECTIVE NOTEBOOK")

        self.create_button(
            content,
            "← Back to Case File",
            self.show_case_file,
            bg=self.neutral,
            width=22
        ).pack(side="bottom", anchor="w", pady=(10, 0))

        notebook = tk.Frame(
            content,
            bg=self.panel,
            highlightbackground=self.gold,
            highlightthickness=2
        )
        notebook.pack(fill="both", expand=True, pady=(15, 0))

        tk.Label(
            notebook,
            text="CASE NOTES",
            bg=self.panel,
            fg=self.gold,
            font=("Georgia", 20, "bold")
        ).pack(anchor="w", padx=25, pady=(15, 10))

        text = tk.Text(
            notebook,
            bg=self.input_bg,
            fg=self.white,
            insertbackground=self.white,
            font=("Consolas", 12),
            relief="flat",
            wrap="word",
            padx=10,
            pady=10
        )
        text.pack(fill="both", expand=True, padx=25, pady=(0, 25))

        text.insert("1.0", "=== MIDNIGHT MANSION CASE NOTES ===\n\n")

        text.insert(
            "end",
            f"Detective: {self.detective_name}\n"
            f"Username: {self.username}\n"
            f"Difficulty: {self.difficulty}\n\n"
        )

        text.insert(
            "end",
            f"Score: {self.score}\n"
            f"Lives Remaining: {self.lives}\n"
            f"Suspects Investigated: {len(self.visited_suspects)}/5\n"
            f"Evidence Collected: {len(self.collected_evidence)}/6\n\n"
        )

        text.insert("end", "=== SUSPECTS INVESTIGATED ===\n")

        for suspect in self.visited_suspects:
            text.insert("end", f"• {suspect}: {self.suspects[suspect]['role']}\n")

        text.insert("end", "\n=== EVIDENCE COLLECTED ===\n")

        for evidence in self.collected_evidence:
            text.insert("end", f"• {evidence}\n")

        text.config(state="disabled")

    # =========================================================
    # HINT
    # =========================================================

    def show_hint(self):
        if self.used_hints >= 3:
            messagebox.showinfo(
                "No More Hints",
                "You have already used all 3 available hints."
            )
            return

        self.used_hints += 1
        self.score -= 5

        hints = [
            "Look closely at the security camera evidence.",
            "Pay attention to the missing documents.",
            "The person connected to the documents may know more than they admit."
        ]

        hint = hints[self.used_hints - 1]

        self.sounds.play("hint")

        messagebox.showinfo(
            f"Hint #{self.used_hints}",
            f"💡 {hint}\n\n-5 points"
        )

        self.show_case_file()

    # =========================================================
    # FEEDBACK PAGE (available from the side menu during the game)
    # =========================================================

    def show_feedback_page(self):
        content = self.setup_game_page("SUBMIT FEEDBACK")

        # These only exist on the final report page
        self.final_score_label = None
        self.rank_label = None

        panel = tk.Frame(
            content,
            bg=self.panel,
            highlightbackground=self.gold,
            highlightthickness=2
        )
        panel.pack(fill="both", expand=True, pady=(15, 0), padx=40)

        self.build_feedback_form(panel)

    # =========================================================
    # FINAL ACCUSATION
    # =========================================================

    def show_accusation(self):
        content = self.setup_game_page("FINAL ACCUSATION")

        # Reserve the bottom row for navigation so the button stays on-screen.
        self.create_button(
            content,
            "← Back to Case File",
            self.show_case_file,
            bg=self.neutral,
            width=22,
            pady=8
        ).pack(side="bottom", anchor="w", pady=(8, 0))

        tk.Label(
            content,
            text="⚖ Who is the murderer?",
            bg=self.bg,
            fg=self.white,
            font=("Georgia", 24, "bold")
        ).pack(anchor="w", pady=(20, 10))

        tk.Label(
            content,
            text=(
                "You have reviewed the evidence and interrogated the suspects.\n"
                "Choose carefully. A wrong accusation will cost you a life."
            ),
            bg=self.bg,
            fg=self.gray,
            font=("Arial", 13),
            justify="left"
        ).pack(anchor="w", pady=(0, 25))

        row = tk.Frame(content, bg=self.bg)
        row.pack(fill="x", pady=10)

        for col, name in enumerate(self.suspects):
            row.grid_columnconfigure(col, weight=1, uniform="accuse")

            self.create_button(
                row,
                name,
                lambda n=name: self.make_accusation(n),
                bg=self.suspects[name]["color"],
                fg="#000000",
                pady=14
            ).grid(row=0, column=col, padx=8, sticky="ew")

    def make_accusation(self, name):

        if name == self.murderer:
            self.score += 100
            self.finish_game(True)

        else:
            self.score -= 30
            self.lives -= 1

            self.sounds.play("wrong")

            messagebox.showerror(
                "Wrong Accusation",
                f"{name} is NOT the murderer!\n\n"
                "-30 points\n"
                "1 life lost.\n\n"
                f"Lives remaining: {self.lives}"
            )

            if self.lives <= 0:
                self.finish_game(False)
            else:
                self.show_accusation()

    # =========================================================
    # PAGE 3 - FINAL REPORT + FEEDBACK + LOGOUT
    # =========================================================

    def finish_game(self, correct):
        self.cancel_timer()

        self.correct = correct
        self.game_finished = True

        self.sounds.play("win" if correct else "lose")

        self.show_final_page()

    def show_final_page(self):
        self.cancel_timer()
        self.clear_screen()

        main = tk.Frame(self.root, bg=self.bg)
        main.pack(fill="both", expand=True)

        # Bottom navigation first so it never gets cut off
        nav = tk.Frame(main, bg=self.bg)
        nav.pack(side="bottom", fill="x", padx=15, pady=10)

        nav_buttons = [
            ("← Back to Investigation", self.back_to_investigation, self.neutral),
            ("🔄  Play Again", self.play_again, self.blue),
            ("🚪  Logout", self.logout, self.red2),
            ("❌  Exit Game", self.root.destroy, self.neutral2),
        ]

        for col, (text, command, color) in enumerate(nav_buttons):
            nav.grid_columnconfigure(col, uniform="nav")
            self.create_button(
                nav,
                text,
                command,
                bg=color,
                width=18,
                pady=8
            ).grid(row=0, column=col, padx=5, sticky="ew")

        tk.Label(
            main,
            text="CASE CLOSED",
            bg=self.bg,
            fg=self.gold,
            font=("Georgia", 32, "bold")
        ).pack(pady=(25, 0))

        if self.correct:
            result_text = "✓ CASE SOLVED"
            result_color = self.green
            result_message = (
                "Excellent work, Detective!\n"
                "You identified the murderer correctly."
            )
        else:
            result_text = "✗ CASE UNSOLVED"
            result_color = self.red_text
            result_message = (
                "The investigation has ended.\n"
                "The murderer was not successfully identified."
            )

        tk.Label(
            main,
            text=result_text,
            bg=self.bg,
            fg=result_color,
            font=("Arial", 22, "bold")
        ).pack()

        tk.Label(
            main,
            text=result_message,
            bg=self.bg,
            fg=self.gray,
            font=("Arial", 12),
            justify="center"
        ).pack(pady=5)

        body = tk.Frame(main, bg=self.bg)
        body.pack(fill="both", expand=True, padx=35, pady=4)
        body.grid_columnconfigure(0, weight=1, uniform="final")
        body.grid_columnconfigure(1, weight=1, uniform="final")
        body.grid_rowconfigure(0, weight=1)

        # ---------- Left: report
        report = tk.Frame(
            body,
            bg=self.panel,
            highlightbackground=self.gold,
            highlightthickness=2
        )
        report.grid(row=0, column=0, sticky="nsew", padx=12)

        tk.Label(
            report,
            text="INVESTIGATION REPORT",
            bg=self.panel,
            fg=self.gold,
            font=("Georgia", 18, "bold")
        ).pack(pady=(8, 5))

        report_data = [
            ("Detective", self.detective_name),
            ("Username", self.username),
            ("Difficulty", self.difficulty),
            ("Final Score", str(self.score)),
            ("Suspects Investigated", f"{len(self.visited_suspects)}/5"),
            ("Evidence Collected", f"{len(self.collected_evidence)}/6"),
            ("Lives Remaining", str(self.lives)),
            ("Hints Used", str(self.used_hints))
        ]

        for label, value in report_data:
            row = tk.Frame(report, bg=self.panel)
            row.pack(fill="x", padx=30, pady=6)

            tk.Label(
                row,
                text=label,
                bg=self.panel,
                fg=self.gray,
                font=("Arial", 12, "bold"),
                width=22,
                anchor="w"
            ).pack(side="left")

            value_label = tk.Label(
                row,
                text=value,
                bg=self.panel,
                fg=self.white,
                font=("Arial", 12),
                anchor="w"
            )
            value_label.pack(side="left")

            if label == "Final Score":
                self.final_score_label = value_label

        tk.Label(
            report,
            text="DETECTIVE RANK",
            bg=self.panel,
            fg=self.gold,
            font=("Arial", 13, "bold")
        ).pack(pady=(20, 5))

        self.rank_label = tk.Label(
            report,
            text=self.get_rank(),
            bg=self.panel,
            fg=self.green if self.correct else self.orange,
            font=("Georgia", 22, "bold")
        )
        self.rank_label.pack(pady=(0, 15))

        # ---------- Right: feedback
        feedback = tk.Frame(
            body,
            bg=self.panel,
            highlightbackground=self.gold,
            highlightthickness=2
        )
        feedback.grid(row=0, column=1, sticky="nsew", padx=12)

        self.build_feedback_form(feedback)

    # =========================================================
    # FEEDBACK FORM (shared by the side-menu page and final page)
    # =========================================================

    def build_feedback_form(self, feedback):

        tk.Label(
            feedback,
            text="DETECTIVE FEEDBACK",
            bg=self.panel,
            fg=self.gold,
            font=("Georgia", 19, "bold")
        ).pack(pady=(7, 2))

        tk.Label(
            feedback,
            text="How was your investigation experience?",
            bg=self.panel,
            fg=self.gray,
            font=("Arial", 11)
        ).pack(pady=(0, 3))

        tk.Label(
            feedback,
            text="Rate the Game",
            bg=self.panel,
            fg=self.white,
            font=("Arial", 12, "bold")
        ).pack(pady=(3, 1))

        self.rating_var = tk.IntVar(value=self.feedback_rating)

        rating_frame = tk.Frame(feedback, bg=self.panel)
        rating_frame.pack(pady=1)

        for i in range(1, 6):
            tk.Radiobutton(
                rating_frame,
                text=f"{i} ★",
                variable=self.rating_var,
                value=i,
                bg=self.panel,
                fg=self.gold,
                selectcolor=self.panel2,
                activebackground=self.panel,
                activeforeground=self.gold,
                font=("Arial", 11, "bold"),
                cursor="hand2"
            ).pack(side="left", padx=6)

        tk.Label(
            feedback,
            text="Feedback Category",
            bg=self.panel,
            fg=self.white,
            font=("Arial", 12, "bold")
        ).pack(pady=(4, 2))

        self.category_var = tk.StringVar(
            value=self.feedback_category or "Gameplay"
        )

        ttk.Combobox(
            feedback,
            textvariable=self.category_var,
            values=[
                "Gameplay",
                "Story",
                "GUI / Design",
                "Difficulty",
                "Features",
                "Overall Experience"
            ],
            state="readonly",
            font=("Arial", 11)
        ).pack(fill="x", padx=25, ipady=1)

        tk.Label(
            feedback,
            text="Your Feedback",
            bg=self.panel,
            fg=self.white,
            font=("Arial", 12, "bold")
        ).pack(pady=(4, 2))

        self.feedback_text = tk.Text(
            feedback,
            bg=self.input_bg,
            fg=self.white,
            insertbackground=self.gold,
            height=3,
            font=("Arial", 11),
            relief="flat",
            wrap="word",
            padx=6,
            pady=4
        )
        self.feedback_text.pack(padx=25, fill="x", expand=False)

        self.feedback_status = tk.Label(
            feedback,
            text="",
            bg=self.panel,
            fg=self.green,
            font=("Arial", 9, "bold")
        )
        self.feedback_status.pack(pady=1)

        # Big submit button
        self.submit_button = self.create_button(
            feedback,
            "⭐  SUBMIT FEEDBACK",
            self.submit_feedback,
            bg=self.gold,
            fg="#000000",
            font=("Arial", 12, "bold"),
            pady=6,
            sound=None
        )
        self.submit_button.pack(fill="x", padx=25, pady=(3, 7))

        if self.feedback_submitted:
            self.feedback_status.config(
                text="✓ Feedback already submitted. Thank you!"
            )
            self.feedback_text.config(state="disabled")
            self.submit_button.config(
                state="disabled",
                bg="#6b7280",
                cursor="arrow"
            )

    # =========================================================
    # FEEDBACK
    # =========================================================

    def submit_feedback(self):

        if self.feedback_submitted:
            messagebox.showinfo(
                "Already Submitted",
                "Your feedback has already been submitted."
            )
            return

        rating = self.rating_var.get()
        category = self.category_var.get()
        comment = self.feedback_text.get("1.0", "end").strip()

        if rating == 0:
            self.sounds.play("wrong")
            messagebox.showwarning(
                "Rating Required",
                "Please select a rating from 1 to 5 stars."
            )
            return

        if not comment:
            self.sounds.play("wrong")
            messagebox.showwarning(
                "Feedback Required",
                "Please write some feedback before submitting."
            )
            return

        self.feedback_submitted = True
        self.feedback_rating = rating
        self.feedback_category = category

        bonus = rating * 5
        self.score += bonus

        self.sounds.play("thanks")

        self.feedback_status.config(
            text=f"✓ Feedback submitted successfully! +{bonus} bonus points"
        )

        self.feedback_text.config(state="disabled")
        self.submit_button.config(state="disabled", bg="#6b7280", cursor="arrow")

        # Refresh score / rank where they are visible
        try:
            if self.final_score_label is not None:
                self.final_score_label.config(text=str(self.score))
            if self.rank_label is not None:
                self.rank_label.config(text=self.get_rank())
        except tk.TclError:
            pass

        self.update_header()

        messagebox.showinfo(
            "Feedback Submitted",
            f"Thank you for your feedback!\n\n"
            f"Rating: {rating}/5\n"
            f"Category: {category}\n"
            f"Bonus: +{bonus} points"
        )

    # =========================================================
    # NAVIGATION FROM FINAL PAGE
    # =========================================================

    def back_to_investigation(self):
        self.show_case_file()

    def logout(self):
        """Logout (final page only) - goes straight back to the sign in page."""
        self.cancel_timer()
        self.reset_state()
        self.show_login_page()

    def play_again(self):
        answer = messagebox.askyesno(
            "Play Again",
            "Start a completely new investigation?"
        )

        if not answer:
            return

        self.cancel_timer()
        self.reset_state()
        self.show_login_page()

    # =========================================================
    # RANK
    # =========================================================

    def get_rank(self):

        if self.score >= 300:
            return "MASTER DETECTIVE"
        elif self.score >= 220:
            return "ELITE DETECTIVE"
        elif self.score >= 150:
            return "SENIOR DETECTIVE"
        elif self.score >= 80:
            return "DETECTIVE"
        else:
            return "ROOKIE DETECTIVE"


# =============================================================
# RUN GAME
# =============================================================

if __name__ == "__main__":

    root = tk.Tk()

    app = MurderMysteryGame(root)

    root.mainloop()
