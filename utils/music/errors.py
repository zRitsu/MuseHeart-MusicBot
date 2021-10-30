from disnake.ext import commands

class GenericError(commands.CheckFailure):

    def __init__(self, text: str):
        self.text = text


class MissingDatabase(commands.CheckFailure):
    pass


class MissingSpotifyClient(commands.CheckFailure):
    pass


class NoPlayer(commands.CheckFailure):
    pass


class NoVoice(commands.CheckFailure):
    pass


class DiffVoiceChannel(commands.CheckFailure):
    pass


class NoSource(commands.CheckFailure):
    pass


class NotDJorStaff(commands.CheckFailure):
    pass


class NotRequester(commands.CheckFailure):
    pass


class MissingSpotifyClient(commands.CheckFailure):
    pass
