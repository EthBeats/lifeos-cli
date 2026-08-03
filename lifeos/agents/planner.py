"""Weekly Planning Agent for multi-day academic strategy and calendar allocation."""

import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

from lifeos.agents.client import OllamaClient
from lifeos.config import settings


class WeeklyPlannerAgent:
    """Agent responsible for multi-day planning, subtask generation, and weekly Obsidian logs."""

    def __init__(self):
        self.ollama = OllamaClient()

    def gather_weekly_context(self, days_ahead: int = 14) -> dict:
        """Gather extended calendar, reminder, and Canvas context for the upcoming window."""
        now = datetime.now()
        start_of_today = datetime(now.year, now.month, now.day, 0, 0, 0)
        end_date = start_of_today + timedelta(days=days_ahead)

        context = {
            "planning_date": now.strftime("%A, %B %d, %Y"),
            "window_days": days_ahead,
            "canvas_assignments": [],
            "calendar_events": [],
            "current_reminders": [],
        }

        # 1. Canvas Deliverables (Next N days)
        if settings.canvas_ical_url:
            try:
                from lifeos.integrations.canvas import CanvasICalParser

                parser = CanvasICalParser(ical_url=settings.canvas_ical_url)
                assignments = parser.get_upcoming_assignments(days_ahead=days_ahead)
                context["canvas_assignments"] = [
                    {
                        "course": a.course_name,
                        "title": a.title,
                        "due_date": a.due_date.strftime("%Y-%m-%d %H:%M (%A)"),
                    }
                    for a in assignments
                ]
            except Exception as e:
                context["canvas_error"] = str(e)

        # 2. Apple Calendar & Reminders
        if sys.platform == "darwin":
            try:
                from lifeos.integrations.apple_eventkit import EventKitBridge

                bridge = EventKitBridge()

                if bridge.request_permissions(entity_type="event"):
                    events = bridge.fetch_events(start_of_today, end_date)
                    context["calendar_events"] = [
                        {
                            "title": e.title,
                            "start": e.start_date.strftime("%Y-%m-%d %H:%M"),
                            "end": e.end_date.strftime("%Y-%m-%d %H:%M"),
                        }
                        for e in events
                    ]

                if bridge.request_permissions(entity_type="reminder"):
                    reminders = bridge.fetch_reminders()
                    context["current_reminders"] = [
                        {
                            "title": r.title,
                            "list": r.calendar_name,
                            "due": (
                                r.due_date.strftime("%Y-%m-%d")
                                if r.due_date
                                else "No date"
                            ),
                        }
                        for r in reminders
                    ]
            except Exception as e:
                context["eventkit_error"] = str(e)

        return context

    def generate_weekly_plan_stream(
        self, days_ahead: int = 7, context: Optional[dict] = None
    ):
        """Stream the weekly strategic plan tokens from Ollama."""
        if not self.ollama.is_available():
            raise RuntimeError(
                f"Ollama server is not responding at {self.ollama.base_url}."
            )

        data = context or self.gather_weekly_context(days_ahead=days_ahead)

        system_prompt = (
            "You are LifeOS Strategic Planner, an AI assistant built for high-performance "
            "academic and personal workflow planning.\n\n"
            "Your task is to analyze the user's workload for the next 7 to 14 days and design a "
            "master Weekly Execution Plan. Decide when the user should go to sleep and wake up "
            "(make sure it is the same time each day) based on their calendar\n\n"
            "Structure your output using clear Markdown:\n"
            "- # 📊 Weekly Executive Overview (High-level workload summary and major deadlines)\n"
            "- ## 🚨 High-Risk Bottlenecks & Critical Deadlines (Identify heavy conflict days)\n"
            "- ## 🧩 Sub-task & Milestone Breakdown (Break complex assignments into 2-3 step prepare tasks)\n"
            "- ## 🗓️ Day-by-Day Focus Allocation (Suggested focus areas Monday through Sunday)\n"
            "- ## 💡 Proactive Planning Recommendations\n"
        )

        user_prompt = f"Here is the system context for the upcoming planning window:\n\n{data}"

        return self.ollama.generate_chat_stream(
            system_prompt=system_prompt, user_prompt=user_prompt
        )
