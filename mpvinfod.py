#!/usr/bin/env python3
import socket
import json
import signal
import sys
import time
import pathlib
import os
import os.path
from string import Template
from inotify_simple import INotify, flags

RECV_CHUNK = 32768  # Max size of bytes to read from the socket.
CLIENT_ID = 1  # Client ID to be used in mpv communication.
ADDR = '/tmp/mpvsocket'  # Location of the socket.
EMPTYSTR = ''  # Placeholder text to use when not active


default_config = [
    {
        'property': 'loop-file',
        'format': '$p ',
        'replace_map': {
            'no': '',
            'inf': '(r)'
        },
        'max_length': 5
    },
    {
        'property': 'volume',
        'format': "($p%) ",
        'type': 'int',
        'max_length': 5,
    },
    {
        'property': 'media-title',
        'format': '$p',
        'max_length': 80,
    },
    {
        'property': 'metadata/by-key/album',
        'format': ' | $p',
        'max_length': 50,
    }
 ]


default_spec_values = {
    'type': 'string',
    'format': '$p',
    'max_length': 50,
    'shorten_str': '...',
    'replace_map': {}
}


user_config = default_config


# Formatted strings in the order of default_config. Empty strings are used for
# values that don't exist yet.
# formatted_cache = []


# def format_cached():
#     "Concatenate formatted_cache."
#     return ''.join(formatted_cache)


def wait():
    "Hacky solution for some bugs relating to socket connections."
    time.sleep(0.1)


def format_property(prop_spec, prop_value):
    "Form prop_value according to its specification."
    # prop_spec = user_config[property_index_cache[prop_name]]
    if prop_spec['type'] == 'int':
        prop_value = str(int(prop_value))

    replace_val = prop_spec['replace_map'].get(prop_value)
    if replace_val is not None:
        prop_value = replace_val

    max_len = prop_spec['max_length']
    is_too_long = len(prop_value) > max_len
    shortened = ((prop_value[:max_len] + prop_spec['shorten_str'])
                 if is_too_long else prop_value)
    formatted = Template(prop_spec['format']).substitute(p=shortened)
    return formatted


def signal_handler(sig, frame):
    """Empty the bar before exiting."""
    output_empty()
    sys.exit(0)


def observe(sock, prop, str=True):
    """Observe the given property. By default all properties will be strings,
    but with the named argument str set to False, return the property in its
    native form.
    """
    cmd = 'observe_property_string' if str else 'observe_property'
    str = json.dumps({
        'command': [cmd, CLIENT_ID, prop]
    }) + '\n'
    sock.sendall(str.encode('UTF-8'))


def get_jsons(str):
    "Parse a string as a line-delimited list of JSON objects."
    return list(map(json.loads, str.splitlines()))


def output(str):
    "Output the given message."
    print(str, flush=True)


def output_empty():
    "Output placeholder string."
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
    if not events:  # No events at all
        return None
    else:
        data = events[-1].get('data')
        # Use empty string to differentiate between 'no events found' and
        # 'newest data is null'.
        return data or ''


def wait_connect(inotify, sockname):
    """Wait for the mpv server to start and return the socket.

This is done by using inotify to passively listen for changes to the socket
file and reconnecting whenever a change occurs. Could be done with a timer as
well, but this has performance advantages.
"""
    while True:
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(ADDR)
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
    for spec in config:
        as_str = spec['type'] == 'string'
        observe(sock, spec['property'], as_str)


def end_session(sock):
    output_empty()
    # For some reason, connect() will reuse the old socket unless we wait a bit
    # (TIME_WAIT state?), resulting in a broken pipe error when sending the
    # data. This hack ensures that a fresh socket is used.
    wait()


def run_observer(sock, prop_index):
    """Main program loop.

Read from the mpv socket until the connection is closed.
Needs a prop_index that maps property names to indices in
"""
    # Ensure empty cache when starting.
    formatted_cache = []
    while True:
        try:
            contents = sock.recv(RECV_CHUNK)
        except ConnectionResetError:
            end_session(sock)
            return
        if not contents:  # Connection closed.
            end_session(sock)
            return
        # Make sure no errors are raised when decoding due to strange
        # encodings.
        json_list = get_jsons(contents.decode('UTF-8', 'ignore'))
        for spec in user_config:
            prop = spec['property']
            value = get_newest_data(json_list, prop)
            if value == '':
                # If the string is empty the property is no longer available,
                # so it shouldn't be formatted.
                formatted_cache[prop_index[prop]] = ''
            elif value is not None:
                formatted_cache[prop_index[prop]] = format_property(
                    prop, value)
        output(format_cached())


def generate_prop_index(config):
    "Map the properties in the user_config to indices"
    return {spec['property']: idx for idx, spec in enumerate(config)}
    # for idx, spec in enumerate(config):
    #     property_index_cache[spec['property']] = idx


def reset_format_cache():
    global formatted_cache
    formatted_cache = [''] * len(user_config)


def fix_config(config):
    """Fix the provided dictionary.

Involves adding default values, ensuring properties are only used once, etc.
Returns the newly created configuration. Throws an exception if there are
errors.
"""
    merged_config = [{}] * len(config)
    for idx, spec in enumerate(config):
        merged_config[idx] = {**default_spec_values, **spec}
    return merged_config


def find_config_file():
    """Find the configuration file; return None if none exists. Either
$XDG_CONFIG_HOME/mpvinfod/config.json or ~/.config/mpvinfod/config.json
"""
    config_dir = (os.getenv('XDG_CONFIG_HOME') or
                  os.path.join(os.path.expanduser('~'), '.config'))
    config_sub_path = os.path.join('mpvinfod', 'config.json')
    config_file = os.path.join(config_dir, config_sub_path)
    return config_file if os.path.isfile(config_file) else None


def run():
    "Set up the program loop and run it."
    global user_config
    config_file = find_config_file()
    if config_file:
        with open(config_file) as f:
            user_config = json.load(f)
    user_config = fix_config(user_config)

    prop_index = generate_prop_index(user_config)

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
            request_observers(sock, user_config)
            run_observer(sock, prop_index)


if __name__ == "__main__":
    run()
