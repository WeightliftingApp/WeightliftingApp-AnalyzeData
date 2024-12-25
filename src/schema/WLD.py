from schema.User import User
from schema.Settings import Settings
from schema.Workout import Workout


class WLD(object):
    def __init__(
        self,
        typeList: dict,
        achievements: list,
        templateList: dict,
        workouts: list,
        settings: dict,
        user: dict,
        version: int,
    ):
        self.typeList = typeList["list"]
        self.achievements = achievements
        self.templateList = templateList
        self.settings = Settings(**settings, data=self)
        self.user = User(**user, data=self, settings=self.settings)
        self.workouts = list(map(lambda x: Workout(**x, user=self.user), workouts))
        self.version = version

    def __repr__(self):
        return f"WLD(typeList={len(self.typeList)}, achievements={len(self.achievements)}, templateList={len(self.templateList)}, workouts={len(self.workouts)}, settings={len(self.settings)}, user={len(self.user)}, version={self.version})"
