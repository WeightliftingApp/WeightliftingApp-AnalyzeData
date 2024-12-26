from dataclasses import dataclass, field
from typing import Optional, Any, Dict
import weakref


@dataclass
class Settings:
    startWeekOnMonday: bool
    disableSleep: bool
    weightInLbs: bool
    distanceInMiles: bool
    restTimerDuration: int
    restTimerAutoStart: bool
    restTimerNotification: bool
    showSmartNames: bool
    smartNicknames: Dict[str, str]
    showEquivalencyChart: bool
    showLastWorkout: bool
    showWorkoutDetails: bool
    nonRepSetsVolume: bool
    bodyweightIsVolume: bool
    bodyweightMultiplier: float
    prefersRIR: Optional[bool] = None
    graphScaleYEnabled: Optional[bool] = None
    showSortDuringExercise: Optional[bool] = None
    sortToShowDuringExercise: Optional[int] = None
    data: Any = field(init=False, repr=False)

    def __init__(self, data, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.data = weakref.ref(data)

    def weightMultiplier(self) -> float:
        return 1 if self.weightInLbs else 2.20462

    def weightSuffix(self) -> str:
        return "lbs" if self.weightInLbs else "kg"

    def __repr__(self) -> str:
        return "Settings()"
