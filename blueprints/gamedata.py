"""
Misc endpoints to return gamedata (e.g. entitlements, limited uses)
"""
from flask import Blueprint, request

from gamedata.compendium import compendium
from gamedata.mixins import DescribableMixin
from lib.utils import success

gamedata = Blueprint('gamedata', __name__)


@gamedata.route("entitlements", methods=["GET"])
def get_entitlements():
    """
    Gets a dict of all valid entitlements.
    Query: free: bool - include free entities?
    {type-id -> entitlement}
    """
    if 'free' in request.args:
        return success({
            f"{t}-{i}": sourced.to_minimal_dict()
            for (t, i), sourced
            in compendium.entitlement_lookup.items()
        })
    return success({
        f"{t}-{i}": sourced.to_minimal_dict()
        for (t, i), sourced
        in compendium.entitlement_lookup.items()
        if not sourced.is_free
    })


@gamedata.route("limiteduse", methods=["GET"])
def get_limited_use():
    """Returns a list of valid entities for use in building an AbilityReference in the automation builder."""
    return success(compendium.raw_limiteduse)


@gamedata.route("describable", methods=["GET"])
def get_describables():
    """Returns a list of valid entities that are describable (for the purpose of building a Text AbilityReference)."""
    # noinspection PyUnresolvedReferences
    # all instances of DescribableMixins are also instances of Sourced here
    return success([
        sourced.to_minimal_dict()
        for (t, i), sourced
        in compendium.entity_lookup.items()
        if isinstance(sourced, DescribableMixin) and isinstance(t, str)
    ])
