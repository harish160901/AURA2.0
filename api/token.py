#!/usr/bin/env python3
"""
Vercel Serverless Function: /api/token
Generates authenticated LiveKit tokens and dispatches the agent worker.
"""

import asyncio
import certifi
import json
import os
import ssl
import uuid
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

import aiohttp
from livekit.api import (
    AccessToken,
    CreateAgentDispatchRequest,
    LiveKitAPI,
    VideoGrants,
)

LIVEKIT_URL = os.environ.get("LIVEKIT_URL", "wss://aura-z0b0c205.livekit.cloud")
LIVEKIT_API_KEY = os.environ.get("LIVEKIT_API_KEY", "APIeooF3fVuy3kc")
LIVEKIT_API_SECRET = os.environ.get("LIVEKIT_API_SECRET", "gyAYTJCUqEVWrs9YOC0eew5ICHUeekDDf7FBebXHNfHc")
AGENT_NAME = "my-agent"


async def dispatch_agent(room_name: str):
    try:
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        connector = aiohttp.TCPConnector(ssl=ssl_ctx)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with LiveKitAPI(
                LIVEKIT_URL,
                LIVEKIT_API_KEY,
                LIVEKIT_API_SECRET,
                session=session,
            ) as lk:
                await lk.agent_dispatch.create_dispatch(
                    CreateAgentDispatchRequest(agent_name=AGENT_NAME, room=room_name)
                )
    except Exception as exc:
        print(f"[Vercel Token] Dispatch notice: {exc}")


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        identity = params.get("identity", ["user"])[0]

        room_name = f"aura-{uuid.uuid4().hex[:8]}"

        token = (
            AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
            .with_identity(identity)
            .with_name("User")
            .with_grants(
                VideoGrants(
                    room_join=True,
                    room=room_name,
                    can_publish=True,
                    can_subscribe=True,
                    can_publish_data=True,
                )
            )
            .to_jwt()
        )

        # Trigger agent dispatch in background
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(dispatch_agent(room_name))
            loop.close()
        except Exception:
            pass

        data = {
            "token": token,
            "url": LIVEKIT_URL,
            "room": room_name,
        }
        body = json.dumps(data).encode("utf-8")

        self.send_response(200)
        self.send_cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.end_headers()
        self.wfile.write(body)

    def send_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
