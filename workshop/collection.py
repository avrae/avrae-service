import abc
import collections
import datetime
import enum
import json

import requests
from bson import ObjectId
from flask import current_app

import config
from lib.errors import NotAllowed
from lib.utils import HelperEncoder
from workshop.errors import CollectableNotFound, CollectionNotFound
from workshop.mixins import EditorMixin, GuildActiveMixin, SubscriberMixin


class PublicationState(enum.Enum):
    PRIVATE = 'PRIVATE'
    UNLISTED = 'UNLISTED'
    PUBLISHED = 'PUBLISHED'


class WorkshopCollection(SubscriberMixin, GuildActiveMixin, EditorMixin):
    def __init__(self,
                 _id, name, description, image, owner,
                 alias_ids, snippet_ids,
                 publish_state, num_subscribers, num_guild_subscribers, last_edited, created_at, tags):
        """
        :param _id: The MongoDB ID of this collection.
        :type _id: bson.ObjectId
        :param name: The name of this collection.
        :type name: str
        :param description: The description.
        :type description: str
        :param image: The URL to the image for this collection, if applicable.
        :type image: str or None
        :param owner: The owner ID of this collection.
        :type owner: int
        :param alias_ids: A list of alias IDs contained in this collection.
        :type alias_ids: list[ObjectId]
        :param snippet_ids: A list of snippet IDs contained in this collection.
        :type snippet_ids: list[ObjectId]
        :param publish_state: The publication state of this collection.
        :type publish_state: PublicationState
        :param num_subscribers: The approximate number of subscribers of this collection.
        :type num_subscribers: int
        :param num_guild_subscribers: The approximate number of guilds subscribed to this collection.
        :type num_guild_subscribers: int
        :param last_edited: The time this collection was last edited.
        :type last_edited: datetime.datetime
        :param created_at: The time this collection was created.
        :type created_at: datetime.datetime
        :param tags: The tags of this collection
        :type tags: list[str]
        """
        super().__init__(_id)
        self.name = name
        self.description = description
        self.image = image
        self.owner = owner
        self._aliases = None
        self._snippets = None
        self.publish_state = publish_state
        self.approx_num_subscribers = num_subscribers
        self.approx_num_guild_subscribers = num_guild_subscribers
        self.last_edited = last_edited
        self.created_at = created_at
        self.tags = tags
        # lazy-load aliases/snippets
        self.alias_ids = alias_ids
        self.snippet_ids = snippet_ids

    @property
    def url(self):
        return f"https://avrae.io/dashboard/workshop/{self.id}"

    @property
    def aliases(self):
        if self._aliases is None:
            self.load_aliases()
        return self._aliases

    @property
    def snippets(self):
        if self._snippets is None:
            self.load_snippets()
        return self._snippets

    def load_aliases(self):
        self._aliases = []
        for alias_id in self.alias_ids:
            self._aliases.append(WorkshopAlias.from_id(alias_id, collection=self, parent=None))
        return self._aliases

    def load_snippets(self):
        self._snippets = []
        for snippet_id in self.snippet_ids:
            self._snippets.append(WorkshopSnippet.from_id(snippet_id, collection=self))
        return self._snippets

    # constructors
    @classmethod
    def from_id(cls, _id):
        if not isinstance(_id, ObjectId):
            _id = ObjectId(_id)

        raw = current_app.mdb.workshop_collections.find_one({"_id": _id})
        if raw is None:
            raise CollectionNotFound()

        return cls(raw['_id'], raw['name'], raw['description'], raw['image'], raw['owner'],
                   raw['alias_ids'], raw['snippet_ids'],
                   PublicationState(raw['publish_state']), raw['num_subscribers'], raw['num_guild_subscribers'],
                   raw['last_edited'], raw['created_at'], raw['tags'])

    # helpers
    @classmethod
    def user_owned_ids(cls, user_id: int):
        """Returns an iterator of ObjectIds of objects the contextual user owns."""
        for obj in current_app.mdb.workshop_collections.find({"owner": user_id}, ['_id']):
            yield obj['_id']

    @classmethod
    def user_subscribed(cls, user_id: int):
        """Returns an iterator of WorkshopCollections that the user has subscribed to."""
        for coll_id in cls.my_sub_ids(user_id):
            try:
                yield cls.from_id(coll_id)
            except CollectionNotFound:
                continue

    @classmethod
    def server_subscribed(cls, guild_id: int):
        """Returns an generator of WorkshopCollections that the server has subscribed to."""
        for coll_id in cls.guild_active_ids(guild_id):
            try:
                yield cls.from_id(coll_id)
            except CollectionNotFound:
                continue

    def is_owner(self, user_id: int):
        return user_id == self.owner

    def to_dict(self, js=False):
        out = {
            "name": self.name, "description": self.description, "image": self.image, "owner": self.owner,
            "alias_ids": self.alias_ids, "snippet_ids": self.snippet_ids,
            "publish_state": self.publish_state.value, "num_subscribers": self.approx_num_subscribers,
            "num_guild_subscribers": self.approx_num_guild_subscribers, "last_edited": self.last_edited,
            "created_at": self.created_at, "tags": self.tags
        }
        if js:
            out['owner'] = str(self.owner)
            out['_id'] = self.id
        return out

    # database operations
    @classmethod
    def create_new(cls, user_id: int, name, description, image):
        """Inserts a new collection into the database and returns the new collection."""
        if not name:
            raise NotAllowed("Name is required.")
        if not description:
            raise NotAllowed("Description is required.")
        now = datetime.datetime.now()
        # noinspection PyTypeChecker
        # id is None until inserted
        inst = cls(None, name, description, image, user_id, [], [], PublicationState.PRIVATE, 0, 0, now, now, [])
        result = current_app.mdb.workshop_collections.insert_one(inst.to_dict())
        inst.id = result.inserted_id
        inst.update_elasticsearch()
        return inst

    def update_info(self, name: str, description: str, image):
        """Updates the collection's user information."""
        if not name:
            raise NotAllowed("Name is required.")
        if not description:
            raise NotAllowed("Description is required.")
        current_app.mdb.workshop_collections.update_one(
            {"_id": self.id},
            {
                "$set": {"name": name, "description": description, "image": image},
                "$currentDate": {"last_edited": True}
            }
        )
        self.name = name
        self.description = description
        self.image = image
        self.last_edited = datetime.datetime.now()
        self.update_elasticsearch()

    def delete(self, run_checks=True):
        if run_checks:
            # do not allow deletion of published collections
            if self.publish_state == PublicationState.PUBLISHED:
                raise NotAllowed("You cannot delete a published collection.")

        # delete all children
        for alias in self.aliases:
            alias.delete(run_checks)
        for snippet in self.snippets:
            snippet.delete(run_checks)

        # delete from db
        current_app.mdb.workshop_collections.delete_one(
            {"_id": self.id}
        )

        # delete subscriptions
        self.sub_coll(current_app.mdb).delete_many({"object_id": self.id})

        # delete from elasticsearch
        requests.delete(f"{config.ELASTICSEARCH_ENDPOINT}/workshop_collections/_doc/{str(self.id)}")

    def update_edit_time(self, update_es=True):
        current_app.mdb.workshop_collections.update_one(
            {"_id": self.id},
            {"$currentDate": {"last_edited": True}}
        )
        self.last_edited = datetime.datetime.now()
        if update_es:
            self.update_elasticsearch()

    def set_state(self, new_state, run_checks=True):
        """
        Updates the collection's publication state, running checks as necessary.

        :type new_state: str or PublicationState
        :param bool run_checks: Whether or not to run the publication state checks (bypass for moderation).
        """
        if isinstance(new_state, str):
            new_state = PublicationState(new_state.upper())

        if new_state == self.publish_state:  # we don't need to do anything
            return

        if run_checks:
            # cannot unpublish
            if self.publish_state == PublicationState.PUBLISHED:
                raise NotAllowed("You cannot unpublish a collection after it has been published")

            # prepublish check: name and description are present, at least one alias/snippet
            if new_state == PublicationState.PUBLISHED:
                if not self.name:
                    raise NotAllowed("A name must be present to publish this collection")
                if not self.description:
                    raise NotAllowed("A description must be present to publish this collection")
                if len(self.alias_ids) == 0 and len(self.snippet_ids) == 0:
                    raise NotAllowed("At least one alias or snippet must be present to publish this collection")

        current_app.mdb.workshop_collections.update_one(
            {"_id": self.id},
            {
                "$set": {"publish_state": new_state.value},
                "$currentDate": {"last_edited": True}
            }
        )
        self.publish_state = new_state
        self.last_edited = datetime.datetime.now()
        self.update_elasticsearch()

    def create_alias(self, name, docs):
        code = f"echo The `{name}` alias does not have an active code version. Please contact the collection author, " \
               f"or if you are the author, create or select an active code version on the Alias Workshop."
        # noinspection PyTypeChecker
        # id is None until inserted
        inst = WorkshopAlias(None, name, code, [], docs, [], self.id, [], None, collection=self)
        result = current_app.mdb.workshop_aliases.insert_one(inst.to_dict())
        inst.id = result.inserted_id

        # update collection references
        if self._aliases is not None:
            self._aliases.append(inst)
        current_app.mdb.workshop_collections.update_one(
            {"_id": self.id},
            {
                "$push": {"alias_ids": result.inserted_id},
                "$currentDate": {"last_edited": True}
            }
        )
        self.alias_ids.append(result.inserted_id)
        self.last_edited = datetime.datetime.now()

        # update all subscriber bindings
        new_binding = {"name": inst.name, "id": inst.id}
        self.sub_coll(current_app.mdb).update_many(
            {"type": {"$in": ["subscribe", "server_active"]}, "object_id": self.id},
            {"$push": {"alias_bindings": new_binding}}
        )

        self.update_elasticsearch()

        return inst

    def create_snippet(self, name, docs):
        code = f'-phrase "The `{name}` snippet does not have an active code version. Please contact the collection ' \
               f'author, or if you are the author, create or select an active code version on the Alias Workshop."'
        # noinspection PyTypeChecker
        # id is None until inserted
        inst = WorkshopSnippet(None, name, code, [], docs, [], self.id, collection=self)
        result = current_app.mdb.workshop_snippets.insert_one(inst.to_dict())
        inst.id = result.inserted_id

        # update collection references
        if self._snippets is not None:
            self._snippets.append(inst)
        current_app.mdb.workshop_collections.update_one(
            {"_id": self.id},
            {
                "$push": {"snippet_ids": result.inserted_id},
                "$currentDate": {"last_edited": True}
            }
        )
        self.snippet_ids.append(result.inserted_id)
        self.last_edited = datetime.datetime.now()

        # update all subscriber bindings
        new_binding = {"name": inst.name, "id": inst.id}
        self.sub_coll(current_app.mdb).update_many(
            {"type": {"$in": ["subscribe", "server_active"]}, "object_id": self.id},
            {"$push": {"snippet_bindings": new_binding}}
        )

        self.update_elasticsearch()

        return inst

    def add_tag(self, tag: str):
        """Adds a tag to this collection. Validates the tag. Does nothing if the tag already exists."""
        if current_app.mdb.workshop_tags.find_one({"slug": tag}) is None:
            raise NotAllowed(f"{tag} is not a valid tag")
        if tag in self.tags:
            return  # we already have the tag, do a no-op

        current_app.mdb.workshop_collections.update_one(
            {"_id": self.id},
            {
                "$push": {"tags": tag},
                "$currentDate": {"last_edited": True}
            }
        )
        self.tags.append(tag)
        self.last_edited = datetime.datetime.now()
        self.update_elasticsearch()

    def remove_tag(self, tag: str):
        """Removes a tag from this collection. Does nothing if the tag is not in the collection."""
        if tag not in self.tags:
            return  # we already don't have the tag, do a no-op

        current_app.mdb.workshop_collections.update_one(
            {"_id": self.id},
            {
                "$pull": {"tags": tag},
                "$currentDate": {"last_edited": True}
            }
        )
        self.tags.remove(tag)
        self.last_edited = datetime.datetime.now()
        self.update_elasticsearch()

    # bindings
    def _generate_default_alias_bindings(self):
        """
        Returns a list of {name: str, id: ObjectId} bindings based on the default names of aliases in the collection.
        """
        return [{"name": alias.name, "id": alias.id} for alias in self.aliases]

    def _generate_default_snippet_bindings(self):
        """
        Returns a list of {name: str, id: ObjectId} bindings based on the default names of snippets in the collection.
        """
        return [{"name": snippet.name, "id": snippet.id} for snippet in self.snippets]

    def _bindings_sanity_check(self, the_ids, the_bindings, binding_cls):
        # sanity check: ensure all aliases are in the bindings
        binding_ids = {b['id'] for b in the_bindings}
        missing_ids = set(the_ids).difference(binding_ids)
        for missing in missing_ids:
            obj = binding_cls.from_id(missing, collection=self)
            the_bindings.append({"name": obj.name, "id": obj.id})

        # sanity check: ensure all names are valid
        for binding in the_bindings:
            if ' ' in binding['name']:
                raise NotAllowed("Spaces are not allowed in bindings.")
            # alias-only checks
            if binding_cls is WorkshopAlias:
                if binding['name'] in current_app.rdb.jget("default_commands", []):
                    raise NotAllowed(f"{binding['name']} is already a built-in command.")
            # snippet-only checks
            if binding_cls is WorkshopSnippet:
                if len(binding['name']) < 2:
                    raise NotAllowed("Snippet names must be at least 2 characters.")

        # sanity check: ensure there is no binding to anything deleted
        return [b for b in the_bindings if b['id'] in the_ids]

    # implementations
    @staticmethod
    def sub_coll(mdb):
        return mdb.workshop_subscriptions

    def subscribe(self, user_id: int, alias_bindings=None, snippet_bindings=None):
        """Updates the contextual author as a subscriber, with given name bindings."""
        if self.publish_state == PublicationState.PRIVATE and not (self.is_owner(user_id) or self.is_editor(user_id)):
            raise NotAllowed("This collection is private.")

        # generate default bindings
        if alias_bindings is None:
            alias_bindings = self._generate_default_alias_bindings()
        else:
            alias_bindings = self._bindings_sanity_check(self.alias_ids, alias_bindings, WorkshopAlias)

        if snippet_bindings is None:
            snippet_bindings = self._generate_default_snippet_bindings()
        else:
            snippet_bindings = self._bindings_sanity_check(self.snippet_ids, snippet_bindings, WorkshopSnippet)

        # insert subscription
        result = self.sub_coll(current_app.mdb).update_one(
            {"type": "subscribe", "subscriber_id": user_id, "object_id": self.id},
            {"$set": {"alias_bindings": alias_bindings, "snippet_bindings": snippet_bindings}},
            upsert=True
        )

        if result.upserted_id is not None:
            # increase subscription count
            current_app.mdb.workshop_collections.update_one(
                {"_id": self.id},
                {"$inc": {"num_subscribers": 1}}
            )
            # log subscribe event
            self.log_event(
                {"type": "subscribe", "object_id": self.id, "timestamp": datetime.datetime.utcnow(), "user_id": user_id}
            )

        return {"alias_bindings": alias_bindings, "snippet_bindings": snippet_bindings,
                "new_subscription": result.upserted_id is not None}

    def unsubscribe(self, user_id: int):
        # remove sub doc
        super().unsubscribe(user_id)
        # decr sub count
        current_app.mdb.workshop_collections.update_one(
            {"_id": self.id},
            {"$inc": {"num_subscribers": -1}}
        )
        # log unsub event
        self.log_event(
            {"type": "unsubscribe", "object_id": self.id, "timestamp": datetime.datetime.utcnow(), "user_id": user_id}
        )

    def set_server_active(self, guild_id: int, alias_bindings=None, snippet_bindings=None, invoker_id: int = None):
        """Sets the object as active for the contextual guild, with given name bindings."""
        if self.publish_state == PublicationState.PRIVATE \
                and not (self.is_owner(invoker_id) or self.is_editor(invoker_id)):
            raise NotAllowed("This collection is private.")

        # generate default bindings
        if alias_bindings is None:
            alias_bindings = self._generate_default_alias_bindings()
        else:
            alias_bindings = self._bindings_sanity_check(self.alias_ids, alias_bindings, WorkshopAlias)

        if snippet_bindings is None:
            snippet_bindings = self._generate_default_snippet_bindings()
        else:
            snippet_bindings = self._bindings_sanity_check(self.snippet_ids, snippet_bindings, WorkshopSnippet)

        # insert sub doc
        result = self.sub_coll(current_app.mdb).update_one(
            {"type": "server_active", "subscriber_id": guild_id, "object_id": self.id},
            {"$set": {"alias_bindings": alias_bindings, "snippet_bindings": snippet_bindings}},
            upsert=True
        )

        if result.upserted_id is not None:
            # incr sub count
            current_app.mdb.workshop_collections.update_one(
                {"_id": self.id},
                {"$inc": {"num_guild_subscribers": 1}}
            )
            # log sub event
            self.log_event(
                {"type": "server_subscribe", "object_id": self.id, "timestamp": datetime.datetime.utcnow(),
                 "user_id": invoker_id}
            )

        return {"alias_bindings": alias_bindings, "snippet_bindings": snippet_bindings,
                "new_subscription": result.upserted_id is not None}

    def unset_server_active(self, guild_id: int, invoker_id: int = None):
        # remove sub doc
        super().unset_server_active(guild_id)
        # decr sub count
        current_app.mdb.workshop_collections.update_one(
            {"_id": self.id},
            {"$inc": {"num_guild_subscribers": -1}}
        )
        # log unsub event
        self.log_event(
            {"type": "server_unsubscribe", "object_id": self.id, "timestamp": datetime.datetime.utcnow(),
             "user_id": invoker_id}
        )

    def update_elasticsearch(self):
        """POSTs the latest version of this collection to ElasticSearch (fire-and-forget)."""
        requests.post(
            f"{config.ELASTICSEARCH_ENDPOINT}/workshop_collections/_doc/{str(self.id)}",
            data=json.dumps(self.to_dict(), cls=HelperEncoder),
            headers={"Content-Type": "application/json"}
        )

    @staticmethod
    def log_event(event):
        """Logs the event and pushes it to ElasticSearch."""
        es_event = event.copy()  # we make a copy because mdb insert adds an _id field which makes es unhappy
        current_app.mdb.analytics_alias_events.insert_one(event)

        # add a sub_score metric
        es_event['sub_score'] = 0
        if es_event['type'] in ('subscribe', 'server_subscribe'):
            es_event['sub_score'] = 1
        elif es_event['type'] in ('unsubscribe', 'server_unsubscribe'):
            es_event['sub_score'] = -1

        requests.post(
            f"{config.ELASTICSEARCH_ENDPOINT}/workshop_events/_doc",
            data=json.dumps(es_event, cls=HelperEncoder),
            headers={"Content-Type": "application/json"}
        )


