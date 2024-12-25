from typing import Optional
import weakref


class Settings(object):
    def __init__(
        self,
        data: object,
        startWeekOnMonday: bool,
        disableSleep: bool,
        weightInLbs: bool,
        distanceInMiles: bool,
        restTimerDuration: int,
        restTimerAutoStart: bool,
        restTimerNotification: bool,
        showSmartNames: bool,
        smartNicknames: dict,
        showEquivalencyChart: bool,
        showLastWorkout: bool,
        showWorkoutDetails: bool,
        nonRepSetsVolume: bool,
        bodyweightIsVolume: bool,
        bodyweightMultiplier: float,
        prefersRIR: Optional[bool] = None,
        graphScaleYEnabled: Optional[bool] = None,
        showSortDuringExercise: Optional[bool] = None,
        sortToShowDuringExercise: Optional[int] = None,
    ):
        self.data = weakref.ref(data)
        self.startWeekOnMonday = startWeekOnMonday
        self.disableSleep = disableSleep
        self.weightInLbs = weightInLbs
        self.distanceInMiles = distanceInMiles
        self.prefersRIR = prefersRIR
        self.restTimerDuration = restTimerDuration
        self.restTimerAutoStart = restTimerAutoStart
        self.restTimerNotification = restTimerNotification
        self.showSmartNames = showSmartNames
        self.smartNicknames = smartNicknames
        self.graphScaleYEnabled = graphScaleYEnabled
        self.showEquivalencyChart = showEquivalencyChart
        self.showLastWorkout = showLastWorkout
        self.showSortDuringExercise = showSortDuringExercise
        self.sortToShowDuringExercise = sortToShowDuringExercise
        self.showWorkoutDetails = showWorkoutDetails
        self.nonRepSetsVolume = nonRepSetsVolume
        self.bodyweightIsVolume = bodyweightIsVolume
        self.bodyweightMultiplier = bodyweightMultiplier

    def weightMultiplier(self):
        return 1 if self.weightInLbs else 2.20462

    def weightSuffix(self):
        return "lbs" if self.weightInLbs else "kg"

    def __repr__(self):
        return "Settings()"
