
import streamlit as st
import streamlit.components.v1 as components
import re
import zipfile
import io
import html
import mimetypes
import base64
import pandas as pd

from pathlib import PurePosixPath
from datetime import datetime
from urllib.parse import urlparse


# =========================================================
# PAGE CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="WhatsApp Chat Viewer",
    page_icon="💬",
    layout="wide"
)

st.title("WhatsApp Chat Viewer")


# =========================================================
# SESSION STATE
# =========================================================

if "messages" not in st.session_state:
    st.session_state.messages = []

if "media_files" not in st.session_state:
    st.session_state.media_files = {}

if "contacts" not in st.session_state:
    st.session_state.contacts = {}

if "loaded_chat_name" not in st.session_state:
    st.session_state.loaded_chat_name = None

if "loaded_chat_signature" not in st.session_state:
    st.session_state.loaded_chat_signature = None


# =========================================================
# TIMESTAMP PARSING
# =========================================================

DATE_TIME = (
    r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
    r",?\s+\d{1,2}:\d{2}"
    r"(?::\d{2})?"
    r"\s*(?:AM|PM)?"
)

LONG_DATE_TIME = (
    r"\d{1,2}\s+[A-Za-z]+\s+\d{4}"
    r",?\s+\d{1,2}:\d{2}"
    r"(?::\d{2})?"
    r"\s*(?:AM|PM)?"
)

TIMESTAMP_PATTERNS = [
    re.compile(
        r"^\[(?P<date>" + DATE_TIME + r")\]"
        r"\s*(?P<body>.*)$",
        re.IGNORECASE
    ),
    re.compile(
        r"^\[(?P<date>" + LONG_DATE_TIME + r")\]"
        r"\s*(?P<body>.*)$",
        re.IGNORECASE
    ),
    re.compile(
        r"^(?P<date>" + DATE_TIME + r")"
        r"\s*[-–]\s*(?P<body>.*)$",
        re.IGNORECASE
    ),
    re.compile(
        r"^(?P<date>" + LONG_DATE_TIME + r")"
        r"\s*[-–]\s*(?P<body>.*)$",
        re.IGNORECASE
    ),
]

INVISIBLE_PREFIXES = (
    "\u200e", "\u200f", "\u202a", "\u202b",
    "\u202c", "\u2066", "\u2067", "\u2068",
    "\u2069", "\ufeff"
)


def clean_line(line):
    line = line.strip()

    while line and line[0] in INVISIBLE_PREFIXES:
        line = line[1:].lstrip()

    return line


def parse_timestamp_line(line):
    line = clean_line(line)

    for pattern in TIMESTAMP_PATTERNS:
        match = pattern.match(line)

        if match:
            return (
                match.group("date").strip(),
                match.group("body")
            )

    return None, None


def parse_datetime(date_text):
    date_text = (
        date_text
        .replace("\u202f", " ")
        .replace("\u00a0", " ")
        .strip()
    )

    formats = [
        "%d/%m/%y, %H:%M:%S",
        "%d/%m/%Y, %H:%M:%S",
        "%m/%d/%y, %H:%M:%S",
        "%m/%d/%Y, %H:%M:%S",
        "%d/%m/%y, %I:%M:%S %p",
        "%d/%m/%Y, %I:%M:%S %p",
        "%m/%d/%y, %I:%M:%S %p",
        "%m/%d/%Y, %I:%M:%S %p",
        "%d/%m/%y, %H:%M",
        "%d/%m/%Y, %H:%M",
        "%m/%d/%y, %H:%M",
        "%m/%d/%Y, %H:%M",
        "%d/%m/%y, %I:%M %p",
        "%d/%m/%Y, %I:%M %p",
        "%m/%d/%y, %I:%M %p",
        "%m/%d/%Y, %I:%M %p",
        "%d %B %Y, %H:%M:%S",
        "%d %b %Y, %H:%M:%S",
        "%d %B %Y, %I:%M:%S %p",
        "%d %b %Y, %I:%M:%S %p",
        "%d %B %Y, %H:%M",
        "%d %b %Y, %H:%M",
        "%d %B %Y, %I:%M %p",
        "%d %b %Y, %I:%M %p",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_text, fmt)
        except ValueError:
            continue

    return None


