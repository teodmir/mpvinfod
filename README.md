# mpv info daemon
  Daemon that outputs information about the currently playing file of mpv,
  suitable for status bar output. This is a work in progress; while the output
  works as intended and is free from bugs in my experience, there is no
  customization and the output format is limited to [volume]% [mediatitle] |
  [album].

# Screenshot showing output in xmobar
![xmobar output](screenshot.png?raw=true "Title")

# Usage
  - mpvinfod uses mpv's socket IPC feature to observe events from mpv. To enable this, mpv needs to be started

# Dependencies
  - inotify-simple: used to monitor the mpv socket for changes and detect when
    the socket is started.

# Todo
  - JSON configuration with arbitrary mpv properties
  - command line arguments
