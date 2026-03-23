import os
import stat
import shutil
import zipfile
import asyncio
import platform
import aiohttp

IS_WINDOWS = platform.system() == "Windows"

# Download destinations
FFMPEG_DIR_WIN   = os.path.join(os.path.dirname(__file__), "ffmpeg_auto", "windows")
FFMPEG_DIR_LINUX = os.path.join(os.path.dirname(__file__), "ffmpeg_auto", "linux")

FFMPEG_BIN_WIN   = os.path.join(FFMPEG_DIR_WIN, "ffmpeg.exe")
FFMPEG_BIN_LINUX = os.path.join(FFMPEG_DIR_LINUX, "ffmpeg")

# Windows build from gyan.dev (most trusted Windows static build)
FFMPEG_URL_WIN = (
    "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
)

# Linux build from yt-dlp's official FFmpeg builds
FFMPEG_URL_LINUX = (
    "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/"
    "ffmpeg-master-latest-linux64-gpl.tar.xz"
)


async def ensure_ffmpeg() -> str:
    if IS_WINDOWS:
        return await _ensure_windows()
    else:
        return await _ensure_linux()


async def _ensure_windows() -> str:
    # 1. Already downloaded before
    if os.path.isfile(FFMPEG_BIN_WIN):
        print(f"[ffmpeg] Using cached Windows binary: {FFMPEG_BIN_WIN}")
        return FFMPEG_BIN_WIN

    # 2. Download
    print("[ffmpeg] Downloading FFmpeg for Windows...")
    os.makedirs(FFMPEG_DIR_WIN, exist_ok=True)
    archive_path = os.path.join(FFMPEG_DIR_WIN, "ffmpeg.zip")

    await _download(FFMPEG_URL_WIN, archive_path)

    # 3. Extract — find ffmpeg.exe inside the nested folder
    print("[ffmpeg] Extracting...")
    with zipfile.ZipFile(archive_path, "r") as z:
        for name in z.namelist():
            if name.endswith("/ffmpeg.exe") or name == "ffmpeg.exe":
                # Flatten — extract directly to FFMPEG_DIR_WIN/ffmpeg.exe
                data = z.read(name)
                with open(FFMPEG_BIN_WIN, "wb") as f:
                    f.write(data)
                break

    os.remove(archive_path)
    print(f"[ffmpeg] Ready: {FFMPEG_BIN_WIN}")
    return FFMPEG_BIN_WIN


async def _ensure_linux() -> str:
    # 1. System ffmpeg (e.g. Render pre-installs it someday)
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        print(f"[ffmpeg] System ffmpeg: {system_ffmpeg}")
        return system_ffmpeg

    # 2. Build-time binary (placed by build.sh)
    BUILD_BIN = os.path.join(os.path.dirname(__file__), "ffmpeg_auto", "linux", "ffmpeg")
    if os.path.isfile(BUILD_BIN) and os.access(BUILD_BIN, os.X_OK):
        print(f"[ffmpeg] Render build binary: {BUILD_BIN}")
        return BUILD_BIN

    # # 3. Fallback: download at runtime (only if build.sh somehow didn't run)
    # if os.path.isfile(FFMPEG_BIN_LINUX) and os.access(FFMPEG_BIN_LINUX, os.X_OK):
    #     print(f"[ffmpeg] Using cached Linux binary: {FFMPEG_BIN_LINUX}")
    #     return FFMPEG_BIN_LINUX

    print("[ffmpeg] Downloading FFmpeg for Linux...")
    import tarfile
    os.makedirs(FFMPEG_DIR_LINUX, exist_ok=True)
    archive_path = os.path.join(FFMPEG_DIR_LINUX, "ffmpeg.tar.xz")

    await _download(FFMPEG_URL_LINUX, archive_path)

    print("[ffmpeg] Extracting...")
    with tarfile.open(archive_path, "r:xz") as tar:
        for member in tar.getmembers():
            if member.name.endswith("/ffmpeg") and member.isfile():
                member.name = "ffmpeg"
                tar.extract(member, path=FFMPEG_DIR_LINUX)
                break

    st = os.stat(FFMPEG_BIN_LINUX)
    os.chmod(FFMPEG_BIN_LINUX, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    os.remove(archive_path)

    print(f"[ffmpeg] Ready: {FFMPEG_BIN_LINUX}")
    return FFMPEG_BIN_LINUX


async def _download(url: str, dest: str):
    """Shared async download helper with progress."""
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open(dest, "wb") as f:
                async for chunk in resp.content.iter_chunked(1024 * 256):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        print(f"\r[ffmpeg] Downloading... {downloaded/total*100:.1f}%", end="")
            print()