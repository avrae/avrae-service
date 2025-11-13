"""
Pydantic automation validation.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Union

from pydantic import ValidationError


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
        for i, key in enumerate(error["loc"]):
            if key == "__root__":  # this is if the model is a custom root - we're at the root already so no change
                continue
            try:
                inst = inst[key]
            except (KeyError, IndexError):
                i = -1
                cur_key = the_error.model.__name__
                break
            if isinstance(inst, dict) and "name" in inst:
                cur_key = str(inst["name"])
                break
        else:  # if there is none, emit the error on the root
            i = -1
            cur_key = the_error.model.__name__

        # the location of the error inside `cur_key` is the rest of the `loc`
        error_location = (" -> ".join(map(str, error["loc"][i + 1 :]))).replace("__root__", "root")

        # add the error to the list of errors on this key
        error_dict[cur_key].append(f"""
            <li>
                <em>{error_location}</em> — {error['msg'].capitalize()}
            </li>
            """)

    title = f"{len(errors)} validation errors in {len(error_dict)} object"

    error_list = [f"""
        <p class='validation-error-item'>
            <strong>{name[:50]}</strong>
        </p>
        <ul class='validation-error-list'>
            {''.join(loc)}
        </ul>
        """ for name, loc in error_dict.items()]

    return f"<h3 class='validation-error-header'>{title}</h3>\n" + "\n".join(error_list)
