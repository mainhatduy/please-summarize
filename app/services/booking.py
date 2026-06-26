"""
Booking Service - Len lich su kien va nhac truoc gio hen.
==========================================================
Luu lich hen vao JSON, theo doi nguoi approve/reject bang reaction va
tra ve cac booking can nhac truoc 1 tieng.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shlex
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any

log = logging.getLogger("bot.booking")


BOOKINGS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "database",
    "bookings.json",
)

APPROVE_EMOJI = "✅"
REJECT_EMOJI = "❌"

_CLOCK_PATTERN = r"(?:[01]?\d|2[0-3])(?::[0-5]\d|h(?:[0-5]\d)?)"
_DATE_PATTERN = r"(?:\d{4}[/-]\d{1,2}[/-]\d{1,2}|\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)"
_RELATIVE_DAY_PATTERN = r"(?:hom nay|hôm nay|ngay mai|ngày mai|mai)"
_TIME_SEARCH_PATTERNS = [
    re.compile(rf"\b{_DATE_PATTERN}\s+{_CLOCK_PATTERN}\b", re.IGNORECASE),
    re.compile(rf"\b{_CLOCK_PATTERN}\s+{_DATE_PATTERN}\b", re.IGNORECASE),
    re.compile(rf"\b{_RELATIVE_DAY_PATTERN}\s+{_CLOCK_PATTERN}\b", re.IGNORECASE),
    re.compile(rf"\b{_CLOCK_PATTERN}\s+{_RELATIVE_DAY_PATTERN}\b", re.IGNORECASE),
    re.compile(rf"\b{_CLOCK_PATTERN}\b", re.IGNORECASE),
]


@dataclass
class BookingDraft:
    event_name: str
    event_time: datetime
    location: str


class BookingService:
    """Quan ly lich hen va persistence bang JSON."""

    def __init__(self, file_path: str = BOOKINGS_FILE):
        self.file_path = file_path
        self._lock = threading.RLock()

    def parse_booking_text(self, raw: str) -> BookingDraft:
        """Parse `.book <ten su kien> | <thoi gian> | <dia diem>`.

        Cung ho tro dang co dau nhay:
            .book "Ten su kien" "2026-06-28 20:00" "Dia diem"

        Neu khong co dau phan cach, service se tim cum thoi gian dau tien va
        xem phan truoc la ten su kien, phan sau la dia diem.
        """
        if not raw or not raw.strip():
            raise ValueError(self.usage_message())

        event_name, time_text, location = self._split_booking_text(raw.strip())
        if not event_name or not time_text or not location:
            raise ValueError(self.usage_message())

        event_time = self._parse_datetime(time_text)
        if event_time <= self._now():
            raise ValueError("Thời gian sự kiện phải nằm trong tương lai.")

        return BookingDraft(
            event_name=event_name,
            event_time=event_time,
            location=location,
        )

    def usage_message(self) -> str:
        return (
            "Cú pháp: `.book <tên sự kiện> | <thời gian> | <địa điểm>`\n"
            "Ví dụ: `.book Sinh nhật team | 2026-06-28 20:00 | Quán ABC, Q1`\n"
            "Có thể dùng: `20:00`, `20h30`, `hôm nay 20h`, `mai 20:00`, "
            "`28/06 20:00`, `2026-06-28 20:00`."
        )

    def build_booking(
        self,
        draft: BookingDraft,
        *,
        channel_id: int,
        created_by_id: int,
        created_by_name: str,
    ) -> dict[str, Any]:
        now = self._now()
        return {
            "id": self._new_booking_id(),
            "event_name": draft.event_name,
            "event_time": draft.event_time.isoformat(),
            "location": draft.location,
            "channel_id": int(channel_id),
            "message_id": None,
            "created_by_id": str(created_by_id),
            "created_by_name": created_by_name,
            "approved_users": {},
            "rejected_users": {},
            "notified_one_hour": False,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

    def add_booking(self, booking: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            data = self._load_data()
            data["bookings"].append(booking)
            self._save_data(data)
        return booking

    def attach_message(self, booking_id: str, message_id: int) -> dict[str, Any] | None:
        with self._lock:
            data = self._load_data()
            booking = self._find_by_id(data["bookings"], booking_id)
            if booking is None:
                return None
            booking["message_id"] = int(message_id)
            booking["updated_at"] = self._now().isoformat()
            self._save_data(data)
            return booking

    def get_by_message_id(self, message_id: int) -> dict[str, Any] | None:
        with self._lock:
            data = self._load_data()
            for booking in data["bookings"]:
                if booking.get("message_id") == int(message_id):
                    return booking
        return None

    def list_bookings(self, channel_id: int | None = None, include_past: bool = False) -> list[dict[str, Any]]:
        now = self._now()
        with self._lock:
            data = self._load_data()
            bookings = list(data["bookings"])

        if channel_id is not None:
            bookings = [
                booking
                for booking in bookings
                if booking.get("channel_id") == int(channel_id)
            ]

        if not include_past:
            bookings = [
                booking
                for booking in bookings
                if self.parse_event_time(booking) > now
            ]

        return sorted(bookings, key=self.parse_event_time)

    def approve(self, message_id: int, user_id: int, user_name: str) -> dict[str, Any] | None:
        return self._set_reaction_status(message_id, user_id, user_name, approved=True)

    def reject(self, message_id: int, user_id: int, user_name: str) -> dict[str, Any] | None:
        return self._set_reaction_status(message_id, user_id, user_name, approved=False)

    def get_due_one_hour_reminders(self) -> list[dict[str, Any]]:
        now = self._now()
        due: list[dict[str, Any]] = []
        with self._lock:
            data = self._load_data()
            for booking in data["bookings"]:
                if booking.get("notified_one_hour"):
                    continue
                event_time = self.parse_event_time(booking)
                seconds_until_event = (event_time - now).total_seconds()
                if 0 < seconds_until_event <= 3600:
                    due.append(booking)
        return due

    def mark_one_hour_notified(self, booking_id: str) -> dict[str, Any] | None:
        with self._lock:
            data = self._load_data()
            booking = self._find_by_id(data["bookings"], booking_id)
            if booking is None:
                return None
            booking["notified_one_hour"] = True
            booking["updated_at"] = self._now().isoformat()
            self._save_data(data)
            return booking

    def parse_event_time(self, booking: dict[str, Any]) -> datetime:
        event_time = datetime.fromisoformat(booking["event_time"])
        if event_time.tzinfo is None:
            event_time = event_time.replace(tzinfo=self._now().tzinfo)
        return event_time

    def format_event_time(self, booking: dict[str, Any]) -> str:
        event_time = self.parse_event_time(booking).astimezone(self._now().tzinfo)
        return event_time.strftime("%d/%m/%Y %H:%M")

    def approved_mentions(self, booking: dict[str, Any]) -> list[str]:
        return [f"<@{user_id}>" for user_id in booking.get("approved_users", {}).keys()]

    def approved_count(self, booking: dict[str, Any]) -> int:
        return len(booking.get("approved_users", {}))

    def rejected_count(self, booking: dict[str, Any]) -> int:
        return len(booking.get("rejected_users", {}))

    def _split_booking_text(self, raw: str) -> tuple[str, str, str]:
        if "|" in raw:
            parts = [part.strip() for part in raw.split("|")]
            if len(parts) >= 3:
                return parts[0], parts[1], " | ".join(parts[2:]).strip()

        try:
            quoted_parts = shlex.split(raw)
        except ValueError:
            quoted_parts = []
        if len(quoted_parts) == 3:
            return quoted_parts[0].strip(), quoted_parts[1].strip(), quoted_parts[2].strip()

        match = self._find_time_text(raw)
        if match is None:
            raise ValueError(self.usage_message())

        event_name = raw[:match.start()].strip(" ,-|")
        time_text = match.group(0).strip()
        location = raw[match.end():].strip(" ,-|")
        return event_name, time_text, location

    def _find_time_text(self, raw: str) -> re.Match[str] | None:
        for pattern in _TIME_SEARCH_PATTERNS:
            match = pattern.search(raw)
            if match:
                return match
        return None

    def _parse_datetime(self, value: str) -> datetime:
        now = self._now()
        text = self._normalize_datetime_text(value)
        lowered = text.lower()

        relative_day = self._relative_day_offset(lowered)
        if relative_day is not None:
            clock = self._extract_clock(lowered)
            if clock is None:
                raise ValueError(f"Không đọc được giờ trong `{value}`.")
            result = datetime.combine(
                now.date() + timedelta(days=relative_day),
                clock,
                tzinfo=now.tzinfo,
            )
            return result

        parsed = self._parse_with_formats(text, now)
        if parsed is not None:
            return parsed

        clock = self._extract_clock(lowered)
        if clock is not None and re.fullmatch(_CLOCK_PATTERN, lowered, re.IGNORECASE):
            result = datetime.combine(now.date(), clock, tzinfo=now.tzinfo)
            if result <= now:
                result += timedelta(days=1)
            return result

        raise ValueError(f"Không đọc được thời gian `{value}`.")

    def _normalize_datetime_text(self, value: str) -> str:
        text = value.strip()
        text = re.sub(r"\b([01]?\d|2[0-3])h([0-5]\d)?\b", self._replace_vietnamese_clock, text, flags=re.IGNORECASE)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _replace_vietnamese_clock(self, match: re.Match[str]) -> str:
        hour = int(match.group(1))
        minute = int(match.group(2) or "0")
        return f"{hour:02d}:{minute:02d}"

    def _relative_day_offset(self, lowered: str) -> int | None:
        if re.search(r"\b(hom nay|hôm nay)\b", lowered):
            return 0
        if re.search(r"\b(ngay mai|ngày mai|mai)\b", lowered):
            return 1
        return None

    def _extract_clock(self, lowered: str) -> time | None:
        match = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", lowered)
        if not match:
            return None
        return time(hour=int(match.group(1)), minute=int(match.group(2)))

    def _parse_with_formats(self, text: str, now: datetime) -> datetime | None:
        full_year_formats = [
            "%Y-%m-%d %H:%M",
            "%Y/%m/%d %H:%M",
            "%d/%m/%Y %H:%M",
            "%d-%m-%Y %H:%M",
            "%d/%m/%y %H:%M",
            "%d-%m-%y %H:%M",
            "%H:%M %Y-%m-%d",
            "%H:%M %Y/%m/%d",
            "%H:%M %d/%m/%Y",
            "%H:%M %d-%m-%Y",
            "%H:%M %d/%m/%y",
            "%H:%M %d-%m-%y",
        ]
        for fmt in full_year_formats:
            parsed = self._try_strptime(text, fmt)
            if parsed is not None:
                return parsed.replace(tzinfo=now.tzinfo)

        yearless_formats = [
            "%d/%m %H:%M",
            "%d-%m %H:%M",
            "%H:%M %d/%m",
            "%H:%M %d-%m",
        ]
        for fmt in yearless_formats:
            parsed = self._try_strptime(text, fmt)
            if parsed is None:
                continue
            result = parsed.replace(year=now.year, tzinfo=now.tzinfo)
            if result <= now:
                result = result.replace(year=now.year + 1)
            return result
        return None

    def _try_strptime(self, text: str, fmt: str) -> datetime | None:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            return None

    def _set_reaction_status(
        self,
        message_id: int,
        user_id: int,
        user_name: str,
        *,
        approved: bool,
    ) -> dict[str, Any] | None:
        with self._lock:
            data = self._load_data()
            booking = self._find_by_message_id(data["bookings"], message_id)
            if booking is None:
                return None

            approved_users = booking.setdefault("approved_users", {})
            rejected_users = booking.setdefault("rejected_users", {})
            user_key = str(user_id)
            user_payload = {
                "name": user_name,
                "updated_at": self._now().isoformat(),
            }

            if approved:
                approved_users[user_key] = user_payload
                rejected_users.pop(user_key, None)
            else:
                rejected_users[user_key] = user_payload
                approved_users.pop(user_key, None)

            booking["updated_at"] = self._now().isoformat()
            self._save_data(data)
            return booking

    def _load_data(self) -> dict[str, Any]:
        if not os.path.exists(self.file_path):
            return {"bookings": []}

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            log.error(f"[booking] Loi khi load file booking: {e}", exc_info=True)
            return {"bookings": []}

        if not isinstance(data, dict):
            return {"bookings": []}
        bookings = data.get("bookings")
        if not isinstance(bookings, list):
            data["bookings"] = []
        return data

    def _save_data(self, data: dict[str, Any]):
        try:
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            log.error(f"[booking] Loi khi save file booking: {e}", exc_info=True)

    def _find_by_id(self, bookings: list[dict[str, Any]], booking_id: str) -> dict[str, Any] | None:
        for booking in bookings:
            if booking.get("id") == booking_id:
                return booking
        return None

    def _find_by_message_id(self, bookings: list[dict[str, Any]], message_id: int) -> dict[str, Any] | None:
        for booking in bookings:
            if booking.get("message_id") == int(message_id):
                return booking
        return None

    def _new_booking_id(self) -> str:
        return f"book_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"

    def _now(self) -> datetime:
        return datetime.now().astimezone()
