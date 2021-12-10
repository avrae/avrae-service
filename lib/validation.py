"""
Pydantic automation validation.
"""
from __future__ import annotations

import abc
from collections import defaultdict
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
    slot: Union[conint(ge=1, le=9), str255]


class AbilityReference(BaseModel):
    id: int
    typeId: int


def str_is_identifier(value: str):
    if not value.isidentifier():
        raise ValueError("value must be a valid identifier")
    return value


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
    save_as: Optional[str255]
    parent: Optional[str255]

    _save_as_identifier = validator("save_as", allow_reuse=True)(str_is_identifier)


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

    _name_identifier = validator("name", allow_reuse=True)(str_is_identifier)


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


def parse_validation_error(data: Union[Dict, List], the_error: ValidationError) -> str:
    """
    Generates a human-readable HTML snippet detailing the validation error.
    
    :param data: The data that parsing raised an error.
    :param the_error: The raised error.
    """
    # group errors by the instance
    error_dict: Dict[str, List[str]] = defaultdict(list)
    errors = the_error.errors()

    for error in errors:
        inst = data
        # enter the error's loc until `inst` is a dict with a `name` key
        for i, key in enumerate(error['loc']):
            if key == '__root__':  # this is if the model is a custom root - we're at the root already so no change
                continue
            try:
                inst = inst[key]
            except (KeyError, IndexError):
                i = -1
                cur_key = the_error.model.__name__
                break
            if isinstance(inst, dict) and 'name' in inst:
                cur_key = str(inst['name'])
                break
        else:  # if there is none, emit the error on the root
            i = -1
            cur_key = the_error.model.__name__

        # the location of the error inside `cur_key` is the rest of the `loc`
        error_location = (' -> '.join(map(str, error['loc'][i + 1:]))).replace('__root__', 'root')

        # add the error to the list of errors on this key
        error_dict[cur_key].append(
            f"""
            <li>
                <em>{error_location}</em> — {error['msg'].capitalize()}
            </li>
            """
        )

    title = f"{len(errors)} validation errors in {len(error_dict)} object"

    error_list = [
        f"""
        <p class='validation-error-item'>
            <strong>{name[:50]}</strong>
        </p>
        <ul class='validation-error-list'>
            {''.join(loc)}
        </ul>
        """
        for name, loc in error_dict.items()
    ]

    return f"<h3 class='validation-error-header'>{title}</h3>\n" + '\n'.join(error_list)
