from schema.Exercise import Exercise
import weakref
from datetime import datetime


class Workout(object):
    def __init__(
        self,
        uuid: str,
        user: object,
        name: str,
        date: str,
        duration: int,
        dateModified: bool,
        exercises: list,
        supersets: list,
    ):
        self.user = weakref.ref(user)
        self.uuid = uuid
        self.name = name
        self.date = datetime.strptime(date, "%Y-%m-%d %H:%M")
        self.duration = duration
        self.dateModified = dateModified
        self.exercises = list(map(lambda x: Exercise(**x, workout=self), exercises))
        self.supersets = supersets

    def __repr__(self):
        return f"Workout(name={self.name}, uuid={self.uuid}, date={self.date}, dateModified={self.dateModified}, exercises={len(self.exercises)}, supersets={len(self.supersets)})"
