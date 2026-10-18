class MajoorError(Exception):
    """Base class for every error raised by Majoor VideoTools."""


class ManifestError(MajoorError):
    """The shot collection is invalid or does not match the expected project."""


class ShotNotFoundError(MajoorError):
    pass


class MediaError(MajoorError):
    """A media file is missing, unreadable or unusable."""


class FFmpegError(MajoorError):
    pass


class AssemblyError(MajoorError):
    pass


class PathError(MajoorError):
    """A path escapes the project directory."""
