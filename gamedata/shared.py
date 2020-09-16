from gamedata.utils import source_slug


class Sourced:
    """
    A base class for entities with a source. Modified from Avrae gamedata to provide minimum functionality for
    entitlements endpoints.
    """

    def __init__(self, entity_type: str, name: str, source: str, entity_id: int = None,
                 page: int = None, url: str = None, is_free: bool = False):
        """
        :param entity_type: The type of this entity.
        :param name: The name of this entity.
        :param source: The abbreviated source this entity comes from.
        :param entity_id: The DDB Entity ID
        :param page: The page number from that source this entity can be found on.
        :param url: The URL that this entity can be found at.
        :param is_free: Whether or not this entity requires a purchase to view.
        """
        self.entity_type = entity_type
        self.name = name
        self.source = source
        self.entity_id = entity_id
        self.page = page
        self._url = url
        self.is_free = is_free

    @classmethod
    def from_data(cls, entity_type, d):
        return cls(entity_type, name=d['name'], source=d['source'], entity_id=d['id'], page=d['page'], url=d['url'],
                   is_free=d['isFree'])

    def source_str(self):
        if self.page is None:
            return self.source
        return f"{self.source} {self.page}"  # e.g. "PHB 196"

    @property
    def url(self):
        """Returns the reference URL for this sourced object."""
        if self._url:
            return f"{self._url}?utm_source=avrae&utm_medium=reference"
        return None

    @property
    def marketplace_url(self):
        """Returns the marketplace URL for this sourced object."""
        if self._url:
            return f"{self._url}?utm_source=avrae&utm_medium=marketplacelink"
        elif slug := source_slug(self.source):
            return f"https://www.dndbeyond.com/marketplace/sources/{slug}?utm_source=avrae&utm_medium=marketplacelink"
        return f"https://www.dndbeyond.com/marketplace?utm_source=avrae&utm_medium=marketplacelink"

    def to_dict(self):
        return {
            "entity_type": self.entity_type, "name": self.name, "source": self.source, "entity_id": self.entity_id,
            "page": self.page, "is_free": self.is_free, "url": self.url, "marketplace_url": self.marketplace_url
        }

    def __repr__(self):
        return f"<{type(self).__name__} entity_id={self.entity_id} entity_type={self.entity_type} {self._url}>"
