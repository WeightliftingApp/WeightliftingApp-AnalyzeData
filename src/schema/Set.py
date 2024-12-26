from dataclasses import dataclass, field
from typing import Optional, Any
import weakref


@dataclass
class Set:
    reps: Optional[int] = None
    weight: Optional[float] = None
    duration: Optional[float] = None
    distance: Optional[float] = None
    incline: Optional[float] = None
    calories: Optional[int] = None
    custom: Optional[str] = None
    volume: Optional[int] = None
    oneRM: Optional[int] = None
    rpe: Optional[int] = None
    rir: Optional[int] = None
    exercise: Any = field(init=False, repr=False)

    def __init__(self, exercise, **data):
        for key, value in data.items():
            setattr(self, key, value)
        self.exercise = weakref.ref(exercise)

    def __getitem__(self, key):
        return self.__dict__[key]

    def __repr__(self):
        return f"Set({', '.join([f'{k}={v}' for k, v in self.__dict__.items() if v is not None and k != 'exercise'])})"
