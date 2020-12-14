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
            return error(401, "missing credentials")

        try:
            uinfo = jwt.decode(the_jwt, config.JWT_SECRET, algorithms='HS256', issuer='avrae.io', audience='avrae.io',
                               verify=True)
        except jwt.InvalidTokenError:
            return error(403, "invalid credentials")

        try:
            user = UserInfo(uinfo)
        except KeyError:
            return error(403, "invalid credentials")

        return func(user, *args, **kwargs)

    return inner


def maybe_auth(func):
    """
    A wrapper that passes the authenticated user as the first argument to the inner if the authorization header is
    present, otherwise passes None as the first argument.

    If the auth header is present but invalid, returns 403 {success: false, error: "invalid credentials"}.
    """

    @functools.wraps(func)
    def inner(*args, **kwargs):
        if 'Authorization' not in request.headers:
            return func(None, *args, **kwargs)
        return requires_auth(func)(*args, **kwargs)

    return inner
