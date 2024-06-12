# Ninject

[![PyPI - Version](https://img.shields.io/pypi/v/ninject.svg)](https://pypi.org/project/ninject)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/ninject.svg)](https://pypi.org/project/ninject)

Ninject uses modern Python features to provide a simple and performant dependency
injection framework.

-   [Installation](#installation)
-   [License](#license)

## Installation

```console
pip install ninject
```

## Usage

First declare a `Dependency` and `inject` it into a function.

```python
from ninject import Dependency, inject

# declare a dependency
Message = Dependency[str, "Message"]

@inject
def print_message(*, message: Message = inject.ed):
    print(message)
```

Next, define a `Context` with a function that `provides` the `Dependency`.

```python
from ninject import Context

context = Context()

@context.provides(Message)
def provide_message() -> str:
    return "Hello, World!"
```

Finally, establish the `context` and call the function with the `inject.ed` dependency:

```python
with context:
    print_message()
```

The output will be:

```text
Hello, World!
```

## License

`ninject` is distributed under the terms of the
[MIT](https://spdx.org/licenses/MIT.html) license.
