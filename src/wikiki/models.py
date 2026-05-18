from dataclasses import dataclass


@dataclass
class EditEvent:
    title: str
    user: str
    bot: bool
    timestamp: int
    comment: str
    length_old: int
    length_new: int
    revision_old: int
    revision_new: int
