"""MIT License

Copyright (c) 2019-2020 PythonistaGuild

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


class WavelinkException(Exception):
    """Base Wavelink Exception."""


class NodeOccupied(WavelinkException):
    """Exception raised when node identifiers conflict."""


class InvalidIDProvided(WavelinkException):
    """Exception raised when an invalid ID is passed somewhere in Wavelink."""


class ZeroConnectedNodes(WavelinkException):
    """Exception raised when an operation is attempted with nodes, when there are None connected."""


class AuthorizationFailure(WavelinkException):
    """Exception raised when an invalid password is provided toa node."""


class BuildTrackError(WavelinkException):
    """Exception raised when a track is failed to be decoded and re-built."""

class TrackNotFound(WavelinkException):
    pass

class MissingSessionID(WavelinkException):

    __slots__ = ('node')

    def __init__(self, node):
        self.node = node

class TrackLoadError(WavelinkException):
    """There was an error while loading a track."""

    __slots__ = ('error', 'node', 'severity', 'cause')

    def __init__(self, node, error, data):
        self.error = error
        self.node = node
        self.data = data
        self.exception = data.get('exception', {})
        self.severity = self.exception.get('severity')
        self.message = f"{self.node.identifier} - {self.exception.get('message')}"
        self.cause = self.exception.get('cause', '')

    def __repr__(self):
        return self.message

    def __str__(self):
        return self.message
