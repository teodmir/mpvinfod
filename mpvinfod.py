#!/usr/bin/env python3
import socket
import json
import signal
import sys
import time
import pathlib
from inotify_simple import INotify, flags

RECV_CHUNK = 8192  # Size of byte chunks to read from the socket.
CLIENT_ID = 1  # Client ID to be used in mpv communication.
ADDR = '/tmp/mpvsocket'  # Location of the socket.
EMPTYSTR = ""  # Placeholder text to use when not active
MAXLEN = 100  # Maximum length of the output string

# Make this non-global
property_dict = {
    'media-title': None,
    'metadata/by-key/album': None,
    'volume': None,
    'loop-file': None
}


def signal_handler(sig, frame):
    """Empty the bar before exiting."""
    def_empty()
    sys.exit(0)


def observe(sock, prop):
    str = json.dumps({
        'command': ['observe_property', CLIENT_ID, prop]
    }) + '\n'
    sock.sendall(str.encode('UTF-8'))


def get_jsons(str):
    return list(map(json.loads, str.splitlines()))


def def_output(str):
    print(str, flush=True)


def def_empty():
    def_output(EMPTYSTR)


def get_newest_data(json_list, event):
    events = [
        j for j in json_list
        if list(map(j.get, ['event', 'id', 'name'])) ==
        ['property-change', CLIENT_ID, event]
    ]
    if not events:
        return None
    else:
        # Use empty string to differentiate between 'no events found' and
        # 'newest data is null'.
        return events[-1].get('data') or ''


def wait_connect(inotify, sockname):
    """Wait for the mpv server to start. This is done by using inotify to
passively listen for changes to the socket file and reconnecting
whenever a change occurs."""
    while True:
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(ADDR)
            return sock
        except ConnectionError:
            # Socket unavailable; wait for changes to the address
            found = False
            while not found:
                for event in inotify.read():
                    if event.name == sockname:
                        found = True
            # Hack; sometimes connection refused otherwise (why?)
            time.sleep(0.1)


def format_properties():
    """Convert the property dict to a string suitable for output."""
    title = property_dict['media-title']
    if not title:
        return None
    album = property_dict['metadata/by-key/album']
    album_str = f' | {album}' if album else ''
    volume = property_dict['volume']
    volume_str = f'({str(int(volume))}%)' if volume else ''
    repeat = property_dict['loop-file']
    repeat_str = ' (r) ' if repeat else ' '
    full = f'{volume_str}{repeat_str}{title}{album_str}'
    output = full if len(full) <= MAXLEN else full[0:MAXLEN] + "..."
    return output


def empty_or_default(s, default):
    """Use 'or' without using the empty string as a false value."""
    return '' if s == '' else s or default


def new_dict(json_list):
    """Update the property dict (if newer values are available)."""
    return {
        k: empty_or_default(get_newest_data(json_list, k), v)
        for k, v in property_dict.items()
    }


def request_observers(sock):
    """Send observe requests to mpv."""
    for event in property_dict.keys():
        observe(sock, event)


def end_session(sock):
    def_empty()
    # For some reason, connect() will reuse the old socket unless we wait a bit
    # (TIME_WAIT state?), resulting in a broken pipe error when sending the
    # data. This hack ensures that a fresh socket is used.
    time.sleep(0.1)


def run_observer(sock):
    """Main program loop."""
    global property_dict
    reset_dict()
    while True:
        try:
            contents = sock.recv(RECV_CHUNK)
        except ConnectionResetError:
            end_session(sock)
            return
        if not contents:  # Connection closed.
            end_session(sock)
            return
        json_list = get_jsons(contents.decode('UTF-8', 'ignore'))
        # Update the dictionary and output only when necessary: that is, only
        # when any of the observed properties have new values.
        new = new_dict(json_list)
        if new != property_dict:
            property_dict = new
            def_output(format_properties())


def reset_dict():
    """Set all property dict values to None."""
    for k in property_dict.keys():
        property_dict[k] = None


def run():
    signal.signal(signal.SIGINT, signal_handler)
    def_empty()
    inotify = INotify()
    watch_flags = flags.CREATE
    watch_dir = pathlib.Path(ADDR).parent
    watch_file = pathlib.Path(ADDR).stem
    inotify.add_watch(watch_dir, watch_flags)
    while True:
        # Using garbage collection to close the socket instead of an explicit
        # close() call.
        with wait_connect(inotify, watch_file) as sock:
            request_observers(sock)
            run_observer(sock)


if __name__ == "__main__":
    run()
