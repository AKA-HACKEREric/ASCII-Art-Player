# ASCII Art Player

![Python](https://img.shields.io/badge/Python-3.8+-blue)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)
![License](https://img.shields.io/badge/License-MIT-green)

Play images and videos as real-time ASCII art in a desktop GUI.

Drop a file, hit play, and watch photos or video rendered with a dense character atlas (Latin, CJK, and Japanese kana). GPU-aware auto-scaling keeps playback smooth on weaker machines.

## Features

- Image and video playback with ASCII rendering
- Drag-and-drop support (via `tkinterdnd2`)
- Audio playback through `ffplay` (optional, requires FFmpeg)
- Keyboard shortcuts for seek, speed, mute, and fullscreen
- Settings panel for quality, resolution presets, and display rate
- Fullscreen mode with auto-hiding controls

## Requirements

- Windows 10 / 11
- Python 3.8+
- `opencv-python`, `numpy`, `Pillow`
- Optional: `tkinterdnd2` for drag-and-drop
- Optional: FFmpeg (`ffplay`) for video audio

## Installation

```bash
git clone https://github.com/AKA-HACKEREric/ascii-art-player.git
cd ascii-art-player
python -m pip install -r requirements.txt
```

## Usage

```bash
python ascii_player.py
```

Open a file from the UI or drag one onto the window. Supported formats include common image and video extensions (PNG, JPG, MP4, MKV, and more).

## Keyboard Shortcuts

| Key | Action |
| --- | --- |
| Space / k | Play / Pause |
| j / l | Seek back / forward 10 s |
| ??/ ??| Seek back / forward 5 s |
| , / . | Step frame while paused |
| < / > | Speed ±0.25? |
| 0?? | Jump to 0%??0% |
| m | Toggle mute |
| f / F11 | Toggle fullscreen |
| Esc | Exit fullscreen |

## License

MIT
