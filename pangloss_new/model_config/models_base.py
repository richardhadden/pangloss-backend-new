from __future__ import annotations

import dataclasses
import typing
import uuid
from collections import ChainMap

import annotated_types
import humps
from pydantic import AnyHttpUrl, BaseModel, ConfigDict
from pydantic_extra_types.ulid import ULID

if typing.TYPE_CHECKING:
    from pangloss_new.model_config.field_definitions import ModelFieldDefinitions

STANDARD_MODEL_CONFIG: ConfigDict = {
    "alias_generator": humps.camelize,
    "populate_by_name": True,
    "use_enum_values": True,
    "arbitrary_types_allowed": True,
}


class EdgeModel(BaseModel):
    show_in_reverse_relation: typing.ClassVar[bool] = False
    model_config = STANDARD_MODEL_CONFIG

    __pg_annotations__: typing.ClassVar[ChainMap[str, type]]
    __pg_field_definitions__: typing.ClassVar["ModelFieldDefinitions"]

    @classmethod
    def __pydantic_init_subclass__(cls) -> None:
        from pangloss_new.model_config.model_manager import ModelManager

        ModelManager.register_edge_model(cls)


class _OwnsMethods:
    """Adds methods to check whether a model has attribute
    set on itself, not in inheritance chain, by inspecting cls.__dict__"""

    @classmethod
    def has_own(cls, key: str) -> bool:
        if key in cls.__dict__:
            return True
        return False

    @classmethod
    def get_own(cls, key: str) -> typing.Any:
        return cls.__dict__.get(key, None)


class _BaseClassProxy:
    __pg_base_class__: typing.ClassVar[type[RootNode] | type[ReifiedRelation]]

    @property
    def __pg_field_definitions__(self):
        return self.__pg_base_class__.__pg_field_definitions__


@dataclasses.dataclass
class BaseMeta:
    """Base class for BaseNode Meta fields"""

    base_model: type["RootNode"]

    abstract: bool = False
    """The model is an abstract model"""
    create: bool = True
    """Model can be directly created"""
    edit: bool = True
    """Model can be directly edited"""
    delete: bool = True
    """Model can be directly deleted"""
    view: bool = True
    """Model can be directly viewed"""
    search: bool = True
    """Model can be directly searched"""

    create_by_reference: bool = False
    "Allow creation by reference by providing a URI/ULID and a label"

    label_field: str | None = None
    """Alternative field to be displayed as label"""

    @property
    def fields(self):
        return self.base_model.__pg_field_definitions__


class RootNode(_OwnsMethods):
    """Base class for basic BaseModel"""

    type: str

    Create: typing.ClassVar[type[CreateBase]]
    HeadView: typing.ClassVar[type[HeadViewBase]]
    View: typing.ClassVar[type[ViewBase]]
    EditHeadView: typing.ClassVar[type[EditHeadViewBase]]
    EditView: typing.ClassVar[type[EditViewBase]]
    EditSet: typing.ClassVar[type[EditSetBase]]
    ReferenceCreate: typing.ClassVar[type[ReferenceCreateBase]] | None = None
    ReferenceView: typing.ClassVar[type[ReferenceViewBase]]
    ReferenceSet: typing.ClassVar[type[ReferenceSetBase]]
    EmbeddedCreate: typing.ClassVar[type[EmbeddedCreateBase]]
    EmbeddedView: typing.ClassVar[type[EmbeddedViewBase]]
    EmbeddedSet: typing.ClassVar[type[EmbeddedSetBase]]

    Meta: typing.ClassVar[type[BaseMeta]] = BaseMeta
    _meta: typing.ClassVar[BaseMeta]

    __pg_annotations__: typing.ClassVar[ChainMap[str, type]]
    __pg_field_definitions__: typing.ClassVar["ModelFieldDefinitions"]

    class edit:
        __pg_base_class__: typing.ClassVar[type[RootNode]]

        @classmethod
        def get(cls, uuid: uuid.UUID | AnyHttpUrl) -> EditHeadViewBase:
            # TODO: Sketching API so far
            return cls.__pg_base_class__.EditHeadView()

        def __new__(cls, *args, **kwargs) -> EditSetBase:
            # TODO: Sketching API so far
            return cls.__pg_base_class__.EditSet(*args, **kwargs)

    class view:
        __pg_base_class__: typing.ClassVar[type[RootNode]]

        @classmethod
        def get(cls, id: uuid.UUID | AnyHttpUrl):
            # TODO: Sketching API so far
            return cls.__pg_base_class__.HeadView()

    def __init_subclass__(cls):
        from pangloss_new.model_config.model_manager import ModelManager

        ModelManager.register_base_model(cls)

    def __new__(cls, *args, **kwargs):
        return cls.Create(*args, **kwargs)


class CreateBase(BaseModel, _BaseClassProxy):
    # id: Can take an optional ID or URI

    id: ULID | AnyHttpUrl | None = None
    label: str


class EditViewBase(BaseModel):
    """Base model returned by API for editing"""

    pass


class EditHeadViewBase(EditViewBase):
    """Head Base model returned by API for editing (contains additional metadata)"""

    pass


class EditSetBase(BaseModel):
    """Base model for updates Post-ed to API"""


