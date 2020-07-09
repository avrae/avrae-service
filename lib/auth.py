import functools

import jwt
from flask import request

import config
from lib.discord import UserInfo
from lib.utils import error


def requires_auth(func):
    """
    A wrapper that ensures the user is authenticated before running the inner.
    If the user is not, returns 403 {success: false, error: "invalid credentials"}.
    Otherwise, calls the inner with the user as the first argument.
    """

    @functools.wraps(func)
    def inner(*args, **kwargs):
        try:
            the_jwt = request.headers['Authorization']
        except KeyError:
            return error(403, "missing credentials")

        uinfo = jwt.decode(the_jwt, config.JWT_SECRET, algorithms='HS256', issuer='avrae.io', audience='avrae.io',
                           verify=True)
        user = UserInfo(uinfo)

        return func(user, *args, **kwargs)

    return inner
