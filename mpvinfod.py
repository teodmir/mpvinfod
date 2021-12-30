#!/usr/bin/env python3
import socket
import json
import signal
import sys
import time
import pathlib
import os
import os.path
from string import Formatter
from inotify_simple import INotify, flags

RECV_CHUNK = 32768  # Max size of bytes to read from the socket.

default_config = {
    "format": "mpv: {media-title}",
    "empty": "",
    "socket": "/tmp/mpvsocket",
    "client_id": 1
}


# Default value to use for property customizations.
default_custom_values = {
    'format': '{prop}',
    'max_length': 50,
    'shorten_str': '...',
    'replace': {},
    'as_int': False
}


def wait():
    "Hacky solution for some bugs relating to socket connections."
    time.sleep(0.1)


def format_property(prop_custom, prop_value):
    "Form prop_value according to its customification."
    if prop_custom['as_int']:
        prop_value = str(int(prop_value))

    replace_val = prop_custom['replace'].get(prop_value)
    if replace_val is not None:
        prop_value = replace_val

    # Empty replacement strings are treated specially; treated as if they were
    # empty to begin with.
    if replace_val == '':
        return ''

    max_len = prop_custom['max_length']
    is_too_long = len(prop_value) > max_len
    shortened = ((prop_value[:max_len] + prop_custom['shorten_str'])
                 if is_too_long else prop_value)
    formatted = prop_custom['format'].format(prop=shortened)
    return formatted


def observe(sock, prop, client_id, native=False):
    """Observe the given property. By default all properties will be strings,
    but with the named argument 'native' set to True, return the property in
    its native form.
    """
    cmd = 'observe_property' if native else 'observe_property_string'
    str = json.dumps({
        'command': [cmd, client_id, prop]
    }) + '\n'
    sock.sendall(str.encode('UTF-8'))


def get_jsons(str):
    "Parse a string as a line-delimited list of JSON objects."
    return list(map(json.loads, str.splitlines()))


def output(str):
    "Output the given message."
    print(str, flush=True)


def get_newest_data(json_list, event, client_id):
    """Get the newest value for the provided event in the json list.
Returns None if no new values exist.
"""
    events = [
        j for j in json_list
        if list(map(j.get, ['event', 'id', 'name'])) ==
        ['property-change', client_id, event]
    ]
    if not events:  # No events at all
        return None
    else:
        data = events[-1].get('data')
        # Use empty string to differentiate between 'no events found' and
        # 'newest data is null'.
        return data if data is not None else ''


def wait_connect(inotify, sockname, addr):
    """Wait for the mpv server to start and return the socket.

This is done by using inotify to passively listen for changes to the socket
file and reconnecting whenever a change occurs. Could be done with a timer as
well, but this has performance advantages.
"""
    while True:
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(addr)
            return sock
        except ConnectionError:
            # Socket unavailable; wait for changes to the address.
            found = False
            while not found:
                for event in inotify.read():
                    if event.name == sockname:
                        found = True
            # Hack; sometimes connection refused otherwise (why?)
            wait()


def request_observers(sock, config):
    "Send observe requests to mpv based on the properties given."
    props = get_requested_properties(config)
    for p in props:
        as_int = config['custom'][p]['as_int']
        observe(sock, p, config['client_id'], as_int)


def end_session(end_str):
    output(end_str)
    # For some reason, connect() will reuse the old socket unless we wait a bit
    # (TIME_WAIT state?), resulting in a broken pipe error when sending the
    # data. This hack ensures that a fresh socket is used.
    wait()


def run_observer(sock, config):
    """Main program loop.

Read from the mpv socket until the connection is closed.
Needs a prop_index that maps property names to indices in
"""
    props = get_requested_properties(config)
    # A map of property names to their formatted values.
    property_cache = {p: '' for p in props}
    while True:
        try:
            contents = sock.recv(RECV_CHUNK)
        except ConnectionResetError:
            end_session(config['empty'])
            return
        if not contents:  # Connection closed.
            end_session(config['empty'])
            return
        # Make sure no errors are raised when decoding due to strange
        # encodings.
        json_list = get_jsons(contents.decode('UTF-8', 'ignore'))
        for prop in props:
            value = get_newest_data(json_list, prop, config['client_id'])
            if value == '':
                # If the string is empty the property is no longer available
                # (an example being a new song having no album title), so it
                # shouldn't be formatted, since it might show the old name.
                property_cache[prop] = ''
            elif value is not None:
                property_cache[prop] = format_property(config['custom'][prop],
                                                       value)
        output(config['format'].format(**property_cache))


def fix_config(config):
    """Fix the provided dictionary.

Involves adding default values, ensuring properties are only used once, etc.
Returns the newly created configuration. Throws an exception if there are
errors.
"""
    props = get_requested_properties(config)

    # Use default values for all configuration options except custom, which has
    # its own default format.
    for key, val in default_config.items():
        if key != 'custom' and key != 'format':
            config[key] = val

    # Create custom section if it doesn't exist and fill it with default
    # values for each property in the format string. .
    if 'custom' not in config:
        config['custom'] = {}
    for p in props:
        #
        config['custom'][p] = {**default_custom_values,
                               **(config['custom'].get(p) or {})}
    return config


def find_config_file():
    """Find the configuration file; return None if none exists. Either
$XDG_CONFIG_HOME/mpvinfod/config.json or ~/.config/mpvinfod/config.json
"""
    config_dir = (os.getenv('XDG_CONFIG_HOME') or
                  os.path.join(os.path.expanduser('~'), '.config'))
    config_sub_path = os.path.join('mpvinfod', 'config.json')
    config_file = os.path.join(config_dir, config_sub_path)
    return config_file if os.path.isfile(config_file) else None


def get_requested_properties(config):
    """Find the properties listed in the format string."""
    return [
        fn for _, fn, _, _ in
        Formatter().parse(config['format']) if fn is not None
    ]


def run():
    "Set up the program loop and run it."
    config_file = find_config_file()
    if config_file:
        with open(config_file) as f:
            user_config = fix_config(json.load(f))
    else:
        user_config = fix_config(default_config)

    def signal_handler(sig, frame):
        """Empty the bar before exiting."""
        output(user_config['empty'])
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    # Output the placeholder string to begin with.
    output(user_config['empty'])

    addr = user_config['socket']

    inotify = INotify()
    watch_flags = flags.CREATE
    watch_dir = pathlib.Path(addr).parent
    watch_file = pathlib.Path(addr).stem
    inotify.add_watch(watch_dir, watch_flags)
    while True:
        # Using garbage collection to close the socket instead of an explicit
        # close() call.
        with wait_connect(inotify, watch_file, addr) as sock:
            request_observers(sock, user_config)
            run_observer(sock, user_config)


if __name__ == "__main__":
    run()