class ViewBase(BaseModel):
    """Base model returned by API for viewing; contains all fields"""

    type: str
    id: uuid.UUID
    label: str


class HeadViewBase(ViewBase):
    """Base model returned by API for viewing; includes reverse relatinos and additional metadata"""

    type: str
    id: uuid.UUID


class ReferenceViewBase(BaseModel, _BaseClassProxy):
    """Base model for viewing a Reference to an entity"""

    type: str
    id: ULID
    label: str


class ReferenceCreateBase(BaseModel, _BaseClassProxy):
    """Base model for setting a Reference to an entity"""

    type: str
    id: ULID | AnyHttpUrl
    label: str


class ReferenceSetBase(BaseModel, _BaseClassProxy):
    """Base model for setting a Reference to an entity"""

    type: str
    id: ULID | AnyHttpUrl


class ReifiedCreateBase(BaseModel, _BaseClassProxy):
    pass


@dataclasses.dataclass
class ReifiedMeta:
    base_model: type["ReifiedBase"]

    @property
    def fields(self) -> ModelFieldDefinitions:
        return self.base_model.__pg_get_fields__()


class ReifiedBase(BaseModel, _OwnsMethods):
    model_config = {"arbitrary_types_allowed": True}

    Create: typing.ClassVar[type[ReifiedCreateBase]]

    __pg_annotations__: typing.ClassVar[ChainMap[str, type]]
    __pg_field_definitions__: typing.ClassVar["ModelFieldDefinitions"]
    __pg_bound_field_definitions__: typing.ClassVar["ModelFieldDefinitions"]

    _meta: typing.ClassVar[ReifiedMeta]

    @classmethod
    def __pydantic_init_subclass__(cls):
        """Create a _meta object with pointer back to this class,
        either the generic type or the bound type"""
        cls._meta = ReifiedMeta(base_model=cls)

    @classmethod
    def __pg_get_fields__(cls) -> ModelFieldDefinitions:
        """Internal getter for reified relation fields to present a consistent API
        and avoid potentially accidentally omitting logic in other spots.

        If it is a generic class, return __pg_field_definitions__;
        if bound (i.e. has origin and args set in __pydantic_generic_metadata,
        check whether the bound field definitions have been created and return, or just return"""
        if (
            cls.__pydantic_generic_metadata__["origin"]
            and cls.__pydantic_generic_metadata__["args"]
        ):
            if not getattr(cls, "__pg_bound_field_definitions__", None):
                from pangloss_new.model_config.model_setup_functions.build_pg_model_definition import (
                    build_pg_bound_model_definition_for_instatiated_reified,
                )

                build_pg_bound_model_definition_for_instatiated_reified(
                    typing.cast(type[ReifiedRelation], cls)
                )
            return cls.__pg_bound_field_definitions__
        return cls.__pg_field_definitions__


class ReifiedRelation[T](ReifiedBase):
    """Base model for creating a reified relation"""

    type: str
    target: typing.Annotated[T, RelationConfig(reverse_name="is_target_of")]

    def __init_subclass__(cls) -> None:
        from pangloss_new.model_config.model_manager import ModelManager

        # Dubious hack to update the parameters used by typing module to allow
        # inheriting class to include additional type parameters
        cls.__parameters__ = cls.__type_params__

        ModelManager.register_reified_relation_model(cls)


class ReifiedRelationViewBase(BaseModel):
    """Base model for viewing a reified relation (contains uuid and additional metadata)"""

    type: str
    uuid: uuid.UUID
    head_uuid: typing.Optional[uuid.UUID] = None
    head_type: typing.Optional[str] = None


class Embedded[T]:
    embedded_type: T


class EmbeddedCreateBase(BaseModel):
    """Base model for creating an embedded node (same as RootNode without id)"""

    type: str


class EmbeddedViewBase(BaseModel):
    """Base model for viewing an embedded model"""

    type: str
    uuid: uuid.UUID
    head_uuid: typing.Optional[uuid.UUID] = None
    head_type: typing.Optional[str] = None


class EmbeddedSetBase(BaseModel):
    type: str
    uuid: uuid.UUID


class Trait:
    pass


class HeritableTrait(Trait):
    pass


class NonHeritableTrait(Trait):
    pass


class MultiKeyField[T](BaseModel):
    """Define a field with multiple additional fields.

    The main field type is supplied by the type param T and is assigned to the `value` field.
    Additional fields may be defined on the subclassed model."""

    value: T

    __pg_field_definitions__: typing.ClassVar["ModelFieldDefinitions"]


@dataclasses.dataclass
class RelationConfig:
    reverse_name: str
    subclasses_relation: typing.Optional[list[str] | frozenset[str]] = None
    edge_model: typing.Optional[type["EdgeModel"]] = None
    validators: list[annotated_types.BaseMetadata] = dataclasses.field(
        default_factory=list
    )

    create_inline: bool = False
    edit_inline: bool = False
    delete_related_on_detach: bool = False
    default_type: typing.Optional[str] = None

    def __hash__(self):
        if self.subclasses_relation:
            self.subclasses_relation = frozenset(self.subclasses_relation)
        return hash(self.__dict__)

    def __post_init__(self):
        self.reverse_name = self.reverse_name.lower().replace(" ", "_")
