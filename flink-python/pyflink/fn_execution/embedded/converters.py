################################################################################
#  Licensed to the Apache Software Foundation (ASF) under one
#  or more contributor license agreements.  See the NOTICE file
#  distributed with this work for additional information
#  regarding copyright ownership.  The ASF licenses this file
#  to you under the Apache License, Version 2.0 (the
#  "License"); you may not use this file except in compliance
#  with the License.  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
# limitations under the License.
################################################################################
from abc import ABC, abstractmethod

import pickle
from typing import TypeVar, List, Tuple

from pyflink.common import Row, RowKind

IN = TypeVar('IN')
OUT = TypeVar('OUT')


class DataConverter(ABC):

    @abstractmethod
    def to_internal(self, value) -> IN:
        pass

    @abstractmethod
    def to_external(self, value) -> OUT:
        pass

    def __eq__(self, other):
        return type(self) == type(other)


class IdentityDataConverter(DataConverter):
    def to_internal(self, value) -> IN:
        return value

    def to_external(self, value) -> OUT:
        return value


class PickleDataConverter(DataConverter):
    def to_internal(self, value) -> IN:
        if value is None:
            return None

        return pickle.loads(value)

    def to_external(self, value) -> OUT:
        if value is None:
            return None

        return pickle.dumps(value)


class FlattenRowDataConverter(DataConverter):
    def __init__(self, field_data_converters: List[DataConverter]):
        self._field_data_converters = field_data_converters

    def to_internal(self, value) -> IN:
        if value is None:
            return None

        return [self._field_data_converters[i].to_internal(item) for i, item in enumerate(value)]

    def to_external(self, value) -> OUT:
        if value is None:
            return None

        return [self._field_data_converters[i].to_external(item) for i, item in enumerate(value)]


class RowDataConverter(DataConverter):

    def __init__(self, field_data_converters: List[DataConverter], field_names: List[str]):
        self._field_data_converters = field_data_converters
        self._reuse_row = Row()
        self._reuse_external_row_data = [None for _ in range(len(field_data_converters))]
        self._reuse_external_row = [None, self._reuse_external_row_data]
        self._reuse_row.set_field_names(field_names)

    def to_internal(self, value) -> IN:
        if value is None:
            return None

        self._reuse_row._values = [self._field_data_converters[i].to_internal(item)
                                   for i, item in enumerate(value[1])]
        self._reuse_row.set_row_kind(RowKind(value[0]))

        return self._reuse_row

    def to_external(self, value: Row) -> OUT:
        if value is None:
            return None

        self._reuse_external_row[0] = value.get_row_kind().value
        values = value._values
        for i in range(len(values)):
            self._reuse_external_row_data[i] = self._field_data_converters[i].to_external(values[i])
        return self._reuse_external_row


class TupleDataConverter(DataConverter):

    def __init__(self, field_data_converters: List[DataConverter]):
        self._field_data_converters = field_data_converters

    def to_internal(self, value) -> IN:
        if value is None:
            return None

        return tuple([self._field_data_converters[i].to_internal(item)
                      for i, item in enumerate(value)])

    def to_external(self, value: Tuple) -> OUT:
        if value is None:
            return None

        return [self._field_data_converters[i].to_external(item)
                for i, item in enumerate(value)]


class ListDataConverter(DataConverter):

    def __init__(self, field_converter: DataConverter):
        self._field_converter = field_converter

    def to_internal(self, value) -> IN:
        if value is None:
            return None

        return [self._field_converter.to_internal(item) for item in value]

    def to_external(self, value) -> OUT:
        if value is None:
            return None

        return [self._field_converter.to_external(item) for item in value]


class DictDataConverter(DataConverter):
    def __init__(self, key_converter: DataConverter, value_converter: DataConverter):
        self._key_converter = key_converter
        self._value_converter = value_converter

    def to_internal(self, value) -> IN:
        if value is None:
            return None

        return {self._key_converter.to_internal(k): self._value_converter.to_internal(v)
                for k, v in value.items()}

    def to_external(self, value) -> OUT:
        if value is None:
            return None

        return {self._key_converter.to_external(k): self._value_converter.to_external(v)
                for k, v in value.items()}


def from_type_info_proto(type_info):
    # for data stream type information.
    from pyflink.fn_execution import flink_fn_execution_pb2

    type_info_name = flink_fn_execution_pb2.TypeInfo

    type_name = type_info.type_name
    if type_name == type_info_name.PICKLED_BYTES:
        return PickleDataConverter()
    elif type_name == type_info_name.ROW:
        return RowDataConverter(
            [from_type_info_proto(f.field_type) for f in type_info.row_type_info.fields],
            [f.field_name for f in type_info.row_type_info.fields])
    elif type_name == type_info_name.TUPLE:
        return TupleDataConverter(
            [from_type_info_proto(field_type)
             for field_type in type_info.tuple_type_info.field_types])
    elif type_name in (type_info_name.BASIC_ARRAY,
                       type_info_name.OBJECT_ARRAY,
                       type_info_name.LIST):
        return ListDataConverter(from_type_info_proto(type_info.collection_element_type))
    elif type_name == type_info_name.MAP:
        return DictDataConverter(from_type_info_proto(type_info.map_type_info.key_type),
                                 from_type_info_proto(type_info.map_type_info.value_type))

    return IdentityDataConverter()


def from_schema_proto(schema, one_arg_optimized=False):
    field_converters = [from_field_type_proto(f.type) for f in schema.fields]
    if one_arg_optimized and len(field_converters) == 1:
        return field_converters[0]
    else:
        return FlattenRowDataConverter(field_converters)


def from_field_type_proto(field_type):
    from pyflink.fn_execution import flink_fn_execution_pb2

    schema_type_name = flink_fn_execution_pb2.Schema

    type_name = field_type.type_name
    if type_name == schema_type_name.ROW:
        return RowDataConverter(
            [from_field_type_proto(f.type) for f in field_type.row_schema.fields],
            [f.name for f in field_type.row_schema.fields])
    elif type_name == schema_type_name.BASIC_ARRAY:
        return ListDataConverter(from_field_type_proto(field_type.collection_element_type))
    elif type_name == schema_type_name.MAP:
        return DictDataConverter(from_field_type_proto(field_type.map_info.key_type),
                                 from_field_type_proto(field_type.map_info.value_type))

    return IdentityDataConverter()