class WorkshopCollectableObject(abc.ABC):
    def __init__(self, _id, name,
                 code, versions, docs, entitlements, collection_id,
                 collection=None):
        """
        :param _id: The MongoDB ID of this object.
        :type _id: bson.ObjectId
        :param name: The name of this object.
        :type name: str
        :param code: The code of this object.
        :type code: str
        :param versions: A list of code versions of this object.
        :type versions: list[CodeVersion]
        :param docs: The help docs of this object.
        :type docs: str
        :param entitlements: A list of entitlements required to run this.
        :type entitlements: list[RequiredEntitlement]
        :param collection_id: The ID of the top-level Collection this object is a member of.
        :type collection_id: ObjectId
        :param collection: The top-level Collection this object is a member of.
        :type collection: WorkshopCollection
        """
        self.id = _id
        self.name = name
        self.code = code
        self.versions = versions
        self.docs = docs
        self.entitlements = entitlements
        self._collection = collection
        # lazy-load collection
        self._collection_id = collection_id

    @property
    def short_docs(self):
        return self.docs.split('\n')[0]

    @property
    def collection(self):
        if self._collection is None:
            self.load_collection()
        return self._collection

    def load_collection(self):
        self._collection = WorkshopCollection.from_id(self._collection_id)
        return self._collection

    def get_entitlements(self):
        """Returns a dict of {entity_type: [entity_id]} for required entitlements."""
        out = collections.defaultdict(lambda: [])
        for ent in self.entitlements:
            out[ent.entity_type].append(ent.entity_id)
        return out

    def to_dict(self, js=False):
        versions = [cv.to_dict() for cv in self.versions]
        entitlements = [ent.to_dict() for ent in self.entitlements]
        out = {
            "name": self.name, "code": self.code, "versions": versions, "docs": self.docs, "entitlements": entitlements,
            "collection_id": self._collection_id
        }
        if js:
            out['_id'] = self.id
        return out

    @staticmethod
    def mdb_coll():
        raise NotImplementedError

    # database touchers
    def update_info(self, name: str, docs: str):
        """Updates the alias' information."""
        self.mdb_coll().update_one(
            {"_id": self.id},
            {"$set": {"name": name, "docs": docs}}
        )
        self.name = name
        self.docs = docs
        self.collection.update_edit_time()

    def create_code_version(self, content: str):
        """Creates a new inactive code version, incrementing version num and setting creation time."""
        version = max((cv.version for cv in self.versions), default=0) + 1
        cv = CodeVersion(version, content, datetime.datetime.now(), False)
        self.mdb_coll().update_one(
            {"_id": self.id},
            {"$push": {"versions": cv.to_dict()}}
        )
        self.versions.append(cv)
        self.collection.update_edit_time()
        return cv

    def set_active_code_version(self, version: int):
        """Sets the code version with version=version active."""
        cv = next((cv for cv in self.versions if cv.version == version), None)
        if cv is None:
            raise NotAllowed("This code version does not exist")
        # set correct current version and update code
        self.mdb_coll().update_one(
            {"_id": self.id},
            {"$set": {
                "code": cv.content,
                "versions.$[current].is_current": True,
                "versions.$[notcurrent].is_current": False
            }},
            array_filters=[{"current.version": version}, {"notcurrent.version": {"$ne": version}}]
        )
        for old_cv in self.versions:
            old_cv.is_current = False
        cv.is_current = True
        self.code = cv.content
        self.collection.update_edit_time()

    def add_entitlement(self, sourced_entity, required=False):
        """
        Adds a required entitlement to this collectable.

        :type sourced_entity: gamedata.shared.Sourced
        :param bool required: Whether or not this entitlement is required by a moderator (cannot be removed).
        """
        if sourced_entity.is_free:
            raise NotAllowed("This entitlement is for a free object.")
        re = RequiredEntitlement(sourced_entity.entity_type, sourced_entity.entity_id, required)
        if (re.entity_type, re.entity_id) in ((existing.entity_type, existing.entity_id) for existing in
                                              self.entitlements):
            raise NotAllowed("This collectable already has this entitlement required.")
        # add to database
        self.mdb_coll().update_one(
            {"_id": self.id},
            {"$push": {
                "entitlements": re.to_dict()
            }}
        )
        self.collection.update_edit_time()
        self.entitlements.append(re)
        return [e.to_dict() for e in self.entitlements]

    def remove_entitlement(self, sourced_entity, ignore_required=False):
        """
        Removes a required entitlement from this collectable.

        :type sourced_entity: gamedata.shared.Sourced
        :param bool ignore_required: Whether to allow removing moderator-required entitlements.
        """
        existing = next((e for e in self.entitlements if
                         (e.entity_type, e.entity_id) == (sourced_entity.entity_type, sourced_entity.entity_id)), None)
        if existing is None:
            raise NotAllowed("This collectable does not require this entitlement.")
        if existing.required and not ignore_required:
            raise NotAllowed("This entitlement is required.")
        # add to database
        self.mdb_coll().update_one(
            {"_id": self.id},
            {"$pull": {
                "entitlements": {"entity_type": existing.entity_type, "entity_id": existing.entity_id}
            }}
        )
        self.collection.update_edit_time()
        self.entitlements.remove(existing)
        return [e.to_dict() for e in self.entitlements]


