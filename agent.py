#!/usr/bin/env python3
"""
AURA 2.0 Intelligent Multimodal Agent
======================================
LiveKit Multimodal Voice & Vision Agent powered by Google Gemini Realtime Live API.
Features:
  - Ultra-fast real-time bi-directional voice conversation.
  - Computer vision via user camera video sampling.
  - Deep macOS system control:
      * Open/close apps (Safari, Maps, Finder, Notes, Terminal, WhatsApp, etc.)
      * Open/list folders (Desktop, Documents, Downloads, Home, etc.)
      * Volume adjustment & battery status check.
  - Reliable text chat input & speech broadcasting back to the HUD.
"""

import asyncio
import certifi
import json
import os
import subprocess
from pathlib import Path

# Fix SSL certificate verification for macOS Python virtual environments
os.environ["SSL_CERT_FILE"] = certifi.where()

from dotenv import load_dotenv
from google.genai import types
from livekit import agents, rtc
from livekit.agents import Agent, AgentSession, WorkerOptions, llm
from livekit.agents.voice.agent_session import VoiceActivityVideoSampler
from livekit.agents.voice.room_io import RoomOptions
from livekit.plugins.google.realtime import RealtimeModel

BASE_DIR = Path(__file__).parent.resolve()
load_dotenv(BASE_DIR / ".env.local")

HOME = Path.home()

DIR_MAP = {
    "desktop": HOME / "Desktop",
    "documents": HOME / "Documents",
    "downloads": HOME / "Downloads",
    "pictures": HOME / "Pictures",
    "music": HOME / "Music",
    "movies": HOME / "Movies",
    "home": HOME,
    "applications": Path("/Applications"),
    "aura": BASE_DIR,
}

APP_MAP = {
    "safari": "Safari",
    "maps": "Maps",
    "map": "Maps",
    "apple maps": "Maps",
    "finder": "Finder",
    "files": "Finder",
    "whatsapp": "WhatsApp",
    "zoom": "zoom.us",
    "keynote": "Keynote",
    "word": "Microsoft Word",
    "excel": "Microsoft Excel",
    "powerpoint": "Microsoft PowerPoint",
    "onenote": "Microsoft OneNote",
    "teams": "Microsoft Teams",
    "onedrive": "OneDrive",
    "notes": "Notes",
    "note": "Notes",
    "calendar": "Calendar",
    "calculator": "Calculator",
    "terminal": "Terminal",
    "settings": "System Settings",
    "system settings": "System Settings",
    "system preferences": "System Preferences",
    "mail": "Mail",
    "messages": "Messages",
    "facetime": "FaceTime",
    "photos": "Photos",
    "music": "Music",
    "chrome": "Google Chrome",
    "google chrome": "Google Chrome",
    "brave": "Brave Browser",
    "vscode": "Visual Studio Code",
    "code": "Visual Studio Code",
    "textedit": "TextEdit",
    "preview": "Preview",
    "activity monitor": "Activity Monitor",
    "reminders": "Reminders",
}

SYSTEM_INSTRUCTIONS = (
    "Your name is Aura 2.0. You are an ultra-fast, intelligent, multimodal voice and vision assistant with direct control over the user's macOS computer. "
    "When the user enables their camera, you can see what is in front of the camera and describe or answer questions about it. "
    "You have tools to open and close any Mac application (like Safari, Maps, Finder, Notes, Terminal, WhatsApp, etc.), "
    "open or list any folder (Desktop, Documents, Downloads, Home, etc.), adjust system volume, and check battery. "
    "Whenever the user asks you to open or close an application, open a folder, list files, or check system settings, "
    "you MUST invoke the appropriate tool immediately and give a brief, natural confirmation of 3 to 6 words. "
    "Answer all general questions accurately, articulately, and directly with ultra-low latency. "
    "Never use markdown formatting, asterisks, emojis, or bullet points in spoken text."
)


