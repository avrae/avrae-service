import functools

import jwt
from flask import current_app, request

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
            uinfo = jwt.decode(the_jwt, config.JWT_SECRET, algorithms=['HS256'],
                               options={'verify_aud': True, 'verify_iss': True},
                               issuer='avrae.io', audience=['avrae.io'])
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


def requires_user_permissions(*required_permissions):
    """
    A wrapper that ensures the user is authenticated and that the user has the given permissions
    (as defined by the user_permissions collection) before running the inner.
    If the user does not have all of the required permissions, returns 403.
    Otherwise, calls the inner with the user as the first argument.
    """

    def wrapper(func):
        @functools.wraps(func)
        @requires_auth
        def inner(user, *args, **kwargs):
            user_permissions = current_app.mdb.user_permissions.find_one({"id": user.id})
            if user_permissions is None:
                return error(403, "User has no permissions")
            elif not all(user_permissions.get(p) for p in required_permissions):
                return error(403, f"Missing one or more permissions: {required_permissions!r}")
            return func(user, *args, **kwargs)

        return inner

    return wrapper