# =========================================================
# CHAT PARSER
# =========================================================

def parse_whatsapp_chat(text):
    messages = []
    current = None

    def save_current():
        nonlocal current

        if current is not None:
            current["message"] = "\n".join(
                current.pop("message_lines", [])
            ).strip()

            messages.append(current)
            current = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip("\r\n")

        date_text, body = parse_timestamp_line(line)

        if date_text is not None:
            save_current()

            parsed_dt = parse_datetime(date_text)

            sender = ""
            message_text = body

            # Split only on the first sender separator.
            if ": " in body:
                possible_sender, possible_message = body.split(
                    ": ", 1
                )

                if possible_sender.strip():
                    sender = possible_sender.strip()
                    message_text = possible_message

            current = {
                "date_text": date_text,
                "datetime": parsed_dt,
                "sender": sender,
                "message_lines": [message_text],
            }

        elif current is not None:
            # Preserve message continuation lines.
            current["message_lines"].append(line)

    save_current()

    for message in messages:
        dt = message["datetime"]

        if dt:
            message["date_display"] = dt.strftime("%d %B %Y")
            message["time_display"] = dt.strftime("%H:%M")
        else:
            message["date_display"] = message["date_text"]
            message["time_display"] = ""

    return messages


# =========================================================
# MEDIA HELPERS
# =========================================================

def normalize_filename(filename):
    return PurePosixPath(
        filename.replace("\\", "/")
    ).name


def get_media_category(filename):
    ext = PurePosixPath(filename).suffix.lower()

    if ext in {
        ".jpg", ".jpeg", ".png", ".gif", ".webp",
        ".bmp", ".tif", ".tiff", ".heic", ".heif"
    }:
        return "Images"

    if ext in {
        ".mp4", ".mov", ".avi", ".mkv", ".3gp",
        ".webm", ".m4v"
    }:
        return "Videos"

    if ext in {
        ".opus", ".mp3", ".m4a", ".aac", ".wav",
        ".ogg", ".amr", ".flac"
    }:
        return "Audio"

    if ext in {
        ".pdf", ".doc", ".docx", ".xls", ".xlsx",
        ".ppt", ".pptx", ".txt", ".csv", ".rtf",
        ".zip", ".7z"
    }:
        return "Documents"

    return "Other Files"


def find_media(filename):
    files = st.session_state.media_files

    if filename in files:
        return files[filename]

    target = normalize_filename(filename).casefold()

    for stored_name, content in files.items():
        if normalize_filename(stored_name).casefold() == target:
            return content

    return None


def extract_attachment_names(message_text):
    pattern = re.compile(
        r"<attached:\s*(.*?)\s*>",
        re.IGNORECASE
    )

    return [
        match.group(1).strip()
        for match in pattern.finditer(message_text)
        if match.group(1).strip()
    ]


def remove_attachment_placeholders(message_text):
    return re.sub(
        r"<attached:\s*.*?\s*>",
        "",
        message_text,
        flags=re.IGNORECASE
    ).strip()


def escape_html(value):
    return html.escape(str(value), quote=True)


def get_chat_links(messages):
    links = []
    seen = set()

    url_pattern = re.compile(r'https?://[^\s<>"]+', re.IGNORECASE)

    for message in messages:
        for url in url_pattern.findall(message.get("message", "")):
            url = url.rstrip(".,;:!?)\u005d")

            if url not in seen:
                seen.add(url)
                links.append({
                    "url": url,
                    "sender": message.get("sender", ""),
                    "date": message.get("date_display", ""),
                    "time": message.get("time_display", ""),
                })

    return links


# =========================================================
# INLINE MEDIA RENDERER
# =========================================================

