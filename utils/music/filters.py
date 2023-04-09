# -*- coding: utf-8 -*-
from typing import Union

from wavelink import WavelinkException


class InvalidFilterArgument(WavelinkException):
    """An invalid argument was passed to a filter."""
    pass


class AudioFilter:

    def __init__(self, filter_name: str, data: Union[dict, float, int]):

        self.filter_name = filter_name

        self.filter = {filter_name: data}

    @classmethod
    def volume(cls, vol: float = 1.0):

        return cls("volume", float(vol))

    @classmethod
    def equalizer(cls, bands: dict):

        return cls("equalizer", bands)

    @classmethod
    def distortion(cls, sin_offset: float = 0, sin_scale: float = 1.0, cos_offset: float = 0,
                   cos_scale: float = 1.0, tan_offset: float = 0, tan_scale: float = 1.0,
                   offset: float = 0, scale: float = 1.0):

        return cls(
            "distortion", {
                "sinOffset": float(sin_offset),
                "sinScale": float(sin_scale),
                "cosOffset": float(cos_offset),
                "cosScale": float(cos_scale),
                "tanOffset": float(tan_offset),
                "tanScale": float(tan_scale),
                "offset": float(offset),
                "scale": float(scale)
            }
        )

    @classmethod
    def timescale(cls, speed: float = 1.0, pitch: float = 1.0, rate: float = 1.0):

        if speed == 0:
            raise InvalidFilterArgument("Timescale speed must be more than 0.1")
        if pitch == 0:
            raise InvalidFilterArgument("Timescale pitch must be more than 0.1")
        if rate == 0:
            raise InvalidFilterArgument("Timescale rate must be more than 0.1")

        return cls(
            "timescale", {
                "speed": float(speed),
                "pitch": float(pitch),
                "rate": float(rate)
            }
        )

    @classmethod
    def tremolo(cls, frequency: float = 2.0, depth: float = 0):

        if frequency <= 0:
            raise InvalidFilterArgument("Tremolo frequency must be more than 0")

        if not 0.1 < depth < 1.1:
            raise InvalidFilterArgument("Tremolo frequency must be between 0,1 and 1.0")

        return cls(
            "tremolo", {
                "frequency": float(frequency),
                "depth": float(depth)
            }
        )

    @classmethod
    def vibrato(cls, frequency: float = 2.0, depth: float = 0):

        if frequency <= 0:
            raise InvalidFilterArgument("Vibrato frequency must be more than 0.")

        if not 0.1 < depth < 1.1:
            raise InvalidFilterArgument("Vibrato frequency must be between 0.1 and 1.0")

        return cls(
            "vibrato", {
                "frequency": int(frequency),
                "depth": float(depth)
            }
        )

    @classmethod
    def karaoke(cls, level: float = 1.0, mono_level: float = 1.0, filter_band: float = 220, filter_width: float = 110):

        return cls(
            "karaoke", {
                "level": float(level),
                "monoLevel": float(mono_level),
                "filterBand": float(filter_band),
                "filterWidth": float(filter_width)
            }
        )


    @classmethod
    def rotation(cls, sample_rate: int = 5):

        return cls("rotation", {"sampleRate": sample_rate})

    @classmethod
    def low_pass(cls, smoothing: float = 20.0):

        return cls("lowpass", {"smoothing": smoothing})

    @classmethod
    def channel_mix(cls, left_to_left: float = 1.0, left_to_right: float = 0, right_to_left: float = 0, right_to_right: float = 1.0):

        return cls(
            "channelmix", {
                "leftToLeft": left_to_left,
                "leftToRight": left_to_right,
                "rightToLeft": right_to_left,
                "rightToRight": right_to_right
            }
        )