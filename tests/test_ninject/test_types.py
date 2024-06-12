import pytest

from ninject.types import Dependency


def test_dependency_annotation():
    with pytest.raises(TypeError, match="Expected exactly two arguments"):
        Dependency[int, "my_int", "something else"]
