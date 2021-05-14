import copy
import logging

from gamedata.klass import Class
from gamedata.shared import Sourced

log = logging.getLogger(__name__)


class Compendium:
    # noinspection PyTypeHints
    # prevents pycharm from freaking out over type comments
    def __init__(self):
        # raw data
        self.raw_backgrounds = []  # type: list[dict]
        self.raw_monsters = []  # type: list[dict]
        self.raw_classes = []  # type: list[dict]
        self.raw_feats = []  # type: list[dict]
        self.raw_items = []  # type: list[dict]
        self.raw_races = []  # type: list[dict]
        self.raw_subraces = []  # type: list[dict]
        self.raw_spells = []  # type: list[dict]
        self.raw_limiteduse = []  # type: list[dict]

        # models
        self.backgrounds = []  # type: list[Sourced]

        self.classes = []  # type: list[Class]
        self.subclasses = []  # type: list[Sourced]

        self.races = []  # type: list[Sourced]
        self.subraces = []  # type: list[Sourced]

        self.feats = []  # type: list[Sourced]
        self.items = []  # type: list[Sourced]
        self.monsters = []  # type: list[Sourced]
        self.spells = []  # type: list[Sourced]

        # lookup helpers
        self.entitlement_lookup = {}

    def reload(self, mdb):
        log.info("Reloading data")
        self.load_all_mongodb(mdb)
        self.load_common()
        log.info(f"Data loading complete - {len(self.entitlement_lookup)} objects registered")

    def load_all_mongodb(self, mdb):
        lookup = {d['key']: d['object'] for d in mdb.static_data.find({})}

        self.raw_classes = lookup.get('classes', [])
        self.raw_feats = lookup.get('feats', [])
        self.raw_monsters = lookup.get('monsters', [])
        self.raw_backgrounds = lookup.get('backgrounds', [])
        self.raw_items = lookup.get('items', [])
        self.raw_races = lookup.get('races', [])
        self.raw_subraces = lookup.get('subraces', [])
        self.raw_spells = lookup.get('spells', [])
        self.raw_limiteduse = lookup.get('limiteduse', [])

    def load_common(self):
        self.entitlement_lookup = {}

        def deserialize_and_register_lookups(cls, data_source, entity_type):
            out = []
            for entity_data in data_source:
                entity = cls.from_data(entity_type, entity_data)
                self._register_entitlement_lookup(entity, entity_type)
                out.append(entity)
            return out

        self.backgrounds = deserialize_and_register_lookups(Sourced, self.raw_backgrounds, 'background')
        self.classes = deserialize_and_register_lookups(Class, self.raw_classes, 'class')
        self.races = deserialize_and_register_lookups(Sourced, self.raw_races, 'race')
        self.subraces = deserialize_and_register_lookups(Sourced, self.raw_subraces, 'subrace')
        self.feats = deserialize_and_register_lookups(Sourced, self.raw_feats, 'feat')
        self.items = deserialize_and_register_lookups(Sourced, self.raw_items, 'magic-item')
        self.monsters = deserialize_and_register_lookups(Sourced, self.raw_monsters, 'monster')
        self.spells = deserialize_and_register_lookups(Sourced, self.raw_spells, 'spell')

        # generated
        self._load_subclasses()

    def _load_subclasses(self):
        self.subclasses = []
        for cls in self.classes:
            for subcls in cls.subclasses:
                copied = copy.copy(subcls)
                copied.name = f"{cls.name}: {subcls.name}"
                # register lookups
                self._register_entitlement_lookup(copied, 'class')
                self.subclasses.append(copied)

    def _register_entitlement_lookup(self, entity, entity_type):
        if entity.entity_id < 0:  # negative entity IDs is a nonmagical item hack, and can be ignored for now
            return
        k = (entity_type, entity.entity_id)
        if k in self.entitlement_lookup:
            log.info(f"Overwriting existing entity lookup key: {k} "
                     f"({self.entitlement_lookup[k].name} -> {entity.name})")
        self.entitlement_lookup[k] = entity

    # helpers
    def lookup_by_entitlement(self, entity_type: str, entity_id: int):
        """Gets an entity by its entitlement data."""
        return self.entitlement_lookup.get((entity_type, entity_id))


compendium = Compendium()
