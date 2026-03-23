import os
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import yt_dlp
from collections import deque
import asyncio
from ffmpeg_setup import ensure_ffmpeg

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Set dynamically on startup by ensure_ffmpeg()
FFMPEG_PATH = None
SONG_QUEUES = {}



async def search_ytdlp_async(query, ydl_opts):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: _extract(query, ydl_opts))

def _extract(query, ydl_opts):
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(query, download=False)

import threading
import os
from http.server import HTTPServer, BaseHTTPRequestHandler

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, format, *args):
        pass

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    print(f"[health] Listening on port {port}")
    server.serve_forever()

threading.Thread(target=run_health_server, daemon=True).start()

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    global FFMPEG_PATH
    FFMPEG_PATH = await ensure_ffmpeg()
    
    # Syncing logic...
    await bot.tree.sync() # Recommendation: Sync globally for simplicity unless testing
    print("BOT IS RUNNING")


@bot.tree.command(name="play", description="Play a song or add it to the queue.")
@app_commands.describe(song_query="Search query")
async def play(interaction: discord.Interaction, song_query: str):
    await interaction.response.defer()

    if interaction.user.voice is None:
        await interaction.followup.send("You must be in a voice channel.")
        return

    voice_channel = interaction.user.voice.channel
    voice_client = interaction.guild.voice_client

    if voice_client is None:
        voice_client = await voice_channel.connect()
    elif voice_channel != voice_client.channel:
        await voice_client.move_to(voice_channel)

    ydl_options = {
        "format": "bestaudio/best",
        "noplaylist": True,
        "quiet": True,
        "http_chunk_size": 10485760,
        "buffer_size": "16K",
    }

    query = "ytsearch1: " + song_query
    try:
        results = await search_ytdlp_async(query, ydl_options)
    except Exception as e:
        await interaction.followup.send(f"Search failed: {e}")
        return

    tracks = results.get("entries", [])
    if not tracks:
        await interaction.followup.send("No results found.")
        return

    first_track = tracks[0]
    audio_url = first_track["url"]
    title = first_track.get("title", "Untitled")

    guild_id = str(interaction.guild_id)
    if SONG_QUEUES.get(guild_id) is None:
        SONG_QUEUES[guild_id] = deque()

    SONG_QUEUES[guild_id].append((audio_url, title))

    if voice_client.is_playing() or voice_client.is_paused():
        await interaction.followup.send(f"Added to queue: **{title}**")
    else:
        await interaction.followup.send(f"Now playing: **{title}**")
        await play_next_song(voice_client, guild_id, interaction.channel)


async def play_next_song(voice_client, guild_id, channel):
    if not SONG_QUEUES.get(guild_id):
        await voice_client.disconnect()
        SONG_QUEUES[guild_id] = deque()
        return

    audio_url, title = SONG_QUEUES[guild_id].popleft()

    ffmpeg_options = {
        "before_options": (
            "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 "
            "-probesize 10M -analyzeduration 10M"
        ),
        "options": (
            "-vn -b:a 192k -ar 48000 -ac 2 "
            "-af \"loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000\""
        ),
    }

    try:
        raw_source = discord.FFmpegPCMAudio(
            audio_url,
            **ffmpeg_options,
            executable=FFMPEG_PATH
        )
        source = discord.PCMVolumeTransformer(raw_source, volume=0.5)
    except Exception as e:
        print(f"[ERROR] Failed to create audio source for '{title}': {e}")
        await channel.send(f"Could not load audio for **{title}**: {e}")
        await play_next_song(voice_client, guild_id, channel)
        return

    def after_play(error):
        if error:
            print(f"[ERROR] Playback error for '{title}': {error}")
        asyncio.run_coroutine_threadsafe(
            play_next_song(voice_client, guild_id, channel), bot.loop
        )

    voice_client.play(source, after=after_play)
    asyncio.create_task(channel.send(f"Now playing: **{title}**"))


@bot.tree.command(name="skip", description="Skip the current song.")
async def skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and (vc.is_playing() or vc.is_paused()):
        vc.stop()
        await interaction.response.send_message("Skipped.")
    else:
        await interaction.response.send_message("Nothing to skip.")


@bot.tree.command(name="pause", description="Pause the current song.")
async def pause(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc is None:
        return await interaction.response.send_message("Not in a voice channel.")
    if not vc.is_playing():
        return await interaction.response.send_message("Nothing is playing.")
    vc.pause()
    await interaction.response.send_message("Paused.")


@bot.tree.command(name="resume", description="Resume the paused song.")
async def resume(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc is None:
        return await interaction.response.send_message("Not in a voice channel.")
    if not vc.is_paused():
        return await interaction.response.send_message("Not paused.")
    vc.resume()
    await interaction.response.send_message("Resumed.")


@bot.tree.command(name="stop", description="Stop playback and clear the queue.")
async def stop(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if not vc or not vc.is_connected():
        return await interaction.response.send_message("Not connected to any voice channel.")

    guild_id_str = str(interaction.guild_id)
    if guild_id_str in SONG_QUEUES:
        SONG_QUEUES[guild_id_str].clear()

    if vc.is_playing() or vc.is_paused():
        vc.stop()

    await vc.disconnect()
    await interaction.response.send_message("Stopped and disconnected.")

import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

bot.run(TOKEN)