
import re
from dataclasses import dataclass
from typing import List, Optional


INVISIBLE_CHARS = {
    "\u200e", "\u200f",
    "\u202a", "\u202b", "\u202c", "\u202d", "\u202e",
    "\u2066", "\u2067", "\u2068", "\u2069",
    "\ufeff",
}


def clean_text(value: str) -> str:
    """Remove invisible direction marks without changing visible text."""
    return "".join(ch for ch in value if ch not in INVISIBLE_CHARS)


@dataclass
class ChatMessage:
    date: str
    sender: str
    message: str
    is_system: bool = False
    attachment_name: Optional[str] = None


BRACKETED_PATTERN = re.compile(
    r"^\[(?P<date>[^\]]+)\]\s*(?P<content>.*)$"
)

DASH_PATTERN = re.compile(
    r"^(?P<date>\d{1,2}/\d{1,2}/\d{2,4},\s*"
    r"\d{1,2}:\d{2}(?::\d{2})?\s*[APap][Mm])"
    r"\s*-\s*(?P<content>.*)$"
)

SENDER_PATTERN = re.compile(
    r"^(?P<sender>[^:]+):\s*(?P<message>.*)$"
)

ATTACHMENT_PATTERN = re.compile(
    r"<\s*attached:\s*(.+?)\s*>",
    flags=re.IGNORECASE,
)


def parse_line(line: str):
    """Recognize the beginning of a WhatsApp message."""
    line = clean_text(line).strip()

    match = BRACKETED_PATTERN.match(line)
    if match:
        return match.group("date").strip(), match.group("content").strip()

    match = DASH_PATTERN.match(line)
    if match:
        return match.group("date").strip(), match.group("content").strip()

    return None


def find_attachment_name(message: str) -> Optional[str]:
    """Extract the filename from an attached-file marker."""
    message = clean_text(message)
    match = ATTACHMENT_PATTERN.search(message)

    if match:
        return match.group(1).strip().strip('"')

    # Some WhatsApp exports use "filename (file attached)".
    match = re.search(
        r"([^\r\n<>]+?)\s*\(file attached\)",
        message,
        flags=re.IGNORECASE,
    )

    if match:
        return match.group(1).strip()

    return None


def make_message(date: str, content: str) -> ChatMessage:
    content = clean_text(content).strip()
    match = SENDER_PATTERN.match(content)

    if match:
        sender = clean_text(match.group("sender")).strip()
        message = clean_text(match.group("message")).strip()

        return ChatMessage(
            date=date,
            sender=sender,
            message=message,
            is_system=False,
            attachment_name=find_attachment_name(message),
        )

    # WhatsApp system notifications can have no sender.
    return ChatMessage(
        date=date,
        sender="System",
        message=content,
        is_system=True,
        attachment_name=find_attachment_name(content),
    )


def parse_chat_text(text: str) -> List[ChatMessage]:
    """
    Parse WhatsApp TXT exports using either:
      [29/01/26, 4:34:08 PM] Name: Message
      8/20/26, 9:24 AM - Name: Message

    Lines that do not begin a new timestamped message are appended
    to the preceding message.
    """
    text = clean_text(text)
    messages: List[ChatMessage] = []

    current_date = None
    current_content = []

    for line in text.splitlines():
        parsed = parse_line(line)

        if parsed:
            if current_date is not None:
                messages.append(
                    make_message(
                        current_date,
                        "\n".join(current_content),
                    )
                )

            current_date, content = parsed
            current_content = [content]

        elif current_date is not None:
            current_content.append(clean_text(line))

    if current_date is not None:
        messages.append(
            make_message(
                current_date,
                "\n".join(current_content),
            )
        )

    return messages


def parse_chat_file(file_path: str) -> List[ChatMessage]:
    """Read and parse a WhatsApp TXT export."""
    with open(
        file_path,
        "r",
        encoding="utf-8-sig",
        errors="replace",
    ) as file:
        return parse_chat_text(file.read())
