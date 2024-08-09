from collections.abc import Mapping
from typing import Any, get_args, get_origin

import ninject
from ninject._dependency import (
    AsyncDependencyContext,
    DependencyContextProvider,
    SyncDependencyContext,
    add_dependency_type,
    get_dependency_name,
    get_dependency_value_var,
    setdefault_dependency_value_var,
)
from ninject._inspect import (
    INJECTED,
    AsyncProviderInfo,
    ProviderInfo,
    SyncProviderInfo,
    get_injected_dependency_types_from_callable,
    get_provider_info,
)
from ninject.types import AsyncFunctionProvider, SyncFunctionProvider


def make_context_providers(
    info: ProviderInfo,
    dependencies: Mapping[str, type] | None,
) -> Mapping[type, DependencyContextProvider]:
    if get_origin(info.provided_type) is tuple:
        return _make_tuple_context_providers(info, dependencies)
    else:
        return {info.provided_type: _make_single_context_provider(info, dependencies)}


def _make_tuple_context_providers(
    info: ProviderInfo,
    dependencies: Mapping[str, type] | None,
) -> dict[type, DependencyContextProvider]:
    is_sync = isinstance(info, SyncProviderInfo)

    tuple_type = info.provided_type
    tuple_item_types = get_args(tuple_type)

    tuple_type_name = ",".join(get_dependency_name(tp) for tp in tuple_item_types)
    add_dependency_type(tuple_type_name, tuple_type)

    providers: dict[type, DependencyContextProvider] = {tuple_type: _make_single_context_provider(info, dependencies)}

    for index, item_type in enumerate(tuple_item_types):
        item_dependencies = {"value": tuple_type}
        item_function_provider = _make_item_function_provider(index, tuple_type, is_sync=is_sync)
        item_info = get_provider_info(item_function_provider, provides_type=item_type)
        providers[item_type] = _make_single_context_provider(item_info, dependencies=item_dependencies)

    return providers


def _make_single_context_provider(
    info: ProviderInfo,
    dependencies: Mapping[str, type] | None,
) -> DependencyContextProvider:
    provider = info.provider
    provided_var = setdefault_dependency_value_var(info.provided_type)
    if dependencies is None:
        dependencies = get_injected_dependency_types_from_callable(provider)
    dependency_context_type = AsyncDependencyContext if isinstance(info, AsyncProviderInfo) else SyncDependencyContext
    dependency_types = tuple(dependencies.values())
    return lambda: dependency_context_type(provider, provided_var, dependency_types)


def _make_item_function_provider(
    item: int, value_type: type, *, is_sync: bool, from_obj: bool = False
) -> SyncFunctionProvider | AsyncFunctionProvider:
    if from_obj:
        if not isinstance(item, str):  # nocov
            msg = f"Expected field to be a string, got {item}"
            raise TypeError(msg)

        if is_sync:

            def sync_provide_attr_field(*, value=INJECTED) -> Any:
                return getattr(value, item)

            sync_provide_attr_field.__annotations__["value"] = value_type

            return sync_provide_attr_field

        else:

            async def async_provide_attr_field(*, value=INJECTED) -> Any:
                return getattr(value, item)

            async_provide_attr_field.__annotations__["value"] = value_type

            return async_provide_attr_field

    elif is_sync:

        def sync_provide_item_field(*, value=INJECTED) -> Any:
            return value[item]

        sync_provide_item_field.__annotations__["value"] = value_type

        return sync_provide_item_field

    else:

        async def async_provide_item_field(*, value=INJECTED) -> Any:
            return value[item]

        async_provide_item_field.__annotations__["value"] = value_type

        return async_provide_item_field
