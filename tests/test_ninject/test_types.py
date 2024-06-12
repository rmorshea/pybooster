import pytest

from ninject.types import Dependency, dependencies


def test_dependency_annotation():
    with pytest.raises(TypeError, match="Expected exactly two arguments"):
        Dependency[int, "my_int", "something else"]


def test_dependencies_must_be_a_typed_dict():
    with pytest.raises(TypeError, match=r"Expected .* to be a TypedDict"):

        @dependencies
        class NotTypedDict:
            pass
