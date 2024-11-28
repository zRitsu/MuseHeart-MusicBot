# Créditos: Devoxin (lavalink.py)
# https://github.com/devoxin/Lavalink.py/blob/development/lavalink/utils.py

import struct
from base64 import b64encode
from io import BytesIO
from typing import Final, Dict, Any, Mapping, Callable, Optional, Tuple

V2_KEYSET = {'title', 'author', 'length', 'identifier', 'isStream', 'uri', 'sourceName', 'position'}
V3_KEYSET = V2_KEYSET | {'artworkUrl', 'isrc'}

class _MissingObj:
    __slots__ = ()

    def __repr__(self):
        return '...'


MISSING: Any = _MissingObj()

class DataWriter:
    __slots__ = ('_buf',)

    def __init__(self):
        self._buf: Final[BytesIO] = BytesIO()

    def _write(self, data):
        self._buf.write(data)

    def write_byte(self, byte):
        self._buf.write(byte)

    def write_boolean(self, boolean: bool):
        enc = struct.pack('B', 1 if boolean else 0)
        self.write_byte(enc)

    def write_unsigned_short(self, short: int):
        enc = struct.pack('>H', short)
        self._write(enc)

    def write_int(self, integer: int):
        enc = struct.pack('>i', integer)
        self._write(enc)

    def write_long(self, long_value: int):
        enc = struct.pack('>Q', long_value)
        self._write(enc)

    def write_nullable_utf(self, utf_string: Optional[str]):
        self.write_boolean(bool(utf_string))

        if utf_string:
            self.write_utf(utf_string)

    def write_utf(self, utf_string: str):
        utf = utf_string.encode('utf8')
        byte_len = len(utf)

        if byte_len > 65535:
            raise OverflowError('UTF string may not exceed 65535 bytes!')

        self.write_unsigned_short(byte_len)
        self._write(utf)

    def finish(self) -> bytes:
        with BytesIO() as track_buf:
            byte_len = self._buf.getbuffer().nbytes
            flags = byte_len | (1 << 30)
            enc_flags = struct.pack('>i', flags)
            track_buf.write(enc_flags)

            self._buf.seek(0)
            track_buf.write(self._buf.read())
            self._buf.close()

            track_buf.seek(0)
            return track_buf.read()

def _write_track_common(track: Dict[str, Any], writer: DataWriter):
    writer.write_utf(track['title'].encode('ascii', 'ignore').decode('ascii'))
    writer.write_utf(track['author'].encode('ascii', 'ignore').decode('ascii'))
    writer.write_long(track['length'])
    writer.write_utf(track['identifier'])
    writer.write_boolean(track['isStream'])
    writer.write_nullable_utf(track['uri'])



def encode_track(track: Dict[str, Any],
                 source_encoders: Mapping[str, Callable[[DataWriter, Dict[str, Any]], None]] = MISSING) -> Tuple[int, str]:
    """
    Encodes a track dict into a base64 string, readable by the Lavalink server.

    A track should have *at least* the following keys:
    ``title``, ``author``, ``length``, ``identifier``, ``isStream``, ``uri``, ``sourceName`` and ``position``.

    If the track is a v3 track, it should have the following additional fields:
    ``artworkUrl`` and ``isrc``. isrc can be ``None`` if not applicable.

    Parameters
    ----------
    track: Dict[str, Union[Optional[str], int, bool]]
        The track dict to serialize.
    source_encoders: Mapping[:class:`str`, Callable[[:class:`DataWriter`]]
        A mapping of source-specific encoders to use.
        Some Lavaplayer sources have additional fields encoded on a per-source manager basis, so you can
        specify a mapping of encoders that will handle encoding these additional fields. This isn't required
        for all sources, so ensure that you need them before specifying.

        The mapping must be in the format of something like ``{'http': http_encoder_function}``, where the
        key ``str`` is the name of the source. These functions will only be called if track's ``sourceName``
        field matches.

    Raises
    ------
    :class:`InvalidTrack`
        If the track has unexpected, or missing keys, possibly due to an incompatible version or another reason.

    Returns
    -------
    Tuple[int, str]
        A tuple containing (track_version, encoded_track).
        For example, if a track was encoded as version 3, the return value will be ``(3, '...really long track string...')``.
    """
    track_keys = track.keys()  # set(track) is faster for larger collections, but slower for smaller.

    if not V2_KEYSET <= track_keys:  # V2_KEYSET contains the minimum number of fields required to successfully encode a track.
        missing_keys = [k for k in V2_KEYSET if k not in track]

        raise Exception(
            f'Track object is missing keys required for serialization: {", ".join(missing_keys)}'
        )

    if V3_KEYSET <= track_keys:
        return (3, encode_track_v3(track, source_encoders))

    return (2, encode_track_v2(track, source_encoders))

def encode_track_v2(track: Dict[str, Any],
                    source_encoders: Mapping[str, Callable[[DataWriter, Dict[str, Any]], None]] = MISSING) -> str:
    assert V2_KEYSET <= track.keys()

    writer = DataWriter()

    version = struct.pack('B', 2)
    writer.write_byte(version)
    _write_track_common(track, writer)
    writer.write_utf(track['sourceName'])

    if source_encoders is not MISSING and track['sourceName'] in source_encoders:
        source_encoders[track['sourceName']](writer, track)

    writer.write_long(track['position'])

    enc = writer.finish()
    return b64encode(enc).decode()

def encode_track_v3(track: Dict[str, Any],
                    source_encoders: Mapping[str, Callable[[DataWriter, Dict[str, Any]], None]] = MISSING) -> str:
    assert V3_KEYSET <= track.keys()

    writer = DataWriter()
    version = struct.pack('B', 3)
    writer.write_byte(version)
    _write_track_common(track, writer)
    writer.write_nullable_utf(track['artworkUrl'])
    writer.write_nullable_utf(track['isrc'])
    writer.write_utf(track['sourceName'])

    if source_encoders is not MISSING and track['sourceName'] in source_encoders:
        source_encoders[track['sourceName']](writer, track)

    writer.write_long(track['position'])

    enc = writer.finish()
    return b64encode(enc).decode()
