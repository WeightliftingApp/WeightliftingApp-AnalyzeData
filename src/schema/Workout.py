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
        self.date = datetime.strptime(data.get("date"), "%Y-%m-%d %H:%M")
        self.exercises = [
            Exercise(**e, workout=self) for e in data.get("exercises", [])
        ]

    def __repr__(self):
        return f"Workout(name={self.name}, uuid={self.uuid}, date={self.date}, dateModified={self.dateModified}, exercises={len(self.exercises)}, supersets={len(self.supersets)})"
