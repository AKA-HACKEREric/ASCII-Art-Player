<div align="center">

# 🎞 ASCII Art Player

A modern real-time ASCII media player built with Python.

Transform videos, images, and audio into colorful ASCII art with customizable rendering and color grading.

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Windows-blue)
![License](https://img.shields.io/badge/License-MIT-green)

</div>

---

# 📸 Screenshots

> Coming Soon...

| Main Window | Video Playback |
| ------------ | -------------- |
| ![](docs/images/main.png) | ![](docs/images/video.png) |

| Color Grading | Audio Visualizer |
| -------------- | ---------------- |
| ![](docs/images/color.png) | ![](docs/images/audio.png) |

---

# ✨ Features

- 🎥 Play videos as real-time ASCII art
- 🖼️ Display images in ASCII
- 🎵 Audio waveform visualization
- 🎨 Brightness, Contrast, Exposure, Gamma and Saturation controls
- 🌈 RGB Color Grading
- ⚡ GPU-aware rendering presets
- 🖱️ Drag & Drop support
- ⌨️ Keyboard shortcuts
- 📺 Fullscreen mode
- 🔊 FFmpeg audio playback
- 🧵 Multi-threaded rendering pipeline

---

# 📦 Requirements

- Python 3.11+
- Windows 10 / 11
- FFmpeg (Recommended)

---

# 📥 Installation

Clone the repository

```bash
git clone https://github.com/AKA-HACKEREric/ascii-player.git
cd ascii-player
```

Install dependencies

```bash
pip install numpy pillow opencv-python tkinterdnd2
```

(Optional)

```bash
pip install imageio
```

Install FFmpeg

1. Download FFmpeg
2. Add it to your system PATH
3. Verify installation

```bash
ffmpeg -version
```

Run the project

```bash
python ascii_player.py
```

---

# 📁 Project Structure

```text
ascii-player/
│
├── docs/
│   └── images/
├── assets/
├── README.md
├── requirements.txt
├── ascii_player.py
└── LICENSE
```

---

# ⌨️ Keyboard Shortcuts

| Key | Action |
|------|--------|
| Space | Play / Pause |
| ← → | Seek |
| J / L | Skip 10 Seconds |
| M | Mute |
| F11 | Fullscreen |
| Esc | Exit Fullscreen |

---

# 🛠 Built With

- Python
- OpenCV
- Pillow
- NumPy
- Tkinter
- TkinterDnD2
- FFmpeg

---

# 🚀 Roadmap

- [x] Video Playback
- [x] Image Viewer
- [x] Audio Visualization
- [x] Color Grading
- [x] GPU Detection
- [ ] Linux Support
- [ ] macOS Support
- [ ] Plugin System
- [ ] Theme Support

---

# 🤝 Contributing

Pull requests and suggestions are welcome!

If you find a bug or have an idea, feel free to open an Issue.

---

# 📄 License

This project is licensed under the MIT License.

---

# 👨‍💻 Author

**HACKEREric**

GitHub:
https://github.com/AKA-HACKEREric
