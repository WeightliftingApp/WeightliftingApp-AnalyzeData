from dataclasses import dataclass, field
from typing import List, Any
import weakref
from datetime import datetime

from schema.Exercise import Exercise


@dataclass
class Workout:
    uuid: str
    name: str
    duration: int
    dateModified: bool
    supersets: List[List[int]]
    version: int = 1
    user: Any = field(init=False, repr=False)
    date: datetime = field(init=False)
    exercises: List[Exercise] = field(init=False)

    def __init__(self, user, **data):
        self.uuid = data.get("uuid")
        self.name = data.get("name")
        self.duration = data.get("duration")
        self.dateModified = data.get("dateModified")
        self.supersets = data.get("supersets", [])
        self.user = weakref.ref(user)

        # Clean and normalize the date string
        date_str = data.get("date")

        try:
            self.date = datetime.strptime(date_str, "%Y-%m-%d %H:%M")
        except ValueError:
            try:
                # Replace any kind of whitespace (including invisible ones) with a single space
                date_str = " ".join(date_str.split())
                # Normalize AM/PM format
                date_str = date_str.replace("a.m.", "AM").replace("p.m.", "PM")
                self.date = datetime.strptime(date_str, "%Y-%m-%d %I:%M %p")
            except ValueError:
                raise ValueError(
                    f"Unable to parse date: {date_str}. Expected format: YYYY-MM-DD HH:MM or YYYY-MM-DD HH:MM AM/PM"
                )

        self.exercises = [
            Exercise(**e, workout=self) for e in data.get("exercises", [])
        ]

    def numSets(self):
        return sum(len(exercise.sets) for exercise in self.exercises)

    def volume(self):
        return sum(exercise.volume() for exercise in self.exercises)

    def __repr__(self):
        return f"Workout(name={self.name}, uuid={self.uuid}, date={self.date}, exercises={len(self.exercises)}, supersets={len(self.supersets)})"
