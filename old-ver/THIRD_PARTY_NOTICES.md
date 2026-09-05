# Third-party notices

## FFmpeg

FFmpeg and ffprobe are not included in this repository and are not covered by
this project's MIT License. Users may configure separately obtained FFmpeg
executables in the application's settings page.

FFmpeg is licensed separately by its copyright holders, generally under the
GNU Lesser General Public License (LGPL) version 2.1 or later. Builds that
enable optional GPL components are governed by the GPL, and builds containing
non-free components may not be redistributable. Consult the license and build
configuration of the exact FFmpeg binaries being used:

- https://ffmpeg.org/legal.html
- `ffmpeg.exe -version`
- `ffmpeg.exe -buildconf`

Anyone redistributing FFmpeg with this application is responsible for
complying with the license terms of that exact FFmpeg build.
