from pymongo import AsyncMongoClient


class MongoClient(AsyncMongoClient):
    def __init__(self, uri: str, **kwargs):
        super().__init__(host=uri, **kwargs)
        self.__settings = self.get_database("settings")
        self.button_store = self.__settings.get_collection("button_store")
        self.recruit_data = self.__settings.get_collection("recruit_data")
        self.auto_recruit = self.__settings.get_collection("auto_recruit")