class WorkshopAlias(WorkshopCollectableObject):
    def __init__(self, _id, name, code, versions, docs, entitlements, collection_id, subcommand_ids, parent_id,
                 collection=None, parent=None):
        """
        :param subcommand_ids: The alias IDs that are a child of this alias.
        :type subcommand_ids: list[ObjectId]
        :param parent: The alias that is a parent of this alias, if applicable.
        :type parent: WorkshopAlias or None
        """
        super().__init__(_id, name, code, versions, docs, entitlements,
                         collection_id=collection_id, collection=collection)
        self._subcommands = None
        self._parent = parent
        # lazy-load subcommands, collection, parent
        self._subcommand_ids = subcommand_ids
        self._parent_id = parent_id

    @property
    def parent(self):
        if self._parent_id is None:
            return None
        if self._parent is None:
            self.load_parent()
        return self._parent

    @property
    def has_parent(self):
        return self._parent_id is not None

    @property
    def subcommands(self):
        if self._subcommands is None:
            self.load_subcommands()
        return self._subcommands

    def load_parent(self):
        self._parent = WorkshopAlias.from_id(self._parent_id, collection=self._collection)
        return self._parent

    def load_subcommands(self):
        self._subcommands = []
        for subcommand_id in self._subcommand_ids:
            self._subcommands.append(
                WorkshopAlias.from_id(subcommand_id, collection=self._collection, parent=self))
        return self._subcommands

    @staticmethod
    def mdb_coll():
        return current_app.mdb.workshop_aliases

    # constructors
    @classmethod
    def from_dict(cls, raw, collection=None, parent=None):
        versions = [CodeVersion.from_dict(cv) for cv in raw['versions']]
        entitlements = [RequiredEntitlement.from_dict(ent) for ent in raw['entitlements']]
        return cls(raw['_id'], raw['name'], raw['code'], versions, raw['docs'], entitlements, raw['collection_id'],
                   raw['subcommand_ids'], raw['parent_id'], collection, parent)

    @classmethod
    def from_id(cls, _id, collection=None, parent=None):
        if not isinstance(_id, ObjectId):
            _id = ObjectId(_id)

        raw = cls.mdb_coll().find_one({"_id": _id})
        if raw is None:
            raise CollectableNotFound()
        return cls.from_dict(raw, collection, parent)

    def to_dict(self, js=False):
        out = super().to_dict(js)
        out.update({
            "subcommand_ids": self._subcommand_ids, "parent_id": self._parent_id
        })
        return out

    # database touchers
    def create_subalias(self, name, docs):
        code = f"echo The `{name}` alias does not have an active code version. Please contact the collection author, " \
               f"or if you are the author, create or select an active code version on the Alias Workshop."
        # noinspection PyTypeChecker
        inst = WorkshopAlias(None, name, code, [], docs, [], self.collection.id, [], self.id, parent=self)
        result = self.mdb_coll().insert_one(inst.to_dict())
        inst.id = result.inserted_id

        # update alias references
        if self._subcommands is not None:
            self._subcommands.append(inst)
        self.mdb_coll().update_one(
            {"_id": self.id},
            {"$push": {"subcommand_ids": result.inserted_id}}
        )
        self._subcommand_ids.append(result.inserted_id)

        self.collection.update_edit_time()
        return inst

    def delete(self, run_checks=True):
        """Deletes the alias from the collection."""

        if run_checks:
            # do not allow deletion of top-level aliases
            if self.collection.publish_state == PublicationState.PUBLISHED and self._parent_id is None:
                raise NotAllowed("You cannot delete a top-level alias from a published collection.")

        if self._parent_id is None:
            # clear all bindings
            self.collection.sub_coll(current_app.mdb).update_many(
                {"type": {"$in": ["subscribe", "server_active"]}, "object_id": self.collection.id},
                {"$pull": {"alias_bindings": {"id": self.id}}}
                # pull from the alias_bindings array all docs with this id
            )

            # remove reference from collection
            current_app.mdb.workshop_collections.update_one(
                {"_id": self.collection.id},
                {"$pull": {"alias_ids": self.id}}
            )
            self.collection.alias_ids.remove(self.id)
        else:
            # remove reference from parent
            self.mdb_coll().update_one(
                {"_id": self.parent.id},
                {"$pull": {"subcommand_ids": self.id}}
            )
            self.parent._subcommand_ids.remove(self.id)

        # delete all children
        for child in self.subcommands:
            child.delete(run_checks)

        self.collection.update_edit_time()

        # delete from db
        self.mdb_coll().delete_one(
            {"_id": self.id}
        )


