from dataclasses import dataclass, field


@dataclass
class ArticleStats:
    title: str
    editor_count: int
    revert_count: int
    edit_velocity: float
    tension_score: float
    status: str
    flags: list[str] = field(default_factory=list)
    last_edit_min: int = 0


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
