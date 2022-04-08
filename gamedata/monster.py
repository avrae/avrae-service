import logging

from .shared import Sourced

log = logging.getLogger(__name__)


# NOTE: monsters aren't really useful in the API, and it'd be a pain to implement all the functionality -
# we just have the minimal class here for lookup
class Monster(Sourced):
    entity_type = "monster"
    type_id = 779871897

    def __init__(self, name, **kwargs):
        super().__init__(**kwargs)
        self.name = name

    @classmethod
    def from_data(cls, d):
        return cls(
            name=d["name"],
            homebrew=False,
            source=d["source"],
            entity_id=d["id"],
            page=d["page"],
            url=d["url"],
            is_free=d["isFree"],
        )
