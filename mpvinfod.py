#!/usr/bin/env python3
import socket
import json
import signal
import sys
import time
import pathlib
from string import Template
from inotify_simple import INotify, flags

RECV_CHUNK = 8192  # Size of byte chunks to read from the socket.
CLIENT_ID = 1  # Client ID to be used in mpv communication.
ADDR = '/tmp/mpvsocket'  # Location of the socket.
EMPTYSTR = ""  # Placeholder text to use when not active


default_format = [
    {
        'property': 'volume',
        'format': "($p%) ",
        'max_length': 10,
        'shorten_str': '...'
    },
    {
        'property': 'media-title',
        'format': "$p",
        'max_length': 80,
        'shorten_str': '...'
    },
    {
        'property': 'metadata/by-key/album',
        'format': " | $p",
        'max_length': 50,
        'shorten_str': '...'
    }
 ]


# Cached values of properties of properties to their indices in
# default_format.
property_index_cache = {}


# Formatted strings in the order of default_format. Empty strings are used for
# values that don't exist yet.
formatted_cache = []


def format_cached():
    "Concatenate formatted_cache."
    return ''.join(formatted_cache)


def wait():
    time.sleep(0.1)


def format_property(prop_name, prop_value):
    spec = default_format[property_index_cache[prop_name]]
    max_len = spec['max_length']
    is_too_long = len(prop_value) > max_len
    shortened = ((prop_value[:max_len] + spec['shorten_str'])
                 if is_too_long else prop_value)
    formatted = Template(spec['format']).substitute(p=shortened)
    return formatted


def signal_handler(sig, frame):
    """Empty the bar before exiting."""
    output_empty()
    sys.exit(0)


def observe(sock, prop):
    str = json.dumps({
        'command': ['observe_property_string', CLIENT_ID, prop]
    }) + '\n'
    sock.sendall(str.encode('UTF-8'))


def get_jsons(str):
    "Return list of jsons "
    return list(map(json.loads, str.splitlines()))


def output(str):
    "Output the status bar message. Just print it."
    print(str, flush=True)


def output_empty():
    output(EMPTYSTR)


def get_newest_data(json_list, event):
    """Get the newest value for the provided event in the json list.
Returns None if no new values exist.
"""
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
    """Wait for the mpv server to start.

This is done by using inotify to
passively listen for changes to the socket file and reconnecting
whenever a change occurs.
"""
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
            wait()


def request_observers(sock):
    """Send observe requests to mpv based on properties."""
    for spec in default_format:
        observe(sock, spec['property'])


def end_session(sock):
    output_empty()
    # For some reason, connect() will reuse the old socket unless we wait a bit
    # (TIME_WAIT state?), resulting in a broken pipe error when sending the
    # data. This hack ensures that a fresh socket is used.
    wait()


def run_observer(sock):
    """Main program loop.

Read from the mpv socket until the connection is closed.
"""
    # Ensure empty cache when starting.
    reset_format_cache()
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
        for spec in default_format:
            prop = spec['property']
            value = get_newest_data(json_list, prop)
            if value:
                formatted_cache[property_index_cache[prop]] = format_property(prop, value)
        output(format_cached())
        # Update the dictionary and output only when necessary: that is, only
        # when any of the observed properties have new values.


def generate_prop_index():
    global default_format
    for idx, spec in enumerate(default_format):
        property_index_cache[spec['property']] = idx


def reset_format_cache():
    global formatted_cache
    formatted_cache = [''] * len(default_format)


def run():
    generate_prop_index()
    signal.signal(signal.SIGINT, signal_handler)
    output_empty()
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
