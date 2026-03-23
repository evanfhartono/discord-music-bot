#!/usr/bin/env bash
set -e

echo "[build] Installing Python dependencies..."
pip install -r requirements.txt

echo "[build] Downloading FFmpeg static binary for Linux..."
mkdir -p ./ffmpeg_auto/linux

curl -L \
  "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz" \
  -o /tmp/ffmpeg.tar.xz

echo "[build] Extracting..."
tar -xf /tmp/ffmpeg.tar.xz -C /tmp/

find /tmp -maxdepth 3 -name "ffmpeg" -type f -exec mv {} ./ffmpeg_auto/linux/ffmpeg \;

chmod +x ./ffmpeg_auto/linux/ffmpeg
rm -f /tmp/ffmpeg.tar.xz

echo "[build] FFmpeg ready:"
./ffmpeg_auto/linux/ffmpeg -version | head -1