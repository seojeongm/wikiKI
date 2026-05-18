from .models import EditEvent


def is_enwiki_edit(event: dict) -> bool:
    """Return True only for English Wikipedia edit events."""
    return event.get("wiki") == "enwiki" and event.get("type") == "edit"


def parse_edit_event(event: dict) -> EditEvent:
    """Extract required fields from a recentchange event dict."""
    return EditEvent(
        title=event["title"],
        user=event["user"],
        bot=event["bot"],
        timestamp=event["timestamp"],
        comment=event.get("comment", ""),
        length_old=event["length"]["old"],
        length_new=event["length"]["new"],
        revision_old=event["revision"]["old"],
        revision_new=event["revision"]["new"],
    )
