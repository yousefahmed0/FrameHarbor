# FrameHarbor

A Windows desktop application that saves frames from local videos or YouTube links as numbered PNG or JPG images.

## Download for Windows

Get **FrameHarbor-Windows.zip** from the [latest release](https://github.com/yousefahmed0/FrameHarbor/releases/latest). Extract the entire ZIP, open the `FrameHarbor` folder, and run `FrameHarbor.exe`. Keep `_internal` beside the executable.

## Use the application

1. Open `FrameHarbor.exe` in the `FrameHarbor` folder.
2. Select **Local file**, then click **Choose video**, or select **YouTube URL** and paste a video link.
3. Choose a save location, image format, and frame interval.
4. Leave the interval at **1** to save every frame. Set it to **5** to save frames 1, 6, 11, and so on.
5. Click **Export frames** for a local file, or **Download & export** for a YouTube link. Then click **Open output folder** when complete.

No installation, Python, Node.js, or FFmpeg setup is needed for the packaged app. Local-file exports work offline. YouTube downloads require internet access. Keep the entire application folder together, including `_internal`. To move it to another computer, copy the whole folder. Windows 10/11, 64-bit. The executable is unsigned.

YouTube accepts regular watch links, youtu.be links, and Shorts. The app downloads one video at its best available video resolution, then automatically extracts frames using your chosen settings. The downloaded source is retained under **YouTube downloads** inside your chosen save location; frames are in a separate folder named after the video. The source video may have no audio because frame extraction does not need it. Playlist parameters on a video link are ignored. Playlist-only links and active live streams are not supported. Private, age-restricted, sign-in-only, region-blocked, or otherwise unavailable videos may fail. The app does not read browser cookies or sign in to YouTube. Download errors appear in the app, with details in the download folder's `download.log`. YouTube can change its download requirements; the bundled downloader may need updating in a future build. Use videos you own or have permission to download.

Frames are named `frame_00000001.png`, `frame_00000002.png`, etc. Each export creates a new subfolder named after the video and the export time. Existing exports are preserved. `export.json` records the source, settings, count, and completion state; `export.log` contains decoder warnings or errors.

PNG is lossless; JPG uses high-quality compression and usually takes less space. Frames retain decoded dimensions and FFmpeg's normal orientation handling. The app selects the first video stream, excludes cover art, and preserves its decoded frame order, including variable frame rates. Numbered images do not encode the original per-frame presentation timing. Audio and subtitles are not exported. HDR sources receive FFmpeg's standard image conversion without an HDR tone-mapping workflow. Damaged or encrypted inputs may fail.

Cancel stops the downloader or decoder and keeps files already written. Interrupted YouTube downloads may leave a partial source file in their download folder. Closing during export also cancels safely. A large or long video can create many thousands of files; allow enough disk space. Frame counts shown before export may be estimates for formats that do not store a count. The final count is based on actual saved files.

## Run or rebuild from source

Use Python 3.11+ with Tkinter, FFmpeg/FFprobe, and Node.js 22+ on PATH:

```powershell
python -m pip install -r requirements.txt
python app.py
python -m unittest -v
python build.py
```

The build writes a portable `FrameHarbor` folder beside this source folder. `build.py` bundles FFmpeg and Node.js from PATH, plus a SHA256-verified official yt-dlp Windows release downloaded by `prepare_tools.py`. The tests create temporary synthetic videos and check PNG/JPG exports, sampling, variable frame rate, Unicode paths, cancellation, folder isolation, URL validation, downloader failures, and the download-to-frames pipeline using a controlled downloader fixture. A live YouTube download was also verified during development.

## Dependencies and notices

The packaged decoder is FFmpeg 8.1 essentials from Gyan, built with GPL version 3 components. Its license and build documentation are in `licenses/`; its upstream source and build information are available at https://www.gyan.dev/ffmpeg/builds/ and https://ffmpeg.org/download.html. The FFmpeg binaries run as separate local processes. FFmpeg documentation: https://ffmpeg.org/ffmpeg.html. Python and third-party runtime notices are also included in the application folder. The app uses Pillow for previews and PyInstaller for packaging: https://python-pillow.github.io/ and https://pyinstaller.org/.

YouTube support uses the official yt-dlp Windows executable (2026.10.26) with its bundled EJS components and Node.js 24.14.1. Their licenses and downloader release checksum are in `licenses/`. Documentation and source: https://github.com/yt-dlp/yt-dlp, https://github.com/yt-dlp/yt-dlp/wiki/EJS, https://github.com/nodejs/node. All bundled tools run as separate subprocesses. No downloader settings from your other apps are loaded.

The application source files in this folder may be used and modified freely for personal or commercial purposes. Dependency licenses remain applicable to those dependencies.
