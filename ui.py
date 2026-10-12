"""
AURA — Premium Tkinter Chat + Voice UI
• Connects to LiveKit room and auto-dispatches the Aura agent
• Text chat via input bar (Enter or Send)
• Voice via 🎙 mic toggle (Aura responds by voice through your speakers)
"""

import asyncio
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import scrolledtext
from datetime import datetime
import os

from dotenv import load_dotenv
from livekit import rtc
from livekit.api import (
    AccessToken, VideoGrants,
    LiveKitAPI, CreateAgentDispatchRequest,
)

load_dotenv(".env.local")

LIVEKIT_URL        = os.environ["LIVEKIT_URL"]
LIVEKIT_API_KEY    = os.environ["LIVEKIT_API_KEY"]
LIVEKIT_API_SECRET = os.environ["LIVEKIT_API_SECRET"]

ROOM_NAME            = "aura-room"
PARTICIPANT_IDENTITY = "user"
AGENT_NAME           = "my-agent"

# ── colours ─────────────────────────────────────────────────────────────────
BG       = "#0d0d12"
BG_PANEL = "#16161f"
BG_INPUT = "#1e1e2e"
BORDER   = "#252540"
PURPLE   = "#7c3aed"
PURPLE_D = "#5b21b6"
GREEN    = "#10b981"
RED      = "#ef4444"
LAVENDER = "#a78bfa"
TEAL     = "#2dd4bf"
MUTED    = "#6b7280"
WHITE    = "#f0eeff"

FONT  = "Helvetica Neue"
FONTS = "Helvetica"


def generate_token() -> str:
    return (
        AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity(PARTICIPANT_IDENTITY)
        .with_name("User")
        .with_grants(VideoGrants(room_join=True, room=ROOM_NAME))
        .to_jwt()
    )


# ═══════════════════════════════════════════════════════════════════════════
#  Backend
# ═══════════════════════════════════════════════════════════════════════════
class AuraBackend:
    def __init__(self, msg_q: queue.Queue, loop: asyncio.AbstractEventLoop):
        self.q         = msg_q
        self.loop      = loop
        self.room      = rtc.Room(loop=loop)
        self.platform  = None   # initialised inside async connect()
        self.mic_track = None
        self.audio_src = None
        self._mic_on   = False

    def push(self, sender: str, text: str):
        self.q.put((sender, text, datetime.now().strftime("%H:%M")))

    # ── text stream ─────────────────────────────────────────────────────────
    def _on_text_stream(self, reader: rtc.TextStreamReader, identity: str):
        asyncio.ensure_future(self._read_stream(reader, identity), loop=self.loop)

    async def _read_stream(self, reader: rtc.TextStreamReader, identity: str):
        text = await reader.read_all()
        if text.strip():
            label = "Aura" if identity != PARTICIPANT_IDENTITY else "You"
            self.push(label, text.strip())

    # ── connect + dispatch ───────────────────────────────────────────────────
    async def connect(self):
        try:
            token = generate_token()
            self.room.register_text_stream_handler("lk.transcription", self._on_text_stream)
            self.room.register_text_stream_handler("lk.chat",          self._on_text_stream)
            await self.room.connect(LIVEKIT_URL, token)
            self.push("System", "✓ Connected to room")

            # PlatformAudio MUST be created AFTER the event loop is running.
            # Keeping it alive routes incoming agent audio to your speakers.
            self.platform = rtc.PlatformAudio()

            # Auto-dispatch the agent so it joins the room
            await self._dispatch_agent()

        except Exception as exc:
            self.push("System", f"✗ Connection error: {exc}")

    async def _dispatch_agent(self):
        """Ask the LiveKit server to send the agent into our room."""
        try:
            async with LiveKitAPI(
                url=LIVEKIT_URL,
                api_key=LIVEKIT_API_KEY,
                api_secret=LIVEKIT_API_SECRET,
            ) as lk:
                await lk.agent_dispatch.create_dispatch(
                    CreateAgentDispatchRequest(
                        agent_name=AGENT_NAME,
                        room=ROOM_NAME,
                    )
                )
            self.push("System", "✓ Aura is joining…")
        except Exception as exc:
            self.push("System", f"Dispatch note: {exc}")

    # ── send text ────────────────────────────────────────────────────────────
    async def send_text(self, text: str):
        self.push("You", text)
        await self.room.local_participant.send_text(text, topic="lk.chat")

    # ── mic ─────────────────────────────────────────────────────────────────
    async def enable_mic(self):
        if self._mic_on or self.platform is None:
            return
        self.audio_src = self.platform.create_audio_source()
        self.mic_track = rtc.LocalAudioTrack.create_audio_track("mic", self.audio_src)
        await self.room.local_participant.publish_track(self.mic_track)
        self._mic_on = True
        self.push("System", "🎙 Microphone ON — speak now")

    async def disable_mic(self):
        if not self._mic_on:
            return
        if self.mic_track:
            self.mic_track.mute()
            await self.room.local_participant.unpublish_track(self.mic_track)
            self.mic_track = None
        if self.audio_src:
            self.audio_src.close()
            self.audio_src = None
        self._mic_on = False
        self.push("System", "🔇 Microphone OFF")

    async def toggle_mic(self) -> bool:
        if self._mic_on:
            await self.disable_mic()
        else:
            await self.enable_mic()
        return self._mic_on

    async def disconnect(self):
        await self.disable_mic()
        await self.room.disconnect()
        if self.platform:
            self.platform.close()
            self.platform = None


