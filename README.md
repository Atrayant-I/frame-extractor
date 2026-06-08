# Frame Extractor

A professional, high-performance desktop application for precise video frame extraction and navigation. Built with Python, OpenCV, and Tkinter, it features a modern dark-themed GUI designed for seamless user experience and millisecond-accurate seeking.

## About the Project

Frame Extractor is designed for developers, video editors, and researchers who need a lightweight, fast, and precise tool to navigate video files and extract specific frames. By separating the GUI thread from video decoding and caching operations via a persistent background preloader, Frame Extractor achieves near-zero latency seeking, solving common performance bottlenecks found in standard video player tools.

## Key Features

- **⚡ Hardware-Accelerated Seeking**: Employs a persistent worker thread (`PreloadWorker`) that keeps the video stream buffer open, eliminating the overhead of repeatedly reloading video container headers.
- **⏱️ Frame-Accurate Controls**: Navigate frame-by-frame with precision using arrow keys, or jump quickly by ±10 frames using `Shift + Arrows`.
- **🖱️ Drag & Drop Interface**: Drag any video file directly onto the main canvas for instant loading and preview.
- **🎞️ Dynamic Filmstrip**: Generates visual, clickable timeline thumbnails automatically upon video loading for fast timeline scrub jumps.
- **🔖 Multi-Frame Bookmarking**: Tag key frames during review and export them all at once into your designated directory.
- **📋 Batch Processing**: Automate frame extraction by saving one frame every N frames throughout the entire duration of the video.
- **⚙️ Configurable Presets**: Configure default export paths, output formats (PNG/JPG), and JPEG quality parameters that persist between sessions.
- **📜 Recent Workspace**: Remembers the last 8 opened video directories for quick access.

## Tech Stack

- **Core Logic**: Python 3.8+
- **Video Decoding**: OpenCV (`opencv-python`)
- **Image Processing**: Pillow (PIL)
- **GUI Engine**: Tkinter (with `tkinterdnd2` integration for drag & drop capabilities)

## Installation & Setup

1. **Clone the Repository**
   ```bash
   git clone https://github.com/Atrayant-I/frame-extractor.git
   cd frame-extractor
   ```

2. **Install Dependencies**
   Ensure you have Python installed, then run:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the Application**
   ```bash
   python main.py
   ```

## Keyboard Shortcuts Quick Reference

| Shortcut | Action |
| --- | --- |
| `Spacebar` | Toggle Play / Pause playback |
| `Left Arrow` | Step 1 frame backward |
| `Right Arrow` | Step 1 frame forward |
| `Shift + Left` | Jump 10 frames backward |
| `Shift + Right` | Jump 10 frames forward |
| `M` | Toggle bookmark on current frame |
| `Ctrl + S` | Save current frame instantly |
| `Ctrl + O` | Open file explorer to load a video |
| `Ctrl + E` | Open the export directory in system Explorer |
| `Home` | Seek to the first frame |
| `End` | Seek to the last frame |

## License

This software is released under the **MIT License**. Feel free to use, modify, and distribute it for personal and commercial applications.
