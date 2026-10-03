# Frame Extractor

A desktop application for exploring videos, saving frames, and creating clips with audio. Built with Python, PySide6, and OpenCV, it features a dark liquid glass interface.

## Features

- **Capture and Clips modes:** a centered, two-position switch with an animated indicator for the active mode.
- **Frame capture:** save the current frame as PNG or JPG. Captures respect the crop selection and visible zoom area.
- **Precise navigation:** move one frame at a time, jump through the video, or seek on the timeline.
- **Audio playback:** listen to the video's audio while it plays in the app.
- **Filmstrip and recent videos:** browse clickable thumbnails and reopen recently used files.
- **Bookmarks:** mark frames of interest and export them as images.
- **Batch extraction:** save frames every N frames or seconds.
- **Multiple clips:** mark several start and end points in one video and manage the ranges in a clip list.
- **Two clip export options:** save each range as an individual MP4 or combine the ranges into one video in chronological order.
- **Audio in exported clips:** MP4 files are encoded as H.264 video and AAC audio for broad playback compatibility.
- **Persistent settings:** configure the output folder, image format and quality, scaling, and navigation preferences.

## Requirements

- Python 3.10 or later
- FFmpeg and FFprobe on your system `PATH` to export clips

The app uses Qt Multimedia for audio playback. Videos without an audio track play silently.

## Install and run

### Windows quick installation

1. Download and extract `Frame-Extractor-Windows.zip` to the folder where you want to keep the app.
2. Double-click `install.bat` and wait for installation to finish.
3. Launch **Frame Extractor** from the desktop shortcut.

The installer requires Python 3.10 or later and an Internet connection to download dependencies. It creates a virtual environment inside the extracted folder. If you move that folder, run `install.bat` again to update the shortcut. FFmpeg and FFprobe are optional for installation and required only for clip export.

### Manual installation

```bash
git clone https://github.com/Atrayant-I/frame-extractor.git
cd frame-extractor
python -m pip install -r requirements.txt
python main.py
```

On Windows, the app will notify you if FFmpeg is unavailable when you try to export clips. Install FFmpeg and make sure both `ffmpeg` and `ffprobe` can be run from a terminal.

## Using Clips mode

1. Open a video and select **Clips** with the centered switch at the top. The app's controls are labeled in Spanish.
2. Seek to the start frame and choose **Marcar inicio** (Mark start) or press `I`.
3. Seek to the end frame and choose **Marcar fin** (Mark end) or press `O`. The range is added to the list; repeat to add more clips.
4. Open **Clips** to review or remove ranges, then choose **Guardar clips individuales** (Save individual clips) or **Guardar video combinado** (Save combined video).
5. Clips are saved beside the original video by default. Use **Cambiar...** in the Clips window to choose a different destination folder for either export option.

Ranges are exported in their original chronological order. The marked end frame is included in each clip.

## Keyboard shortcuts

| Key | Action |
| --- | --- |
| `Space` | Save the current frame in Capturas mode; play or pause in Clips mode |
| `←` / `→` | Move to the previous or next frame |
| `Shift` + `←` / `→` | Jump backward or forward |
| `I` / `O` | Mark a clip's start or end in Clips mode |
| `M` | Toggle a bookmark in Capturas mode |
| `Ctrl` + `S` | Save the current frame |
| `Ctrl` + `O` | Open a video |
| `Ctrl` + `E` | Open the export folder |
| `Home` / `End` | Go to the first or last frame |

## Technologies

- Python
- PySide6 / Qt Widgets and Qt Multimedia
- OpenCV (`opencv-python`)
- FFmpeg / FFprobe for clip export

## License

This project is distributed under the MIT License. See [`LICENSE`](LICENSE) for details.