class Assistant(Agent):
    def __init__(self, room: rtc.Room | None = None) -> None:
        super().__init__(instructions=SYSTEM_INSTRUCTIONS)
        self.room = room

    async def _publish_action(self, action: str, status: str, text: str, target: str = "") -> None:
        """Broadcast instant tool execution telemetry to the room for 0ms UI feedback."""
        try:
            if self.room and self.room.local_participant:
                payload = json.dumps({
                    "type": "action",
                    "action": action,
                    "status": status,
                    "target": target,
                    "text": text,
                })
                await self.room.local_participant.publish_data(
                    payload.encode("utf-8"),
                    topic="lk.chat",
                    reliable=True,
                )
        except Exception as e:
            print(f"[Assistant Action Error] {e}")

    @llm.function_tool
    async def open_application(self, app_name: str) -> str:
        """Open any application on macOS such as Maps, Safari, Finder, Notes, Terminal, WhatsApp, Calculator, Chrome, etc."""
        cleaned = app_name.strip().lower()
        target = APP_MAP.get(cleaned, app_name.strip())
        await self._publish_action("open_app", "starting", f"⚡ Opening {target}...", target=target)
        try:
            subprocess.Popen(["open", "-a", target])
            await self._publish_action("open_app", "completed", f"✓ Opened {target}", target=target)
            return f"Opened {target} successfully."
        except Exception as e:
            await self._publish_action("open_app", "error", f"✗ Error opening {target}: {e}", target=target)
            return f"Error opening {app_name}: {e}"

    @llm.function_tool
    async def close_application(self, app_name: str) -> str:
        """Close or quit any running application on macOS like Maps, Safari, Notes, etc."""
        cleaned = app_name.strip().lower()
        target = APP_MAP.get(cleaned, app_name.strip())
        await self._publish_action("close_app", "starting", f"⚡ Closing {target}...", target=target)
        try:
            script = f'tell application "{target}" to quit'
            subprocess.Popen(["osascript", "-e", script])
            await self._publish_action("close_app", "completed", f"✓ Closed {target}", target=target)
            return f"Closed {target} successfully."
        except Exception as e:
            await self._publish_action("close_app", "error", f"✗ Error closing {target}: {e}", target=target)
            return f"Error closing {app_name}: {e}"

    @llm.function_tool
    async def open_folder(self, folder_name: str) -> str:
        """Open any folder on macOS in Finder (e.g. Desktop, Documents, Downloads, Home, Pictures, Music, Applications)."""
        cleaned = folder_name.strip().lower()
        path = DIR_MAP.get(cleaned)
        if not path:
            p = Path(folder_name.strip())
            if p.is_dir():
                path = p
            else:
                hp = HOME / folder_name.strip()
                if hp.is_dir():
                    path = hp
                else:
                    path = DIR_MAP["desktop"]
        folder_display = path.name or str(path)
        await self._publish_action("open_folder", "starting", f"⚡ Opening folder {folder_display}...", target=folder_display)
        try:
            subprocess.Popen(["open", str(path)])
            await self._publish_action("open_folder", "completed", f"✓ Opened folder {folder_display}", target=folder_display)
            return f"Opened folder {folder_display} successfully."
        except Exception as e:
            await self._publish_action("open_folder", "error", f"✗ Error opening folder: {e}", target=folder_display)
            return f"Error opening folder {folder_name}: {e}"

    @llm.function_tool
    async def list_folder_contents(self, folder_name: str) -> str:
        """List files and subfolders inside a specific folder on macOS."""
        cleaned = folder_name.strip().lower()
        path = DIR_MAP.get(cleaned)
        if not path:
            p = Path(folder_name.strip())
            if p.is_dir():
                path = p
            else:
                path = HOME / folder_name.strip()
        folder_display = path.name or str(path)
        await self._publish_action("list_folder", "starting", f"⚡ Listing {folder_display}...", target=folder_display)
        try:
            if not path or not path.exists():
                await self._publish_action("list_folder", "error", f"✗ Folder {folder_name} not found")
                return f"Folder {folder_name} does not exist"
            items = [p.name for p in sorted(path.iterdir()) if not p.name.startswith(".")]
            top_items = items[:12]
            summary = ", ".join(top_items)
            msg = f"✓ Found {len(items)} items: {summary}"
            await self._publish_action("list_folder", "completed", msg, target=folder_display)
            return f"Folder contains {len(items)} items: {summary}"
        except Exception as e:
            await self._publish_action("list_folder", "error", f"✗ Error listing folder: {e}")
            return f"Error listing {folder_name}: {e}"

    @llm.function_tool
    async def set_mac_volume(self, volume_percent: int) -> str:
        """Set the macOS master system audio volume from 0 to 100 percent."""
        vol = max(0, min(100, int(volume_percent)))
        await self._publish_action("set_volume", "starting", f"⚡ Setting volume to {vol}%...", target=str(vol))
        try:
            subprocess.Popen(["osascript", "-e", f"set volume output volume {vol}"])
            await self._publish_action("set_volume", "completed", f"✓ Volume set to {vol}%", target=str(vol))
            return f"Volume set to {vol}%."
        except Exception as e:
            await self._publish_action("set_volume", "error", f"✗ Error setting volume: {e}")
            return f"Error setting volume: {e}"

    @llm.function_tool
    async def get_mac_battery(self) -> str:
        """Get the current macOS battery percentage and charging status."""
        await self._publish_action("get_battery", "starting", "⚡ Reading battery status...")
        try:
            res = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=1)
            raw = res.stdout.strip()
            await self._publish_action("get_battery", "completed", f"✓ Battery: {raw}")
            return raw
        except Exception as e:
            await self._publish_action("get_battery", "error", f"✗ Error reading battery: {e}")
            return f"Error reading battery: {e}"


