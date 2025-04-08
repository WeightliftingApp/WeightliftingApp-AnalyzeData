from dataclasses import dataclass, field
from typing import Optional, Any, List
import weakref

from schema.Set import Set


@dataclass
class Exercise:
    name: str
    category: str
    style: str
    iteration: Optional[str] = None
    workout: Any = field(init=False, repr=False)
    sets: List[Set] = field(init=False)

    def __init__(self, workout, **data):
        self.name = data.get("name")
        self.category = data.get("category")
        self.style = data.get("style")
        self.iteration = data.get("iteration")
        self.workout = weakref.ref(workout)
        self.sets = [Set(**s, exercise=self) for s in data.get("sets", [])]

    def volume(self):
        return sum(set.volume or 0 for set in self.sets)

    def displayName(self) -> str:
        return f"{self.iteration} {self.name}" if self.iteration else self.name

    def __repr__(self):
        return f"Exercise(name={self.displayName()}, category={self.category}, style={self.style}, sets={len(self.sets)})"
