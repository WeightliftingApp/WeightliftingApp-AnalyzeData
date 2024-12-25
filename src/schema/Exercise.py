from schema.Set import Set
from typing import Optional
import weakref


class Exercise(object):
    def __init__(
        self,
        workout: object,
        name: str,
        category: str,
        style: str,
        sets: list,
        iteration: Optional[str] = None,
    ):
        self.workout = weakref.ref(workout)
        self.name = name
        self.iteration = iteration
        self.category = category
        self.style = style
        self.sets = list(map(lambda x: Set(**x, exercise=self), sets))

    def displayName(self):
        return f"{self.iteration} {self.name}" if self.iteration else self.name

    def __repr__(self):
        return f"Exercise(name={self.displayName()}, category={self.category}, style={self.style}, sets={len(self.sets)})"
