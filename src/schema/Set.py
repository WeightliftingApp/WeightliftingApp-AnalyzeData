from typing import Optional
import weakref


class Set(object):
    def __init__(
        self,
        exercise: object,
        reps: Optional[int] = None,
        weight: Optional[float] = None,
        duration: Optional[float] = None,
        distance: Optional[float] = None,
        incline: Optional[float] = None,
        calories: Optional[int] = None,
        custom: Optional[str] = None,
        volume: Optional[int] = None,
        oneRM: Optional[int] = None,
        rpe: Optional[int] = None,
        rir: Optional[int] = None,
    ):
        self.exercise = weakref.ref(exercise)
        self.reps = reps
        self.weight = weight
        self.duration = duration
        self.distance = distance
        self.incline = incline
        self.calories = calories
        self.custom = custom
        self.volume = volume
        self.oneRM = oneRM
        self.rpe = rpe
        self.rir = rir

    def __getitem__(self, key):
        return self.__dict__[key]

    def __repr__(self):
        return f"Set({', '.join([f'{k}={v}' for k, v in self.__dict__.items() if v is not None and k != 'exercise'])})"
