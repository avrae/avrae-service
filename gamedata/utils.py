from gamedata import constants


def long_source_name(source):
    return constants.SOURCE_MAP.get(source, source)


def source_slug(source):
    return constants.SOURCE_SLUG_MAP.get(source)
