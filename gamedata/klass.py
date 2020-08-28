from .shared import Sourced


class Class(Sourced):
    def __init__(self, subclasses, *args, **kwargs):
        """
        :type subclasses: list[Sourced]
        """
        super().__init__(*args, **kwargs)
        self.subclasses = subclasses

    @classmethod
    def from_data(cls, entity_type, d):
        subclasses = [Sourced.from_data('class', s) for s in d['subclasses']]
        return cls(subclasses, entity_type, name=d['name'], source=d['source'], entity_id=d['id'], page=d['page'],
                   url=d['url'], is_free=d['isFree'])
