import json
from typing import Union, Optional, Any, Tuple
from warnings import warn

from aredis import RedisError
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, ValidationError
from pymongo.results import UpdateResult, InsertOneResult

from gflbans.internal.log import logger
from gflbans.internal.utils import validate


def _clean(d):
    a = d
    if '_id' in a and a['_id'] is None:
        del a['_id']
    return a


# NOTE: On caching: Sometimes, we can load things from a cache to avoid a DB query
# for any function that is a getty function, you can pass a cache reference into the cache param
# Only use this for areas where it doesn't really matter if the data is a little bit out of a date.
# (Such as various frontend requests)
class DBase(BaseModel):
    __collection__ = 'base'

    id: Optional[ObjectId]

    class Config:
        arbitrary_types_allowed = True
        underscore_attrs_are_private = False
        orm_mode = True
        fields = {'id': '_id'}

    @classmethod
    def load_document(cls, doc):
        try:
            return cls(**doc)
        except ValidationError:
            if '_id' in doc:
                logger.error(f'Validation of document {str(doc["_id"])} has failed.', exc_info=True)
            raise

    @classmethod
    async def from_id(cls, db_ref: AsyncIOMotorDatabase, obj_id: Union[str, ObjectId]):
        if isinstance(obj_id, str):
            p_id = ObjectId(obj_id)
        else:
            p_id = obj_id

        p = await db_ref[cls.__collection__].find_one({'_id': p_id})

        if p is None:
            logger.debug(f'tried to load {str(p_id)} from {cls.__collection__}, but could not find it')
            return None

        logger.debug(f'loaded {str(p_id)} of {cls.__collection__}')

        return cls.load_document(p)

    @classmethod
    async def find_one_from_query(cls, db_ref: AsyncIOMotorDatabase, query: dict):
        p = await db_ref[cls.__collection__].find_one(query)

        if p is None:
            return None

        logger.debug(f'loaded {str(p["_id"])} of {cls.__collection__}')

        return cls.load_document(p)

    @classmethod
    def _from_query(cls, db_ref: AsyncIOMotorDatabase, query: dict, limit=None, skip=0,
                    sort: Tuple[str, Any] = None):
        qk = json.dumps(query, default=lambda o: str(o))

        logger.debug(f'DB: running query {qk} with limit {limit}'
                     f', skip {skip}, and sort {sort}')

        dcur = db_ref[cls.__collection__].find(query)

        if sort is not None:
            dcur.sort(sort[0], direction=sort[1])

        if limit is not None:
            dcur.limit(limit)

        if skip > 0:
            dcur.skip(skip)

        return dcur

    @classmethod
    async def from_query(cls, db_ref: AsyncIOMotorDatabase, query: dict, limit=None, skip=0,
                         sort: Tuple[str, Any] = None):
        async for document in cls._from_query(db_ref, query, limit, skip, sort):
            logger.debug(f'DB: load {str(document["_id"])} of {cls.__collection__}')
            yield cls.load_document(document)

    @classmethod
    async def list_from_query(cls, db_ref: AsyncIOMotorDatabase, query: dict, limit=30, skip=0,
                              sort: Tuple[str, Any] = None):
        return [cls.load_document(x) for x in await cls._from_query(db_ref, query, limit, skip, sort).to_list(limit)]

    @classmethod
    async def count(cls, db_ref: AsyncIOMotorDatabase, query: dict):
        return await db_ref[cls.__collection__].count_documents(query)

    async def commit(self, db_ref: AsyncIOMotorDatabase) -> Union[UpdateResult, InsertOneResult]:
        validate(self)

        if self.id is not None and isinstance(self.id, ObjectId):
            logger.debug(f'DB: update policy {str(self.id)}')

            # Already exists! Try to replace and do an upsert if not found
            if self.__collection__ == 'rpc':
                ur: UpdateResult = await db_ref[self.__collection__].replace_one(
                    {'_id': self.id}, _clean(self.dict(by_alias=True, exclude_none=True, exclude_unset=False)), upsert=True)
            else:
                ur: UpdateResult = await db_ref[self.__collection__].replace_one(
                    {'_id': self.id}, _clean(self.dict(by_alias=True, exclude_none=True, exclude_unset=True)), upsert=True)

            assert ur.acknowledged

            if ur.upserted_id is not None:
                logger.warning(f'DB: we thought {str(self.id)} existed, but it didn\'t. Now {str(ur.upserted_id)}')
                self.id = ur.upserted_id

            return ur
        else:
            self.id = None
            if self.__collection__ == 'rpc':
                ior: InsertOneResult = await db_ref[self.__collection__].insert_one(_clean(self.dict(by_alias=True,
                                                                                                    exclude_unset=False,
                                                                                                    exclude_none=True)))
            else:
                ior: InsertOneResult = await db_ref[self.__collection__].insert_one(_clean(self.dict(by_alias=True,
                                                                                                    exclude_unset=True,
                                                                                                    exclude_none=True)))

            assert ior.acknowledged

            self.id = ior.inserted_id
            logger.debug(f'DB: saved {str(self.id)} of {self.__collection__}')

            return ior

    async def unset_field(self, db_ref: AsyncIOMotorDatabase, field: str, session=None):
        if self.id is None:
            raise ValueError('Tried to unset a field when this object doesn\'t exist in the DB')

        if field not in self.__fields__:
            raise KeyError(f'{field} is not a valid field for this type.')

        setattr(self, field, None)

        validate(self)

        return await db_ref[self.__collection__].update_one({'_id': self.id}, {
            '$unset': {self.__fields__[field].alias: ''}
        }, session=session)

    async def update_field(self, db_ref: AsyncIOMotorDatabase, field: str, value: Any, session=None):
        if self.id is None:
            raise ValueError('Tried to prepare a field update for this object when it has not yet been '
                             'written to the database')

        if field not in self.__fields__:
            raise KeyError(f'{field} is not a field of this object')

        if value is None:
            warn(f'Attempting to null set field {field} of {self.__collection__}. Did you want to unset it instead?')

        setattr(self, field, value)

        validate(self)

        if hasattr(value, 'dict'):
            value = value.dict(by_alias=True,
                               exclude_unset=True,
                               exclude_none=True)

        if type(value) == list:
            nl = []

            for v in value:
                if hasattr(v, 'dict'):
                    nl.append(v.dict(by_alias=True, exclude_unset=True, exclude_none=True))
                else:
                    nl.append(v)
            value = nl

        return await db_ref[self.__collection__].update_one({'_id': self.id}, {
            '$set': {
                self.__fields__[field].alias: value
            }
        }, session=session)

    async def add_bit_flag(self, db_ref: AsyncIOMotorDatabase, field: str, value: int, session=None):
        if self.id is None:
            raise ValueError('Cannot add bit flag to this object that has not been committed yet')

        if field not in self.__fields__:
            raise KeyError(f'No such field {field}')

        setattr(self, field, getattr(self, field) | value)

        validate(self)

        return await db_ref[self.__collection__].update_one({'_id': self.id}, {
            '$bit': {
                self.__fields__[field].alias: {
                    'or': value
                }
            }
        }, session=session)

    async def remove_bit_flag(self, db_ref: AsyncIOMotorDatabase, field: str, value: int, session=None):
        if self.id is None:
            raise ValueError('Cannot add bit flag to this object that has not been committed yet')

        if field not in self.__fields__:
            raise KeyError(f'No such field {field}')

        setattr(self, field, getattr(self, field) & ~value)

        validate(self)

        return await db_ref[self.__collection__].update_one({'_id': self.id}, {
            '$bit': {
                self.__fields__[field].alias: {
                    'and': ~value
                }
            }
        }, session=session)

    async def append_to_array_field(self, db_ref: AsyncIOMotorDatabase, field: str, value: Any, session=None):
        if self.id is None:
            raise ValueError('Cannot modify a document that has not yet been committed.')

        if field not in self.__fields__:
            raise KeyError(f'No such field {field}')

        arr = getattr(self, field)

        arr.append(value)

        setattr(self, field, arr)

        validate(self)

        if hasattr(value, 'dict'):
            value = value.dict(by_alias=True, exclude_unset=True, exclude_none=True)

        return await db_ref[self.__collection__].update_one({'_id': self.id}, {
            '$push': {
                self.__fields__[field].alias: value
            }
        })
