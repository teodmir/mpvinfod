# mpv info daemon
Daemon that outputs information about the currently playing file of mpv,
suitable for status bar output. This is a work in progress, but it should be
bug free as long as your configuration doesn't contain errors.

# Screenshot showing output in xmobar
![xmobar output](screenshot.png?raw=true "Title")

# Usage
  mpvinfod uses mpv's socket IPC feature to observe events from mpv. To enable
  this, mpv needs to be started with the `--input-ipc-server` option (see the
  mpv manual for details). Since it only makes sense to output information from
  a single instance of mpv (what would the output look like from multiple mpv
  instances?), you should either use a single instance of mpv (see the umpv
  script that is provided with mpv) or use a shell alias if you only want this
  feature enabled at certain times. I personally use mpv to play music this way
  and use a shell alias that disables video playback using `--vo=null` along
  with the IPC server location.

# Dependencies
  - inotify-simple: used to monitor the mpv socket for changes and detect when
    the socket is started.

# Configuration
mpvinfod uses a JSON configuration file located at
`${XDG_CONFIG_HOME}/mpvinfod/config.json` or `~/.config/mpvinfod/config` if
`XDG_CONFIG_HOME` is undefined. An example configuration is provided in
examples/config.json. The configuration itself consists of two parts: format,
which is a format string where mpv properties written as {property} are
replaced by the value of the corresponding mpv property. For a list of
available properties, see the "Property list" section of the mpv manual. As the
manual itself states, some options are also available as properties, such as
"mute".

The second part is the optional custom part, which defines how the property
should be display. Available properties are:

- empty: String to use when no video is available. Defaults to the empty string
  (empty output in the status bar)

- socket: The path to the socket. Defaults to /mpvsocket.

- client_id: The request identifier that should uniquely identify this
  application. If you aren't using anything else that uses the JSON IPC feature
  of mpv then you shouldn't have to change this. Defaults to 1.

- custom: "Property display customization" below.

## Property display customization
- format: How the string should be formatted; a format string inside the format
  string, basically. The placeholder text `{prop}` is replaced with the actual
  value. Useful for adding extra strings only when the property is present (see
  the volume and album customizations in the example configuration for ideas).
  Default: "{prop}"

- max_length: if the resulting string length is longer than this, then the
  string will be shortened. Default: 50 characters.

- shorten_str: String that is appended if the string was shortened.
  Default: "...".

- replace: An object that maps strings to strings; the key being a value to
  match, and the mapping being the value to replace it with.
