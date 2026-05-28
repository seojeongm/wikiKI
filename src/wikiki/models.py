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


@dataclass
class ArticleStats:
    title: str
    editor_count: int
    revert_count: int
    edit_velocity: int
    tension_score: float
    status: str
