from dataclasses import dataclass, field
from typing import List, Dict
import json
from schema.User import User
from schema.Settings import Settings
from schema.Workout import Workout


@dataclass
class WLD:
    version: int = 1
    achievements: List[dict] = field(default_factory=list)
    templateList: Dict[str, dict] = field(default_factory=dict)
    typeList: List[str] = field(init=False)
    workouts: List[Workout] = field(init=False)
    settings: Settings = field(init=False)
    user: User = field(init=False)

    def __init__(self, file_path: str = None, **data):
        if file_path is not None:
            with open(file_path, "r") as f:
                data = json.load(f)

        self.version = data.get("version", 1)
        self.achievements = data.get("achievements", [])
        self.templateList = data.get("templateList", {})
        self.typeList = data["typeList"]["list"]
        self.settings = Settings(**data["settings"], data=self)
        self.user = User(**data["user"], data=self, settings=self.settings)
        self.workouts = [Workout(**w, user=self.user) for w in data["workouts"]]

    def __repr__(self):
        return f"WLD(version={self.version}, achievements={len(self.achievements)}, templateList={len(self.templateList)}, typeList={len(self.typeList)}, workouts={len(self.workouts)}, settings={self.settings}, user={self.user})"
