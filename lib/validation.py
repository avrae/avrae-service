"""
Pydantic automation validation.
"""
from __future__ import annotations

import abc
from typing import Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ValidationError, conint, constr, validator

# ==== automation ====
str255 = constr(max_length=255, strip_whitespace=True)
str1024 = constr(max_length=1024, strip_whitespace=True)
str4096 = constr(max_length=4096, strip_whitespace=True)


# ---- Helper Models ----
class HigherLevels(BaseModel):
    __root__: Dict[constr(regex=r'[0-9]'), str255]


class SpellSlotReference(BaseModel):
    slot: conint(ge=1, le=9)


class AbilityReference(BaseModel):
    id: int
    typeId: int


# ---- effects ----
class Effect(BaseModel, abc.ABC):
    type: str
    meta: Optional[List[Effect]]

    @classmethod
    def __get_validators__(cls):
        yield cls.return_effect

    @classmethod
    def return_effect(cls, values):  # https://github.com/samuelcolvin/pydantic/issues/619#issuecomment-713508861
        try:
            etype = values["type"]
        except KeyError:
            raise ValueError("missing 'type' key")
        try:
            return EFFECT_TYPES[etype](**values)
        except KeyError:
            raise ValueError(f"{etype} is not a valid effect type")


Effect.update_forward_refs()


class Target(Effect):
    type: Literal['target']
    target: Union[Literal['all', 'each', 'self'], conint(ge=1)]
    effects: List[Effect]


class Attack(Effect):
    type: Literal['attack']
    hit: List[Effect]
    miss: List[Effect]
    attackBonus: Optional[str255]


class Save(Effect):
    type: Literal['save']
    stat: Literal['str', 'dex', 'con', 'int', 'wis', 'cha']
    fail: List[Effect]
    success: List[Effect]
    dc: Optional[str255]


class Damage(Effect):
    type: Literal['damage']
    damage: str255
    overheal: Optional[bool]
    higher: Optional[HigherLevels]
    cantripScale: Optional[bool]


class TempHP(Effect):
    type: Literal['temphp']
    amount: str255
    higher: Optional[HigherLevels]
    cantripScale: Optional[bool]


class IEffect(Effect):
    type: Literal['ieffect']
    name: str255
    duration: Union[int, str255]
    effects: str1024
    end: Optional[bool]
    conc: Optional[bool]
    desc: Optional[str4096]
    stacking: Optional[bool]


class Roll(Effect):
    type: Literal['roll']
    dice: str255
    name: str255
    higher: Optional[HigherLevels]
    cantripScale: Optional[bool]
    hidden: Optional[bool]


class Text(Effect):
    type: Literal['text']
    text: Union[AbilityReference, str4096]


class SetVariable(Effect):
    type: Literal['variable']
    name: str255
    value: str255
    higher: Optional[HigherLevels]
    onError: Optional[str255]

    @validator('name', allow_reuse=True)
    def name_should_be_identifier(cls, v: str):
        assert v.isidentifier(), "must be a valid identifier"
        return v


class Condition(Effect):
    type: Literal['condition']
    condition: str255
    onTrue: List[Effect]
    onFalse: List[Effect]
    errorBehaviour: Optional[Literal['true', 'false', 'both', 'neither', 'raise']]


class UseCounter(Effect):
    type: Literal['counter']
    counter: Union[SpellSlotReference, AbilityReference, str255]
    amount: str255
    allowOverflow: Optional[bool]
    errorBehaviour: Optional[Literal['warn', 'raise']]


class CastSpell(Effect):
    type: Literal['spell']
    id: int
    level: Optional[int]
    dc: Optional[str255]
    attackBonus: Optional[str255]
    castingMod: Optional[str255]


class Automation(BaseModel):
    __root__: List[Effect]


EFFECT_TYPES = {
    "target": Target,
    "attack": Attack,
    "save": Save,
    "damage": Damage,
    "temphp": TempHP,
    "ieffect": IEffect,
    "roll": Roll,
    "text": Text,
    "variable": SetVariable,
    "condition": Condition,
    "counter": UseCounter,
    "spell": CastSpell
}


def is_valid_automation(automation):
    try:
        Automation.parse_obj(automation)
    except ValidationError as e:
        return False, str(e)
    return True, None