async def my_agent(ctx: agents.JobContext):
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("[Agent Error] GEMINI_API_KEY is not set in environment or .env.local!")

    model = RealtimeModel(
        instructions=SYSTEM_INSTRUCTIONS,
        voice="Puck",
        api_key=api_key,
        temperature=0.2,
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                silence_duration_ms=250,  # Ultra-fast 250ms VAD for instant reaction turnaround
                prefix_padding_ms=15,
            )
        ),
    )

    session = AgentSession(
        llm=model,
        aec_warmup_duration=0.0,
        video_sampler=VoiceActivityVideoSampler(speaking_fps=1.0, silent_fps=0.3),
    )

    assistant = Assistant(room=ctx.room)
    await session.start(
        room=ctx.room,
        agent=assistant,
        room_options=RoomOptions(close_on_disconnect=False, text_output=True),
    )

    # Listen for fast text messages submitted from the UI
    @ctx.room.on("data_received")
    def on_data_received(dp: rtc.DataPacket):
        try:
            if dp.participant and dp.participant.identity != "user":
                return
            text = dp.data.decode("utf-8").strip()
            if text:
                print(f"[Agent] Fast text input: {text}")
                session.generate_reply(user_input=text)
        except Exception as e:
            print(f"[Agent] Error processing data packet: {e}")

    # 1. Real-time User Speech Transcription Captioning
    @session.on("user_input_transcribed")
    def on_user_input_transcribed(ev):
        try:
            transcript = (getattr(ev, "transcript", "") or "").strip()
            if transcript:
                is_final = getattr(ev, "is_final", False)
                async def _publish_user():
                    try:
                        if ctx.room and ctx.room.local_participant:
                            payload = json.dumps({
                                "type": "caption",
                                "role": "user",
                                "text": transcript,
                                "is_final": is_final,
                            })
                            await ctx.room.local_participant.publish_data(
                                payload.encode("utf-8"),
                                topic="lk.chat",
                                reliable=True,
                            )
                    except Exception:
                        pass
                asyncio.create_task(_publish_user())
        except Exception as e:
            print(f"[Agent] Error in user_input_transcribed: {e}")

    # 2. Real-time Assistant Speech Caption Streaming (as soon as words are generated)
    @session.on("speech_created")
    def on_speech_created(ev):
        try:
            handle = getattr(ev, "speech_handle", None)
            if handle:
                def on_item(item):
                    if getattr(item, "role", None) == "assistant":
                        text = (getattr(item, "text_content", "") or getattr(item, "raw_text_content", "") or "").strip()
                        if text:
                            async def _publish_speech():
                                try:
                                    if ctx.room and ctx.room.local_participant:
                                        payload = json.dumps({
                                            "type": "caption",
                                            "role": "assistant",
                                            "text": text,
                                            "is_final": False,
                                        })
                                        await ctx.room.local_participant.publish_data(
                                            payload.encode("utf-8"),
                                            topic="lk.chat",
                                            reliable=True,
                                        )
                                except Exception:
                                    pass
                            asyncio.create_task(_publish_speech())
                handle._add_item_added_callback(on_item)
        except Exception as e:
            print(f"[Agent] Error in speech_created: {e}")

    # 3. Final Conversation Turn Broadcast
    @session.on("conversation_item_added")
    def on_conversation_item_added(ev):
        try:
            item = getattr(ev, "item", None)
            if item and getattr(item, "role", None) == "assistant":
                text = (getattr(item, "text_content", "") or getattr(item, "raw_text_content", "") or "").strip()
                if text:
                    print(f"[Agent Spoken Complete] {text}")
                    async def _publish_final():
                        try:
                            if ctx.room and ctx.room.local_participant:
                                payload = json.dumps({
                                    "type": "caption",
                                    "role": "assistant",
                                    "text": text,
                                    "is_final": True,
                                })
                                await ctx.room.local_participant.publish_data(
                                    payload.encode("utf-8"),
                                    topic="lk.chat",
                                    reliable=True,
                                )
                        except Exception:
                            pass
                    asyncio.create_task(_publish_final())
        except Exception as e:
            print(f"[Agent] Error in conversation item: {e}")

    # Initial spoken introduction
    session.generate_reply(
        instructions="Greet the user as Aura 2.0 in one quick sentence. Tell them you are ready for voice, vision, and system tasks."
    )


if __name__ == "__main__":
    agents.cli.run_app(
        WorkerOptions(
            entrypoint_fnc=my_agent,
            agent_name="my-agent",
            num_idle_processes=6,  # More warm workers = faster join latency
        )
    )