# ═══════════════════════════════════════════════════════════════════════════
#  Tkinter UI
# ═══════════════════════════════════════════════════════════════════════════
class AuraUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.q    = queue.Queue()

        # Create loop, set it as the current one, then start it in bg thread
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        self.backend = AuraBackend(self.q, self.loop)

        threading.Thread(target=self._run_loop, daemon=True).start()

        self._build_ui()
        self._poll_queue()

        asyncio.run_coroutine_threadsafe(self.backend.connect(), self.loop)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _poll_queue(self):
        while not self.q.empty():
            sender, text, ts = self.q.get_nowait()
            self._render(sender, text, ts)
        self.root.after(80, self._poll_queue)

    # ── build UI ─────────────────────────────────────────────────────────────
    def _build_ui(self):
        r = self.root
        r.title("Aura — AI Voice Assistant")
        r.configure(bg=BG)
        r.geometry("580x780")
        r.minsize(460, 560)

        # top bar
        top = tk.Frame(r, bg=BG_PANEL)
        top.pack(fill=tk.X)

        lf = tk.Frame(top, bg=BG_PANEL)
        lf.pack(side=tk.LEFT, padx=20, pady=16)
        tk.Label(lf, text="✦", font=(FONTS, 18), fg=PURPLE, bg=BG_PANEL).pack(side=tk.LEFT, padx=(0, 6))
        tk.Label(lf, text="AURA", font=(FONT, 20, "bold"), fg=WHITE, bg=BG_PANEL).pack(side=tk.LEFT)

        rf = tk.Frame(top, bg=BG_PANEL)
        rf.pack(side=tk.RIGHT, padx=20, pady=16)
        self.status_dot = tk.Label(rf, text="●", font=(FONTS, 11), fg="#374151", bg=BG_PANEL)
        self.status_dot.pack(side=tk.LEFT)
        self.status_lbl = tk.Label(rf, text="connecting…", font=(FONT, 11), fg=MUTED, bg=BG_PANEL)
        self.status_lbl.pack(side=tk.LEFT, padx=(4, 0))

        tk.Frame(r, bg=BORDER, height=1).pack(fill=tk.X)

        # sub-header hint
        tk.Label(r, text="Type or speak — Aura responds by voice & text",
                 font=(FONT, 11), fg=MUTED, bg=BG, pady=8).pack(fill=tk.X)
        tk.Frame(r, bg=BORDER, height=1).pack(fill=tk.X)

        # chat scroll area
        chat_fr = tk.Frame(r, bg=BG)
        chat_fr.pack(fill=tk.BOTH, expand=True)

        self.chat = scrolledtext.ScrolledText(
            chat_fr,
            bg=BG, fg=WHITE,
            font=(FONT, 14),
            relief=tk.FLAT,
            wrap=tk.WORD,
            padx=20, pady=16,
            state=tk.DISABLED,
            cursor="arrow",
            highlightthickness=0,
            borderwidth=0,
            selectbackground=PURPLE,
        )
        self.chat.pack(fill=tk.BOTH, expand=True)

        self.chat.tag_config("you_name",  foreground=LAVENDER, font=(FONT, 13, "bold"))
        self.chat.tag_config("aura_name", foreground=TEAL,     font=(FONT, 13, "bold"))
        self.chat.tag_config("ts",        foreground=MUTED,    font=(FONT, 10))
        self.chat.tag_config("you_body",  foreground=WHITE,    font=(FONT, 14))
        self.chat.tag_config("aura_body", foreground="#e2e8f0",font=(FONT, 14))
        self.chat.tag_config("system",    foreground=MUTED,    font=(FONT, 11, "italic"))

        # bottom input bar
        tk.Frame(r, bg=BORDER, height=1).pack(fill=tk.X)
        bot = tk.Frame(r, bg=BG_PANEL, pady=14)
        bot.pack(fill=tk.X)

        self.mic_btn = tk.Button(
            bot, text="🎙", font=(FONTS, 20),
            bg=GREEN, fg=WHITE, relief=tk.FLAT, bd=0,
            width=3, cursor="hand2", activebackground=GREEN,
            command=self._toggle_mic,
        )
        self.mic_btn.pack(side=tk.LEFT, padx=(16, 8))

        # entry with subtle border
        wrap = tk.Frame(bot, bg=BORDER, padx=1, pady=1)
        wrap.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        self.entry = tk.Entry(
            wrap, bg=BG_INPUT, fg=WHITE,
            insertbackground=WHITE,
            font=(FONT, 14),
            relief=tk.FLAT, bd=0, highlightthickness=0,
        )
        self.entry.pack(fill=tk.BOTH, ipady=11, padx=6)
        self.entry.bind("<Return>", lambda _: self._send())
        self.entry.focus_set()

        tk.Button(
            bot, text="Send ›", font=(FONT, 13, "bold"),
            bg=PURPLE, fg=WHITE, relief=tk.FLAT, bd=0,
            padx=20, pady=11, cursor="hand2", activebackground=PURPLE_D,
            command=self._send,
        ).pack(side=tk.RIGHT, padx=(8, 16))

        tk.Label(r, text="⏎ send   ·   🎙 mic toggle",
                 font=(FONTS, 9), fg=MUTED, bg=BG).pack(pady=(4, 10))

    # ── render ───────────────────────────────────────────────────────────────
    def _render(self, sender: str, text: str, ts: str):
        self.chat.config(state=tk.NORMAL)
        if sender == "System":
            self.chat.insert(tk.END, f"\n  {text}\n", "system")
            if "Connected" in text:
                self.status_dot.config(fg=GREEN)
                self.status_lbl.config(text="online")
            elif "error" in text.lower() or "✗" in text:
                self.status_dot.config(fg=RED)
                self.status_lbl.config(text="error")
        else:
            name_tag = "you_name" if sender == "You" else "aura_name"
            body_tag = "you_body" if sender == "You" else "aura_body"
            icon = "👤" if sender == "You" else "✦"
            self.chat.insert(tk.END, f"\n{icon} {sender}  ", name_tag)
            self.chat.insert(tk.END, f"{ts}\n", "ts")
            self.chat.insert(tk.END, f"   {text}\n", body_tag)
        self.chat.config(state=tk.DISABLED)
        self.chat.see(tk.END)

    # ── actions ──────────────────────────────────────────────────────────────
    def _send(self):
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, tk.END)
        asyncio.run_coroutine_threadsafe(self.backend.send_text(text), self.loop)

    def _toggle_mic(self):
        def _done(fut):
            try:
                on = fut.result()
                if on:
                    self.mic_btn.config(bg=RED, text="🔴", activebackground=RED)
                else:
                    self.mic_btn.config(bg=GREEN, text="🎙", activebackground=GREEN)
            except Exception:
                pass
        fut = asyncio.run_coroutine_threadsafe(self.backend.toggle_mic(), self.loop)
        fut.add_done_callback(_done)

    def _on_close(self):
        asyncio.run_coroutine_threadsafe(self.backend.disconnect(), self.loop)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.root.destroy()


# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    root = tk.Tk()
    AuraUI(root)
    root.mainloop()
