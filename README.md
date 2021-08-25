# byref

### Pass arguments by reference—in Python!

`byref`is a decorator that allows Python functions to declare reference parameters, with similar semantics to C++'s `T&` or C#'s `ref T`. Any modifications made within the function to these parameters will be picked up by the caller.

## Usage

```python
from byref import byref

@byref("x")
def add(x, y, /):
    x += y

a = 60
add(a, 40)
print(f"{a}!") # this prints 100!
```

## Motivation

I thought it would be funny.

## Implementation

For what looks like a simple feature, this is surprisingly difficult to implement (638 lines, at time of writing). See [CURSED.md](CURSED.md).

## Installation

Please see the releases section for prebuilt Python 3 wheels.

## License

[ISC License](https://choosealicense.com/licenses/isc/)