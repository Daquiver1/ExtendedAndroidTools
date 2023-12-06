# Copyright (c) Meta Platforms, Inc. and affiliates.

from textwrap import dedent
from projects.jdwp.codegen.types import python_type_for
import typing

from projects.jdwp.defs.schema import (
    Array,
    ArrayLength,
    Field,
    Struct,
    TaggedUnion,
    UnionTag,
)


StructLink = typing.Tuple[Struct, Field, Struct]


class StructGenerator:
    def __init__(self, root: Struct, name: str):
        self.__root = root
        self.__struct_to_name = compute_struct_names(root, name)

    def __get_python_type_for(self, struct: Struct, field: Field) -> str:
        type = field.type
        match type:
            case Struct():
                return self.__struct_to_name[type]
            case Array():
                array_type = typing.cast(Array, type)
                return f"typing.List[{self.__struct_to_name[array_type.element_type]}]"
            case TaggedUnion():
                tagged_union_type = typing.cast(TaggedUnion, type)
                union_types = [
                    self.__struct_to_name[case_struct]
                    for (_, case_struct) in tagged_union_type.cases
                ]
                union_types_str = ", ".join(union_types)
                return f"typing.Union[{union_types_str}]"
            case _:
                return python_type_for(type)

    def __is_explicit_field(self, field: Field) -> bool:
        return not isinstance(field.type, (ArrayLength, UnionTag))

    def __get_field_name(self, field: Field) -> str:
        words = field.name.split(" ")
        words = [words[0]] + [word.capitalize() for word in words[1:]]
        return "".join(words)

    def __generate_dataclass(self, struct: Struct) -> str:
        name = self.__struct_to_name[struct]
        fields_def = "\n".join(
            f"    {self.__get_field_name(field)}: {self.__get_python_type_for(struct, field)}"
            for field in struct.fields
            if self.__is_explicit_field(field)
        )
        class_def = f"@dataclasses.dataclass(frozen=True)\nclass {name}:\n{fields_def}"
        return dedent(class_def)

    def generate(self):
        return [
            self.__generate_dataclass(nested)
            for _, _, nested in reversed(list(nested_structs(self.__root)))
        ] + [self.__generate_dataclass(self.__root)]


def format_enum_name(enum_value):
    words = enum_value.name.split("_")
    formatted_name = "".join(word.capitalize() for word in words)
    return f"{formatted_name}Type"


def nested_structs(root: Struct) -> typing.Generator[StructLink, None, None]:
    for field in root.fields:
        field_type = field.type
        match field_type:
            case Array():
                array_type = typing.cast(Array, field_type)
                yield root, field, array_type.element_type
                yield from nested_structs(array_type.element_type)
            case TaggedUnion():
                tagged_union_type = typing.cast(TaggedUnion, field_type)
                for _, struct in tagged_union_type.cases:
                    yield root, field, struct
                    yield from nested_structs(struct)
            case Struct():
                yield root, field, field_type
                yield from nested_structs(field_type)


def compute_struct_names(root: Struct, name: str) -> typing.Mapping[Struct, str]:
    names = {root: name}
    for parent, field, nested in nested_structs(root):
        sanitized_field_name = "".join(
            word.capitalize() for word in field.name.split(" ")
        )
        type = field.type
        match type:
            case Struct():
                names[nested] = f"{names[parent]}{sanitized_field_name}"
            case Array():
                names[nested] = f"{names[parent]}{sanitized_field_name}Element"
            case TaggedUnion():
                tagged_union_type = typing.cast(TaggedUnion, type)
                for case_value, case_struct in tagged_union_type.cases:
                    case_name = format_enum_name(case_value)
                    names[
                        case_struct
                    ] = f"{names[parent]}{sanitized_field_name}Case{case_name}"
    return names
