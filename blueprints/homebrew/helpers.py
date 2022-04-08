from flask import Response, abort


# permission query helpers
def user_is_owner(data_coll, user, obj_id):
    data = data_coll.find_one({"_id": obj_id}, ["owner"])
    if data is None:
        abort(Response("Object not found", 404))
    return int(user.id) == data["owner"]


def user_can_edit(data_coll, sub_coll, user, obj_id):
    can_edit = sub_coll.find_one({"type": "editor", "subscriber_id": int(user.id), "object_id": obj_id}) is not None
    return can_edit or user_is_owner(data_coll, user, obj_id)


def user_can_view(data_coll, sub_coll, user, obj_id):
    data = data_coll.find_one({"_id": obj_id}, ["public"])
    if data is None:
        abort(Response("Object not found", 404))
    return data["public"] or (user is not None and user_can_edit(data_coll, sub_coll, user, obj_id))


# data iterators
def user_owned(data_coll, user):
    return data_coll.find({"owner": int(user.id)})


def user_editable(data_coll, sub_coll, user):
    for obj in user_owned(data_coll, user):
        yield obj
    for sub_obj in sub_coll.find({"type": "editor", "subscriber_id": int(user.id)}):
        obj = data_coll.find_one({"_id": sub_obj["object_id"]})
        if obj is not None:
            yield obj


def user_subscribed(data_coll, sub_coll, user):
    for obj in user_editable(data_coll, sub_coll, user):
        yield obj
    for sub_obj in sub_coll.find({"type": "subscribe", "subscriber_id": int(user.id)}):
        obj = data_coll.find_one({"_id": sub_obj["object_id"]})
        if obj is not None:
            yield obj
