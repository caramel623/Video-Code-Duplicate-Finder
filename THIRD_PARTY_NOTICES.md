# Third-party notices

## FFmpeg

This project bundles `ffmpeg.exe` and `ffprobe.exe`, stored with Git LFS,
and ships them inside the PyInstaller bundle (`dist/VideoFinder.exe`).

The exact binaries are a public **FFmpeg** build:

- Version/build: `N-126390-g9fc8c785e2-20260903`
- Prebuilt by Gyan D.: <https://www.gyan.dev/ffmpeg/builds/>
- Source: <https://github.com/FFmpeg/FFmpeg>
- License: **GNU General Public License v3 (GPL v3)** - the build was
  configured with `--enable-gpl --enable-version3`.

The FFmpeg binaries are not covered by this project's MIT License. They are
distributed as separate, unmodified public builds and are invoked by the
application as external command-line processes (they are not linked into the
Python code), so the GPL does not require this application's own source to be
released; the FFmpeg binaries themselves remain under GPL v3.

GPL v3 compliance (redistribution):

- The full license text ships in [`licenses/ffmpeg-GPL.txt`](licenses/ffmpeg-GPL.txt).
- The exact build configuration is reproducible from `ffmpeg -version` /
  `ffmpeg -buildconf` plus the FFmpeg source repository above.
- A written offer is made to provide the complete corresponding source for the
  FFmpeg binaries; the identical prebuilt binaries can also be downloaded from
  <https://www.gyan.dev/ffmpeg/builds/>.
- Some libraries linked into the FFmpeg build carry their own licenses (LGPL,
  BSD, etc.); those terms apply to the respective libraries.

## PySide6 / Qt

PySide6 (Qt for Python) is used as a separate library and is available under
the GNU Lesser General Public License v3 (LGPLv3), the GNU General Public
License (GPL), or a commercial license. See <https://www.qt.io/licensing> for
the full terms.

A plain-text copy of these notices ships in the program folder at
[`licenses/THIRD_PARTY_NOTICES.txt`](licenses/THIRD_PARTY_NOTICES.txt).