def render_media(filename, content):
    category = get_media_category(filename)

    mime_type = (
        mimetypes.guess_type(filename)[0]
        or "application/octet-stream"
    )

    safe_name = escape_html(normalize_filename(filename))
    encoded = base64.b64encode(content).decode("ascii")
    data_uri = f"data:{mime_type};base64,{encoded}"

    if category == "Images":
        if mime_type in {"image/heic", "image/heif"}:
            return (
                '<div class="media-card">'
                f'<div class="media-name">🖼️ {safe_name}</div>'
                '<div>Preview is not supported by every browser.</div>'
                f'<a href="{data_uri}" download="{safe_name}">'
                'Download image</a>'
                '</div>'
            )

        return (
            '<div class="media-card">'
            f'<img class="chat-image" src="{data_uri}" '
            f'alt="{safe_name}">'
            f'<a href="{data_uri}" download="{safe_name}">'
            'Download image</a>'
            '</div>'
        )

    if category == "Videos":
        return (
            '<div class="media-card">'
            '<div class="media-name">🎬 Video</div>'
            '<video class="chat-video" controls preload="metadata">'
            f'<source src="{data_uri}" type="{escape_html(mime_type)}">'
            '</video>'
            f'<a href="{data_uri}" download="{safe_name}">'
            'Download video</a>'
            '</div>'
        )

    if category == "Audio":
        return (
            '<div class="media-card audio-card">'
            '<div class="media-name">🎵 Voice message</div>'
            '<audio class="chat-audio" controls preload="metadata">'
            f'<source src="{data_uri}" type="{escape_html(mime_type)}">'
            '</audio>'
            f'<a href="{data_uri}" download="{safe_name}">'
            'Download audio</a>'
            '</div>'
        )

    return (
        '<div class="media-card document-card">'
        '<div class="document-icon">📎</div>'
        '<div class="document-details">'
        f'<div class="media-name">{safe_name}</div>'
        f'<div>{escape_html(category)}</div>'
        f'<a href="{data_uri}" download="{safe_name}">'
        'Download file</a>'
        '</div></div>'
    )


# =========================================================
# UPLOADS
# =========================================================

uploaded_chat = st.file_uploader(
    "Open WhatsApp TXT or ZIP export",
    type=["txt", "zip"],
    key="chat_upload"
)

uploaded_media = st.file_uploader(
    "Additional media files (optional)",
    accept_multiple_files=True,
    key="media_upload"
)

uploaded_contacts = st.file_uploader(
    "Contacts VCF or CSV (optional)",
    type=["vcf", "csv"],
    key="contacts_upload"
)


# =========================================================
# LOAD ADDITIONAL MEDIA
# =========================================================

if uploaded_media:
    for file in uploaded_media:
        st.session_state.media_files[file.name] = file.getvalue()


# =========================================================
# READ CHAT TXT OR ZIP
# =========================================================

chat_text = None

if uploaded_chat is not None:
    upload_bytes = uploaded_chat.getvalue()
    signature = (
        uploaded_chat.name,
        len(upload_bytes),
        hash(upload_bytes)
    )

    if signature != st.session_state.loaded_chat_signature:
        # Avoid retaining files from a previous ZIP export.
        st.session_state.media_files = {}

        for file in uploaded_media or []:
            st.session_state.media_files[file.name] = file.getvalue()

        if uploaded_chat.name.lower().endswith(".txt"):
            for encoding in [
                "utf-8-sig", "utf-8", "utf-16",
                "cp1252", "latin-1"
            ]:
                try:
                    chat_text = upload_bytes.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue

        elif uploaded_chat.name.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(upload_bytes)) as archive:
                    txt_files = [
                        name for name in archive.namelist()
                        if name.lower().endswith(".txt")
                        and not name.endswith("/")
                    ]

                    if txt_files:
                        preferred = [
                            name for name in txt_files
                            if "chat" in PurePosixPath(name).name.lower()
                        ]

                        selected_txt = (
                            preferred[0] if preferred else txt_files[0]
                        )

                        raw_txt = archive.read(selected_txt)

                        for encoding in [
                            "utf-8-sig", "utf-8", "utf-16",
                            "cp1252", "latin-1"
                        ]:
                            try:
                                chat_text = raw_txt.decode(encoding)
                                break
                            except UnicodeDecodeError:
                                continue

                    for name in archive.namelist():
                        if name.endswith("/") or name.lower().endswith(".txt"):
                            continue

                        basename = normalize_filename(name)

                        if basename:
                            st.session_state.media_files.setdefault(
                                basename,
                                archive.read(name)
                            )

            except zipfile.BadZipFile:
                st.error("The uploaded ZIP file is invalid.")

            except Exception as exc:
                st.error(f"Unable to read ZIP file: {exc}")

        if chat_text is not None:
            st.session_state.messages = parse_whatsapp_chat(chat_text)
            st.session_state.loaded_chat_name = uploaded_chat.name
            st.session_state.loaded_chat_signature = signature

            if not st.session_state.messages:
                st.warning(
                    "No messages detected. The timestamp format "
                    "may need adjustment."
                )
    else:
        # Reuse the already parsed chat on Streamlit reruns.
        chat_text = None


