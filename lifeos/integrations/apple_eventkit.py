"""Apple EventKit integration for macOS Calendars and Reminders via PyObjC."""

import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

# Platform guard: PyObjC only runs on macOS
if sys.platform != "darwin":
    raise ImportError("Apple EventKit integration is only supported on macOS (darwin).")

import Foundation
from EventKit import (
    EKEntityTypeEvent,
    EKEntityTypeReminder,
    EKEvent,
    EKEventStore,
    EKReminder,
    EKSpanThisEvent,
)


@dataclass
class ReminderItem:
    """Standardized representation of an Apple Reminder task."""

    id: str
    title: str
    notes: Optional[str]
    due_date: Optional[datetime]
    is_completed: bool
    calendar_name: str
    has_time: bool = True


@dataclass
class CalendarEventItem:
    """Standardized representation of an Apple Calendar event."""

    id: str
    title: str
    notes: Optional[str]
    start_date: datetime
    end_date: datetime
    location: Optional[str]
    calendar_name: str
    is_all_day: bool


class EventKitBridge:
    """Native PyObjC bridge for macOS EventKit (Calendar & Reminders)."""

    def __init__(self):
        self.store = EKEventStore.alloc().init()

    # -------------------------------------------------------------------------
    # Safe Date Conversion Utilities
    # -------------------------------------------------------------------------

    @staticmethod
    def _nsdate_to_datetime(ns_date: Optional[Foundation.NSDate]) -> Optional[datetime]:
        """Convert macOS NSDate to standard Python timezone-aware datetime."""
        if ns_date is None:
            return None
        return datetime.fromtimestamp(
            ns_date.timeIntervalSince1970()
        ).astimezone()

    @staticmethod
    def _datetime_to_nsdate(dt: datetime) -> Foundation.NSDate:
        """Convert standard Python datetime to macOS NSDate."""
        return Foundation.NSDate.dateWithTimeIntervalSince1970_(dt.timestamp())

    @staticmethod
    def _parse_due_date_components(comp) -> tuple[Optional[datetime], bool]:
        """
        Safely convert NSDateComponents to Python datetime and a has_time boolean.
        If no time component exists, sets time to 23:59:59 (End of Day).
        """
        if not comp:
            return None, False

        undefined = Foundation.NSDateComponentUndefined

        year = comp.year()
        month = comp.month()
        day = comp.day()

        if year == undefined or month == undefined or day == undefined:
            return None, False

        raw_hour = comp.hour()
        raw_minute = comp.minute()

        # Check if user explicitly set a time
        has_time = raw_hour != undefined and raw_minute != undefined

        if has_time:
            hour = raw_hour
            minute = raw_minute
            second = comp.second()
            second = 0 if second == undefined else second
        else:
            # Default to End of Day (23:59:59) for accurate urgency comparisons
            hour, minute, second = 23, 59, 59

        try:
            return datetime(year, month, day, hour, minute, second), has_time
        except (ValueError, OverflowError):
            return None, False

    @staticmethod
    def _datetime_to_components(dt: datetime) -> Foundation.NSDateComponents:
        """Convert Python datetime to NSDateComponents for EKReminder due dates."""
        components = Foundation.NSDateComponents.alloc().init()
        components.setYear_(dt.year)
        components.setMonth_(dt.month)
        components.setDay_(dt.day)
        components.setHour_(dt.hour)
        components.setMinute_(dt.minute)
        components.setSecond_(dt.second)
        return components

    # -------------------------------------------------------------------------
    # Authorization & Permissions
    # -------------------------------------------------------------------------

    def request_permissions(self, entity_type: str = "reminder") -> bool:
        """
        Request system permissions for Reminders or Calendar.
        Triggers native macOS popup prompt on first run.
        """
        target_type = (
            EKEntityTypeReminder if entity_type == "reminder" else EKEntityTypeEvent
        )
        event = threading.Event()
        access_granted = False

        def completion(granted: bool, error):
            nonlocal access_granted
            access_granted = granted
            event.set()

        self.store.requestAccessToEntityType_completion_(target_type, completion)
        event.wait(timeout=10.0)
        return access_granted

    # -------------------------------------------------------------------------
    # Apple Reminders API
    # -------------------------------------------------------------------------

    def fetch_reminders(
        self,
        calendar_name: Optional[str] = None,
        include_completed: bool = False,
    ) -> list[ReminderItem]:
        """Fetch incomplete or all reminders from Apple Reminders."""
        calendars = self.store.calendarsForEntityType_(EKEntityTypeReminder)
        if calendar_name:
            calendars = [c for c in calendars if c.title() == calendar_name]

        if include_completed:
            predicate = self.store.predicateForRemindersInCalendars_(calendars)
        else:
            predicate = (
                self.store.predicateForIncompleteRemindersWithDueDateStarting_ending_calendars_(
                    None, None, calendars
                )
            )

        event = threading.Event()
        raw_reminders = []

        def completion(reminders):
            nonlocal raw_reminders
            if reminders:
                raw_reminders = list(reminders)
            event.set()

        self.store.fetchRemindersMatchingPredicate_completion_(predicate, completion)
        event.wait(timeout=10.0)

        results = []
        for r in raw_reminders:
            due_dt, has_time = self._parse_due_date_components(r.dueDateComponents())

            results.append(
                ReminderItem(
                    id=str(r.calendarItemIdentifier()),
                    title=str(r.title() or ""),
                    notes=str(r.notes()) if r.notes() else None,
                    due_date=due_dt,
                    is_completed=bool(r.isCompleted()),
                    calendar_name=str(r.calendar().title()),
                    has_time=has_time,
                )
            )
        return results

    def create_reminder(
        self,
        title: str,
        due_date: Optional[datetime] = None,
        notes: Optional[str] = None,
        calendar_name: Optional[str] = None,
    ) -> ReminderItem:
        """Create a new task in Apple Reminders."""
        reminder = EKReminder.reminderWithEventStore_(self.store)
        reminder.setTitle_(title)

        if notes:
            reminder.setNotes_(notes)

        if due_date:
            reminder.setDueDateComponents_(self._datetime_to_components(due_date))

        target_calendar = self.store.defaultCalendarForNewReminders()
        if calendar_name:
            calendars = self.store.calendarsForEntityType_(EKEntityTypeReminder)
            matched = [c for c in calendars if c.title() == calendar_name]
            if matched:
                target_calendar = matched[0]

        reminder.setCalendar_(target_calendar)

        success, error = self.store.saveReminder_commit_error_(reminder, True, None)
        if not success:
            raise RuntimeError(f"Failed to create reminder: {error}")

        return ReminderItem(
            id=str(reminder.calendarItemIdentifier()),
            title=title,
            notes=notes,
            due_date=due_date,
            is_completed=False,
            calendar_name=str(target_calendar.title()),
        )

    # -------------------------------------------------------------------------
    # Apple Calendar API
    # -------------------------------------------------------------------------

    def fetch_events(
        self,
        start_date: datetime,
        end_date: datetime,
        calendar_name: Optional[str] = None,
    ) -> list[CalendarEventItem]:
        """Fetch events within a date window from Apple Calendar."""
        calendars = self.store.calendarsForEntityType_(EKEntityTypeEvent)
        if calendar_name:
            calendars = [c for c in calendars if c.title() == calendar_name]

        ns_start = self._datetime_to_nsdate(start_date)
        ns_end = self._datetime_to_nsdate(end_date)

        predicate = self.store.predicateForEventsWithStartDate_endDate_calendars_(
            ns_start, ns_end, calendars
        )
        events = self.store.eventsMatchingPredicate_(predicate)

        results = []
        for e in events or []:
            results.append(
                CalendarEventItem(
                    id=str(e.eventIdentifier()),
                    title=str(e.title() or ""),
                    notes=str(e.notes()) if e.notes() else None,
                    start_date=self._nsdate_to_datetime(e.startDate()),
                    end_date=self._nsdate_to_datetime(e.endDate()),
                    location=str(e.location()) if e.location() else None,
                    calendar_name=str(e.calendar().title()),
                    is_all_day=bool(e.isAllDay()),
                )
            )
        return results

    def create_event(
        self,
        title: str,
        start_date: datetime,
        end_date: datetime,
        location: Optional[str] = None,
        notes: Optional[str] = None,
        calendar_name: Optional[str] = None,
        is_all_day: bool = False,
    ) -> CalendarEventItem:
        """Create a new event in Apple Calendar."""
        event = EKEvent.eventWithEventStore_(self.store)
        event.setTitle_(title)
        event.setStartDate_(self._datetime_to_nsdate(start_date))
        event.setEndDate_(self._datetime_to_nsdate(end_date))
        event.setIsAllDay_(is_all_day)

        if location:
            event.setLocation_(location)
        if notes:
            event.setNotes_(notes)

        target_calendar = self.store.defaultCalendarForNewEvents()
        if calendar_name:
            calendars = self.store.calendarsForEntityType_(EKEntityTypeEvent)
            matched = [c for c in calendars if c.title() == calendar_name]
            if matched:
                target_calendar = matched[0]

        event.setCalendar_(target_calendar)

        success, error = self.store.saveEvent_span_error_(event, EKSpanThisEvent, None)
        if not success:
            raise RuntimeError(f"Failed to create calendar event: {error}")

        return CalendarEventItem(
            id=str(event.eventIdentifier()),
            title=title,
            notes=notes,
            start_date=start_date,
            end_date=end_date,
            location=location,
            calendar_name=str(target_calendar.title()),
            is_all_day=is_all_day,
        )
