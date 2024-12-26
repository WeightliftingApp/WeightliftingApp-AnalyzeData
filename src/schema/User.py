from dataclasses import dataclass, field
from typing import Optional, Any
import weakref


@dataclass
class User:
    dateCreated: str
    totalWorkouts: int = 0
    totalExercises: int = 0
    totalSets: int = 0
    totalVolume: int = 0
    totalDuration: int = 0
    currentStreak: int = 0
    longestStreak: int = 0
    xp: int = 0
    achievementListVersion: int = 0
    name: Optional[str] = None
    weight: Optional[float] = None
    imageData: Optional[str] = None
    data: Any = field(init=False, repr=False)
    settings: Any = field(init=False, repr=False)

    def __init__(self, data, settings, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.data = weakref.ref(data)
        self.settings = weakref.ref(settings)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, User):
            return self.name == other.name
        return False

    def __hash__(self) -> int:
        return hash(self.name)

    def __repr__(self):
        return f"User(name={self.name}, workouts={self.totalWorkouts}, xp={self.xp})"