# =========================================================
# LOAD CONTACTS
# =========================================================

if uploaded_contacts is not None:
    contacts = {}

    if uploaded_contacts.name.lower().endswith(".csv"):
        try:
            contacts_df = pd.read_csv(
                uploaded_contacts,
                dtype=str
            ).fillna("")

            for _, row in contacts_df.iterrows():
                values = list(row.values)

                if len(values) >= 2:
                    name = str(values[0]).strip()
                    number = str(values[1]).strip()

                    if name and number:
                        contacts[number] = name

        except Exception as exc:
            st.error(f"Could not read contacts CSV: {exc}")

    elif uploaded_contacts.name.lower().endswith(".vcf"):
        try:
            vcf_text = uploaded_contacts.getvalue().decode(
                "utf-8",
                errors="replace"
            )

            current_name = ""
            current_numbers = []

            for line in vcf_text.splitlines():
                line = line.strip()

                if line.upper().startswith("BEGIN:VCARD"):
                    current_name = ""
                    current_numbers = []

                elif line.upper().startswith("FN:"):
                    current_name = line.split(":", 1)[1].strip()

                elif line.upper().startswith("TEL") and ":" in line:
                    current_numbers.append(
                        line.split(":", 1)[1].strip()
                    )

                elif line.upper().startswith("END:VCARD"):
                    if current_name:
                        for number in current_numbers:
                            contacts[number] = current_name

        except Exception as exc:
            st.error(f"Could not read contacts VCF: {exc}")

    st.session_state.contacts.update(contacts)


# =========================================================
# SIDEBAR MEDIA EXPLORER
# =========================================================

messages = st.session_state.messages
media_files = st.session_state.media_files
chat_links = get_chat_links(messages)

with st.sidebar:
    st.title("Media Explorer")

    st.caption("Browse files from the loaded chat export.")

    categories = [
        "Images",
        "Videos",
        "Audio",
        "Documents",
        "Other Files"
    ]

    for category in categories:
        matching_files = [
            (filename, content)
            for filename, content in media_files.items()
            if get_media_category(filename) == category
        ]

        with st.expander(
            f"{category} ({len(matching_files)})",
            expanded=False
        ):
            if not matching_files:
                st.caption("No files available.")

            for index, (filename, content) in enumerate(matching_files):
                mime_type = (
                    mimetypes.guess_type(filename)[0]
                    or "application/octet-stream"
                )

                st.markdown(f"**{normalize_filename(filename)}**")

                if category == "Images":
                    if mime_type in {
                        "image/jpeg", "image/png",
                        "image/gif", "image/webp", "image/bmp"
                    }:
                        st.image(content, use_container_width=True)
                    else:
                        st.caption("Image preview unavailable.")

                elif category == "Videos":
                    if mime_type.startswith("video/"):
                        st.video(content)
                    else:
                        st.caption("Video preview unavailable.")

                elif category == "Audio":
                    st.audio(content, format=mime_type)

                st.download_button(
                    "Download file",
                    data=content,
                    file_name=normalize_filename(filename),
                    mime=mime_type,
                    key=f"sidebar_download_{category}_{index}_{filename}"
                )

    with st.expander(f"Links ({len(chat_links)})", expanded=False):
        if not chat_links:
            st.caption("No web links found in the conversation.")

        for index, link in enumerate(chat_links):
            url = link["url"]
            parsed = urlparse(url)

            st.markdown(
                f"[{escape_html(parsed.netloc or url)}]({url})"
            )

            st.caption(
                f'{link["date"]} {link["time"]} · '
                f'{link["sender"]}'
            )


