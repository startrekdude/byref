# byref Implementation Notes

(this will likely be hard to follow without a strong background in (C)Python's internals)

Usual warning: this is not remotely a replacement for the source code and doesn't include, or attempt to include, the same information. Please read the source; it's interesting, if you like that kind of stuff.

I'm not much for TDD, but let's start with a test case anyways. This is what I'm trying to get working.

```python
from byref import byref

@byref("x")
def add(x, y, /):
    x += y

a = 60
add(a, 40)
assert a == 100
```

Breaking it down, my decorator has to:

1. Take the values of the local variables corresponding to the reference parameters after the execution of the wrapped function (the "Easy Part")
2. Put those values into the local/global variables that the function was called with as arguments. And presumably error if the caller puts a constant or something else there (`x = 40`, not `40 = x`). (the "Hard Part")

## Capturing Local Variables

This is the easier part. I can get a copy of the stack frames with `inspect.stack()` and read local variables from `.f_locals`, like so:

```python
from inspect import stack

def read_caller_locals():
    caller = stack()[1].frame
    print(caller.f_locals)

def main():
    secret_key = "hunter2"
    read_caller_locals()

main()
```

Small problem. Quick reminder on how decorators work:

```python
def log_calls(f):
    def wrapped(*args, **kwargs):
        print(f"About to call {f}.")
        result = f(*args, **kwargs)
        print(f"Returned from {f}")
        return result
    return wrapped

@log_calls
def say_hello_to(name):
    print(f"Hello, {name.title()}!")
```

From within `wrapped`, I can't get `f`'s stack frame because it either doesn't exist yet (before call) or has been destroyed (after call). I can only get a reference to stack frames above me in the stack (`f` would need to call me, in other words).

So let's make that happen. I rewrite `f`'s bytecode to first call a hook function to capture its stack frame, then continue with `f`'s normal execution, updating jump offsets as required. (I *promise* I didn't mix it up earlier, this is the Easy Part). Where should the injected bytecode get a reference to the hook function from? I just stuck it in the closure. This probably makes me the first person ever to use `types.CellType`'s constructor ([search](https://www.google.com/search?q=%22CellType%22+and+%22from+types%22+or+%22import+types%22+site%3Agithub.com+inurl%3Apy)).

The code for this is mostly in `byref.py` with some helper functions in `distools.py`.

### What to do with the captured frame?

Alright, so, I've captured `f`'s stack frame. Minor problem: I've done it at the *start* of `f`'s execution, not the *end*, meaning that the values I need aren't available yet. Going back to my test case: I have the `x` before the `x += y`. Rewriting `f`'s bytecode to insert calls to my frame-grabbing hook function before every return operation sounds really annoying, though. Is there any way I can avoid that?

Actually, yeah, that was super easy, barely an inconvenience. Turns out that once you have a reference to a frame, it'll actually update it's `.f_locals` as execution continues. Example:

```python
from inspect import stack

captured_frame = None

def capture_frame():
    global captured_frame
    captured_frame = stack()[1].frame

def do_something():
    capture_frame()
    acc = 0
    for x in range(1, 101):
        acc += x

do_something()
print(captured_frame.f_locals["acc"]) # 5050
```

So now I just need to store `f`'s frame somewhere where I can do something with it after it returns. Why not `wrapped`'s locals? I can get a reference to it easy enough by reaching 2 up in the stack from the hook function, instead of just 1. Then `wrapped` can handle getting the values where they need to go when `f` returns.

Minor caveat, writing a frame's local variables needs one extra magic spell:

```python
import ctypes

ctypes.pythonapi.PyFrame_LocalsToFast(ctypes.py_object(frame), ctypes.c_int(0))
```

So. `f`'s just returned, and we have the values that the reference parameters should be set to. 

## The Hard Part: Picking which of the caller's variables to set

Going back to my test case, look at `add(a, 40)`. It's pretty clear that the right thing to do here is set (the caller's) a to `100`. What about `add(60, 40)`? Probably error...

What about `more_complicated_example(a if b > 7 else c + 2, (lambda a, b: 40//a + (4 < b < 12))(40, x), an_actual_lvalue_here, [c ^ k for c, k in zip(msg, key) if c ^ k != 0], *(x + 2 for x in range(5)), **(defaults | custom))`? K now do it programmatically. From bytecode (specifically, the frame's `f_lasti` points to the function call). Deep breaths...

(it really is amazing how much syntax you can put between function call parens)

First, I'm going to define two terms. An **lvalue** is an expression that can appear on the left side of the assignment operator. An **rvalue** is an expression that can appear on the right side of the assignment operator.

You can have `a = 40` but not `40 = a`. All lvalues are rvalues but the reverse is not true.

Next, I'm going to define my problem. I need to, programmatically and from bytecode (not source or AST), determine which of the arguments to a function call are lvalues and which are rvalues.

Quick tangent. Should I accept `a.some_attribute` as an lvalue? I can set it, so, sure. What about `a[0]`? Yeah that's reasonable. What about `a[i]`? Well, that opens the door to `a[i + 2]` and `a[x()]`, so no. I decided to limit subscript to constants.

To solve this, I simulate running the Python bytecode machine in reverse, taking note of which values are pushed and popped. Where multiple paths could have been taken, I follow all of them, and if they disagree on the source of an argument, force it to be an rvalue. It's probably some of the most insane code I've written, available in `callsite.py`. I'm not going to describe it here, as further encouragement for you to go read the code.

