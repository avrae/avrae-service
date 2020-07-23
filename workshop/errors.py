from lib.errors import AvraeException


class CollectionNotFound(AvraeException):
    def __init__(self, msg="collection not found"):
        super().__init__(msg)


class CollectableNotFound(AvraeException):
    def __init__(self, msg="collectible not found"):
        super().__init__(msg)