# =========================================================
# CHAT VIEWER
# =========================================================

if messages:
    st.subheader("Conversation")

    senders = sorted({
        message["sender"]
        for message in messages
        if message["sender"]
    })

    if senders:
        selected_sender = st.selectbox(
            "Select sender",
            options=senders,
            key="selected_sender"
        )
    else:
        selected_sender = None

    all_dates = list(dict.fromkeys(
        message["date_display"]
        for message in messages
    ))

    selected_dates = st.multiselect(
        "Filter by date",
        options=all_dates,
        key="selected_dates"
    )

    search_text = st.text_input(
        "Search message text",
        placeholder="Enter a word, phrase, or reference number",
        key="search_messages"
    )

    filtered_messages = []

    for message in messages:
        if (
            selected_dates
            and message["date_display"] not in selected_dates
        ):
            continue

        if (
            search_text
            and search_text.casefold()
            not in message["message"].casefold()
        ):
            continue

        filtered_messages.append(message)


    # =====================================================
    # CHAT CSS
    # =====================================================

    chat_css = """
    <style>
    * { box-sizing: border-box; }

    html, body {
        margin: 0;
        padding: 0;
        font-family: Arial, Helvetica, sans-serif;
        background: #efeae2;
    }

    .chat-container {
        width: 100%;
        padding: 12px;
        background: #efeae2;
        min-height: 100%;
    }

    .date-separator {
        text-align: center;
        margin: 16px 0;
    }

    .date-separator span {
        display: inline-block;
        background: #ffffff;
        color: #54656f;
        border-radius: 8px;
        padding: 6px 12px;
        font-size: 12px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.08);
    }

    .message-row {
        display: flex;
        width: 100%;
        margin: 5px 0;
    }

    .message-row.sender { justify-content: flex-end; }
    .message-row.receiver { justify-content: flex-start; }

    .message-bubble {
        max-width: 78%;
        min-width: 90px;
        padding: 7px 9px 5px;
        border-radius: 8px;
        color: #111b21;
        font-size: 14px;
        overflow-wrap: anywhere;
        box-shadow: 0 1px 1px rgba(0,0,0,0.08);
    }

    .sender .message-bubble {
        background: #d9fdd3;
        border-top-right-radius: 2px;
    }

    .receiver .message-bubble {
        background: #ffffff;
        border-top-left-radius: 2px;
    }

    .sender-name {
        color: #128c7e;
        font-size: 12px;
        font-weight: 600;
        margin-bottom: 4px;
    }

    .message-text {
        font-size: 14px;
        line-height: 1.4;
        white-space: pre-wrap;
        overflow-wrap: anywhere;
    }

    .message-time {
        color: #667781;
        font-size: 10px;
        text-align: right;
        margin-top: 4px;
    }

    .media-card {
        margin-top: 5px;
        padding: 4px;
        max-width: 100%;
        border-radius: 7px;
        background: rgba(255,255,255,0.45);
        overflow-wrap: anywhere;
    }

    .media-name {
        font-size: 12px;
        font-weight: 600;
        margin-bottom: 5px;
    }

    .chat-image {
        display: block;
        max-width: 100%;
        max-height: 400px;
        width: auto;
        height: auto;
        object-fit: contain;
        border-radius: 5px;
        margin: 3px 0;
    }

    .chat-video {
        display: block;
        width: 320px;
        max-width: 100%;
        border-radius: 6px;
        margin: 4px 0;
    }

    .chat-audio {
        display: block;
        width: 280px;
        max-width: 100%;
        margin: 4px 0;
    }

    .media-card a {
        display: inline-block;
        color: #075e54;
        font-size: 12px;
        margin-top: 4px;
    }

    .document-card {
        display: flex;
        gap: 10px;
        align-items: center;
        padding: 10px;
        background: rgba(255,255,255,0.7);
    }

    .document-icon { font-size: 28px; }

    .document-details {
        min-width: 0;
        overflow-wrap: anywhere;
    }

    .system-message {
        width: fit-content;
        max-width: 85%;
        margin: 10px auto;
        padding: 6px 10px;
        border-radius: 7px;
        background: #ffffff;
        color: #54656f;
        font-size: 12px;
        text-align: center;
        white-space: pre-wrap;
        overflow-wrap: anywhere;
    }

    @media (max-width: 600px) {
        .message-bubble { max-width: 92%; }

        .chat-video, .chat-audio {
            width: 100%;
        }
    }
    </style>
    """


    # =====================================================
    # BUILD CHAT MESSAGES
    # =====================================================

    chat_parts = ['<div class="chat-container">']
    previous_date = None

    for message in filtered_messages:
        date_display = message["date_display"]

        if date_display != previous_date:
            chat_parts.append(
                '<div class="date-separator">'
                f'<span>{escape_html(date_display)}</span>'
                '</div>'
            )
            previous_date = date_display

        sender = message["sender"]
        message_text = message["message"]
        time_display = message["time_display"]

        # System messages are shown separately.
        if not sender:
            chat_parts.append(
                '<div class="system-message">'
                f'{escape_html(message_text)}'
                '</div>'
            )
            continue

        bubble_class = (
            "sender"
            if sender == selected_sender
            else "receiver"
        )

        display_name = st.session_state.contacts.get(sender, sender)

        attachment_names = extract_attachment_names(message_text)
        visible_text = remove_attachment_placeholders(message_text)

        chat_parts.append(
            f'<div class="message-row {bubble_class}">'
            '<div class="message-bubble">'
        )

        # Show the sender name in BOTH green and white bubbles.
        chat_parts.append(
            '<div class="sender-name">'
            f'{escape_html(display_name)}'
            '</div>'
        )

        if visible_text:
            chat_parts.append(
                '<div class="message-text">'
                f'{escape_html(visible_text)}'
                '</div>'
            )

        for attachment_name in attachment_names:
            media_bytes = find_media(attachment_name)

            if media_bytes is not None:
                chat_parts.append(
                    render_media(attachment_name, media_bytes)
                )
            else:
                chat_parts.append(
                    '<div class="media-card">'
                    '<div class="media-name">📎 '
                    f'{escape_html(attachment_name)}'
                    '</div>'
                    '<div>Media file not included in the uploaded files.</div>'
                    '</div>'
                )

        if time_display:
            chat_parts.append(
                '<div class="message-time">'
                f'{escape_html(time_display)}'
                '</div>'
            )

        chat_parts.append('</div></div>')

    chat_parts.append('</div>')

    complete_html = (
        "<!DOCTYPE html>"
        "<html><head><meta charset='utf-8'>"
        + chat_css
        + "</head><body>"
        + "".join(chat_parts)
        + "</body></html>"
    )

    components.html(
        complete_html,
        height=850,
        scrolling=True
    )


    # =====================================================
    # CSV EXPORT
    # =====================================================

    with st.expander("Export chat messages"):
        export_df = pd.DataFrame([
            {
                "Date": message["date_display"],
                "Time": message["time_display"],
                "Sender": message["sender"],
                "Message": message["message"],
            }
            for message in filtered_messages
        ])

        st.download_button(
            "Download messages as CSV",
            data=export_df.to_csv(
                index=False
            ).encode("utf-8-sig"),
            file_name="whatsapp_chat_export.csv",
            mime="text/csv"
        )

else:
    st.info("Upload a WhatsApp TXT or ZIP export to open the conversation.")
