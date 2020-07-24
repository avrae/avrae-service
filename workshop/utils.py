import abc

from flask import current_app

from lib.errors import NotAllowed


class MixinBase(abc.ABC):
    def __init__(self, oid):
        """
        :type oid: :class:`bson.ObjectId`
        """
        self.id = oid  # subscribable objects need to know their ObjectId

    @staticmethod
    def sub_coll(mdb):
        """Gets the MongoDB collection used to track subscriptions."""
        raise NotImplementedError

    def remove_all_tracking(self):
        """Removes all subscriber documents associated with this object."""
        self.sub_coll(current_app.mdb).delete_many({"object_id": self.id})


class SubscriberMixin(MixinBase, abc.ABC):
    """A mixin that offers subscription support."""

    def is_subscribed(self, user_id: int):
        """Returns whether the user is subscribed to this object."""
        return (self.sub_coll(current_app.mdb).find_one(
            {"type": "subscribe", "subscriber_id": user_id, "object_id": self.id})) is not None

    def subscribe(self, user_id: int):
        """Adds the user as a subscriber."""
        if self.is_subscribed(user_id):
            raise NotAllowed("You are already subscribed to this.")

        self.sub_coll(current_app.mdb).insert_one(
            {"type": "subscribe", "subscriber_id": user_id, "object_id": self.id}
        )

    def unsubscribe(self, user_id: int):
        """Removes the user from subscribers."""
        if not self.is_subscribed(user_id):
            raise NotAllowed("You are not subscribed to this.")

        self.sub_coll(current_app.mdb).delete_many(
            {"type": {"$in": ["subscribe", "active"]}, "subscriber_id": user_id, "object_id": self.id}
            # unsubscribe, unactive
        )

    def num_subscribers(self):
        """Returns the number of subscribers."""
        return self.sub_coll(current_app.mdb).count_documents({"type": "subscribe", "object_id": self.id})

    @classmethod
    def my_subs(cls, user_id: int):
        """Returns an async iterator of dicts representing the subscription objects."""
        for sub in cls.sub_coll(current_app.mdb).find({"type": "subscribe", "subscriber_id": user_id}):
            yield sub

    @classmethod
    def my_sub_ids(cls, user_id: int):
        """Returns an async iterator of ObjectIds representing objects the user is subscribed to."""
        for sub in cls.my_subs(user_id):
            yield sub['object_id']


class GuildActiveMixin(MixinBase, abc.ABC):
    """A mixin that offers guild active support."""

    def is_server_active(self, guild_id: int):
        """Returns whether the object is active on this server."""
        return (self.sub_coll(current_app.mdb).find_one(
            {"type": "server_active", "subscriber_id": guild_id, "object_id": self.id})) is not None

    def toggle_server_active(self, guild_id: int):
        """Toggles whether the object is active in the contextual guild.
        Returns a bool representing its new activity."""
        if self.is_server_active(guild_id):  # I subscribed and want to unsubscribe
            self.unset_server_active(guild_id)
            return False
        else:  # no one has served this object and I want to
            self.set_server_active(guild_id)
            return True

    def set_server_active(self, guild_id: int):
        """Sets the object as active for the contextual guild."""
        self.sub_coll(current_app.mdb).insert_one(
            {"type": "server_active", "subscriber_id": guild_id, "object_id": self.id})

    def unset_server_active(self, guild_id: int):
        """Sets the object as inactive for the contextual guild."""
        self.sub_coll(current_app.mdb).delete_many(
            {"type": "server_active", "subscriber_id": guild_id, "object_id": self.id})

    def num_server_active(self):
        """Returns the number of guilds that have this object active."""
        return self.sub_coll(current_app.mdb).count_documents({"type": "server_active", "object_id": self.id})

    @classmethod
    def guild_active_subs(cls, guild_id: int):
        """Returns an async iterator of dicts representing the subscription object."""
        for sub in cls.sub_coll(current_app.mdb).find({"type": "server_active", "subscriber_id": guild_id}):
            yield sub

    @classmethod
    def guild_active_ids(cls, guild_id: int):
        """Returns a async iterator of ObjectIds representing the objects active in the guild."""
        for sub in cls.guild_active_subs(guild_id):
            yield sub['object_id']


class EditorMixin(MixinBase, abc.ABC):
    """A mixin that offers editor tracking."""

    def is_editor(self, user_id: int):
        """Returns whether the given user can edit this object."""
        return (self.sub_coll(current_app.mdb).find_one(
            {"type": "editor", "subscriber_id": user_id, "object_id": self.id})) is not None

    def toggle_editor(self, user_id: int):
        """Toggles whether a user is allowed to edit the given object.
        Returns whether they can after operations.
        """
        if not self.is_editor(user_id):
            self.add_editor(user_id)
            return True
        else:
            self.remove_editor(user_id)
            return False

    def add_editor(self, user_id: int):
        """Adds the user to the editor list of this object."""
        if self.is_editor(user_id):
            raise NotAllowed("you are already an editor")
        self.sub_coll(current_app.mdb).insert_one({"type": "editor", "subscriber_id": user_id, "object_id": self.id})

    def remove_editor(self, user_id: int):
        """Removes the user from the editor list of this object."""
        self.sub_coll(current_app.mdb).delete_many({"type": "editor", "subscriber_id": user_id, "object_id": self.id})

    def get_editor_ids(self):
        """Returns an iterator of user ids (int) that can edit this object."""
        for sub in self.sub_coll(current_app.mdb).find({"type": "editor", "object_id": self.id}):
            yield sub['subscriber_id']

    @classmethod
    def my_editable_ids(cls, user_id: int):
        """Returns an iterator of ObjectIds representing objects the user can edit."""
        for sub in cls.sub_coll(current_app.mdb).find({"type": "editor", "subscriber_id": user_id}):
            yield sub['object_id']