class WorkshopSnippet(WorkshopCollectableObject):
    @classmethod
    def from_id(cls, _id, collection=None):
        if not isinstance(_id, ObjectId):
            _id = ObjectId(_id)

        raw = current_app.mdb.workshop_snippets.find_one({"_id": _id})
        if raw is None:
            raise CollectableNotFound()

        versions = [CodeVersion.from_dict(cv) for cv in raw['versions']]
        entitlements = [RequiredEntitlement.from_dict(ent) for ent in raw['entitlements']]
        return cls(raw['_id'], raw['name'], raw['code'], versions, raw['docs'], entitlements,
                   raw['collection_id'], collection)

    @staticmethod
    def mdb_coll():
        return current_app.mdb.workshop_snippets

    # database touchers
    def delete(self, run_checks=True):
        """Deletes the snippet from the collection."""

        if run_checks:
            # do not allow deletion of top-level aliases
            if self.collection.publish_state == PublicationState.PUBLISHED:
                raise NotAllowed("You cannot delete a top-level snippet from a published collection.")

        # clear all bindings
        self.collection.sub_coll(current_app.mdb).update_many(
            {"type": {"$in": ["subscribe", "server_active"]}, "object_id": self.collection.id},
            {"$pull": {"snippet_bindings": {"id": self.id}}}
            # pull from the snippet_bindings array all docs with this id
        )

        # remove reference from collection
        current_app.mdb.workshop_collections.update_one(
            {"_id": self.collection.id},
            {"$pull": {"snippet_ids": self.id}}
        )
        self.collection.snippet_ids.remove(self.id)
        self.collection.update_edit_time()

        # delete from db
        self.mdb_coll().delete_one(
            {"_id": self.id}
        )


class CodeVersion:
    def __init__(self, version, content, created_at, is_current):
        """
        :param version: The version of code.
        :type version: int
        :param content: The content of this version.
        :type content: str
        :param created_at: The time this version was created.
        :type created_at: datetime.datetime
        :param is_current: Whether this version is the current live version.
        :type is_current: bool
        """
        self.version = version
        self.content = content
        self.created_at = created_at
        self.is_current = is_current

    @classmethod
    def from_dict(cls, raw):
        return cls(**raw)

    def to_dict(self):
        return {
            "version": self.version, "content": self.content, "created_at": self.created_at,
            "is_current": self.is_current
        }


class RequiredEntitlement:
    """An entitlement that a user must have to invoke this alias/snippet."""

    def __init__(self, entity_type, entity_id, required=False):
        """
        :param str entity_type: The entity type of the required entitlement.
        :param int entity_id: The entity id of the required entitlement.
        :param bool required: Whether this entitlement was required by a moderator and cannot be removed.
        """
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.required = required

    @classmethod
    def from_dict(cls, raw):
        return cls(**raw)

    def to_dict(self):
        return {
            "entity_type": self.entity_type, "entity_id": self.entity_id, "required": self.required
        }
