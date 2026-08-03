"""Daily Synthesizer Agent for compiling calendars, tasks, and Canvas workloads."""

import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

from lifeos.agents.client import OllamaClient
from lifeos.config import settings


class DailySynthesizerAgent:
    """Agent responsible for generating the Daily Briefing and Obsidian sync."""

    def __init__(self):
        self.ollama = OllamaClient()

    def gather_daily_context(self) -> dict:
        """Gather tasks, calendar events, and upcoming assignments."""
        context = {
            "date": datetime.now().strftime("%A, %B %d, %Y"),
            "reminders": [],
            "calendar_events": [],
            "canvas_assignments": [],
        }

        if sys.platform == "darwin":
            try:
                from lifeos.integrations.apple_eventkit import EventKitBridge

                bridge = EventKitBridge()
                if bridge.request_permissions(entity_type="reminder"):
                    reminders = bridge.fetch_reminders()
                    
                    reminder_list = []
                    for r in reminders:
                        if r.due_date:
                            if r.has_time:
                                due_fmt = r.due_date.strftime("%Y-%m-%d %H:%M")
                            else:
                                due_fmt = r.due_date.strftime("%Y-%m-%d") + " (End of Day)"
                        else:
                            due_fmt = "No due date"

                        reminder_list.append(
                            {
                                "title": r.title,
                                "list": r.calendar_name,
                                "due_date": due_fmt,
                            }
                        )
                    context["reminders"] = reminder_list

                if bridge.request_permissions(entity_type="event"):
                    now = datetime.now()
                    start_of_day = datetime(now.year, now.month, now.day, 0, 0, 0)
                    end_of_day = datetime(now.year, now.month, now.day, 23, 59, 59)
                    events = bridge.fetch_events(start_of_day, end_of_day)
                    context["calendar_events"] = [
                        {
                            "title": e.title,
                            "start": e.start_date.strftime("%H:%M"),
                            "end": e.end_date.strftime("%H:%M"),
                        }
                        for e in events
                    ]
            except Exception as e:
                context["eventkit_error"] = str(e)

        # 2. Fetch Canvas Assignments (Next 7 days)
        if settings.canvas_ical_url:
            try:
                from lifeos.integrations.canvas import CanvasICalParser

                parser = CanvasICalParser(ical_url=settings.canvas_ical_url)
                assignments = parser.get_upcoming_assignments(days_ahead=7)
                context["canvas_assignments"] = [
                    {
                        "course": a.course_name,
                        "assignment": a.title,
                        "due_date": a.due_date.strftime("%b %d, %I:%M %p"),
                    }
                    for a in assignments
                ]
            except Exception as e:
                context["canvas_error"] = str(e)

        return context

    def synthesize_daily_plan_stream(self, context: Optional[dict] = None):
        """Stream the synthesized daily plan tokens from Ollama."""
        if not self.ollama.is_available():
            raise RuntimeError(
                f"Ollama server is not responding at {self.ollama.base_url}."
            )

        data = context or self.gather_daily_context()

        system_prompt = (
            "You are LifeOS, an elite executive AI assistant. Your goal is to review "
            "a student/professional's daily calendar, active reminders, and Canvas academic "
            "workload, and synthesize a clear, highly structured Daily Game Plan.\n\n"
            "Important Rules:\n"
            "- Tasks marked as '(End of Day)' have no fixed hour constraint. Treat them as flexible "
            "tasks to fit into open focus windows before the end of the day, NOT as due at midnight."
            "- Make sure to schedule breakfast, lunch, and dinner times so the student knows when to "
            "take breaks throughout their day.\n\n"
            "Formatting guidelines:\n"
            "- Start with a motivational 1-sentence Morning Insight.\n"
            "- ### 🎯 Today's Top Priorities (Pick top 3-4 critical tasks)\n"
            "- ### 📅 Schedule & Time Blocks (Account for fixed events)\n"
            "- ### 📚 Academic Workload (Upcoming Canvas deadlines)\n"
            "- ### ⚡ Actionable Strategy (Clear recommendation on how to execute today)\n"
            "- Keep your tone direct, crisp, and energetic."
        )

        user_prompt = f"Here is today's system data:\n\n{data}"

        return self.ollama.generate_chat_stream(
            system_prompt=system_prompt, user_prompt=user_prompt
        )
