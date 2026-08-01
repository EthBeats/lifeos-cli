"""Canvas LMS integration via iCal (.ics) feed parsing."""

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import httpx
from ics import Calendar


@dataclass
class CanvasItem:
    """Standardized representation of a Canvas assignment or academic event."""

    id: str
    title: str
    course_name: str
    due_date: datetime
    description: Optional[str]
    url: Optional[str]


class CanvasICalParser:
    """Parser for Canvas LMS iCal subscription feeds."""

    def __init__(self, ical_url: Optional[str] = None):
        self.ical_url = ical_url

    def fetch_feed(self, url: Optional[str] = None) -> str:
        """Download raw .ics text content from Canvas feed URL."""
        target_url = url or self.ical_url
        if not target_url:
            raise ValueError(
                "Canvas iCal URL is not provided. " \
                "Set CANVAS_ICAL_URL in your .env file."
            )

        # Convert webcal:// scheme to https:// if present
        if target_url.startswith("webcal://"):
            target_url = "https://" + target_url[9:]

        response = httpx.get(target_url, follow_redirects=True, timeout=10.0)
        response.raise_for_status()
        return response.text

    def parse_assignments(self, ics_content: str) -> list[CanvasItem]:
        """Parse raw iCal string into standard CanvasItem objects."""
        calendar = Calendar(ics_content)
        items = []

        for event in calendar.events:
            summary = event.name or "Untitled Assignment"
            course_name, title = self._extract_course_and_title(summary)

            # Event begin/end time parsed to Python timezone-aware datetime
            due_dt = event.begin.datetime if event.begin else None
            if not due_dt:
                continue

            description = event.description or ""
            url = self._extract_url(description)

            items.append(
                CanvasItem(
                    id=str(event.uid),
                    title=title,
                    course_name=course_name,
                    due_date=due_dt,
                    description=description.strip() if description else None,
                    url=url,
                )
            )

        return items

    def get_upcoming_assignments(
        self, days_ahead: int = 14, url: Optional[str] = None
    ) -> list[CanvasItem]:
        """
        Fetch and return assignments due within the specified window 
        (default 14 days).
        """
        raw_feed = self.fetch_feed(url=url)
        all_items = self.parse_assignments(raw_feed)

        now = datetime.now(timezone.utc)
        results = []

        for item in all_items:
            # Ensure due_date is timezone aware for comparison
            item_dt = item.due_date
            if item_dt.tzinfo is None:
                item_dt = item_dt.replace(tzinfo=timezone.utc)

            delta = (item_dt - now).days
            if -1 <= delta <= days_ahead:
                results.append(item)

        return sorted(results, key=lambda x: x.due_date)

    @staticmethod
    def _extract_course_and_title(summary: str) -> tuple[str, str]:
        """
        Extract course code and assignment title from Canvas summaries.
        Handles patterns like:
        - "Assignment 1 [CS 101]"
        - "[CS 101] Assignment 1"
        - "CS 101: Assignment 1"
        """
        # Match pattern with brackets: "Title [Course]" or "[Course] Title"
        bracket_match = re.search(r"\[(.*?)\]", summary)
        if bracket_match:
            course_name = bracket_match.group(1).strip()
            title = summary.replace(bracket_match.group(0), "").strip(" :-")
            return course_name, title

        # Match pattern with colon: "Course: Title"
        if ":" in summary:
            parts = summary.split(":", 1)
            return parts[0].strip(), parts[1].strip()

        return "General", summary.strip()

    @staticmethod
    def _extract_url(description: str) -> Optional[str]:
        """Extract Canvas assignment URL from description body."""
        match = re.search(r"https?://[^\s>]+", description)
        return match.group(0) if match else None
