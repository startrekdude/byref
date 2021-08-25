import ctypes
import sys
import warnings

from dataclasses import dataclass
from inspect import Parameter, signature, stack
from platform import python_implementation
from types import CellType, FunctionType

from .callsite import analyze_callsite, Attr, Lvalue, Rvalue, Subscr
from .distools import inject_prologue_hook, make_code, make_opcodes_global, Op

if sys.version_info[:2] < (3, 9):
	raise ImportError("byref does not work on versions of Python prior to 3.9")

if sys.version_info[:2] > (3, 9) or python_implementation() != "CPython":
	warnings.warn("byref has not been tested with this version of Python, and may not work correctly")

make_opcodes_global()

@dataclass(frozen=True)
class PosWriteback:
	src : str
	dst : int

@dataclass(frozen=True)
class LvalueWriteback:
	src : str
	dst : Lvalue

def analyze_writeback(f, refs):
	sig = signature(f)
	args = tuple(p.name for p in sig.parameters.values()
		if p.kind == Parameter.POSITIONAL_ONLY and p.default == Parameter.empty)
	
	writeback = []
	for ref in refs:
		if ref not in args:
			raise ValueError(f'Parameter "{ref}" is not eligible to be passed by reference' +
				f'—must be a positional-only argument with no default value')
		writeback.append(PosWriteback(ref, args.index(ref)))
	
	return tuple(writeback)

def writeback(frame):
	ctypes.pythonapi.PyFrame_LocalsToFast(ctypes.py_object(frame), ctypes.c_int(0))

def byref_call_hook():
	frames = stack()
	
	f_frame = frames[1].frame
	wrapped_frame = frames[2].frame
	caller_frame = frames[3].frame
	wrapped_locals = wrapped_frame.f_locals
	
	pos_writebacks = wrapped_locals["pos_writebacks"]
	args = analyze_callsite(caller_frame)
	
	lvalue_writebacks = []
	for pos_writeback in pos_writebacks:
		if pos_writeback.dst >= len(args):
			raise ValueError(f"Argument {pos_writeback.dst} is an rvalue; expected lvalue")
		
		arg = args[pos_writeback.dst]
		if isinstance(arg, Rvalue):
			raise ValueError(f"Argument {pos_writeback.dst} is an rvalue; expected lvalue")
		lvalue_writebacks.append(LvalueWriteback(pos_writeback.src, arg))
	
	wrapped_locals["f_frame"] = f_frame
	wrapped_locals["lvalue_writebacks"] = lvalue_writebacks
	writeback(wrapped_frame)

def inject_call_hook(f, hook):
	cell = CellType(hook)
	closure = f.__closure__
	
	if closure and len(closure) >= 255:
		raise ValueError("Unable to inject call hook, closure too large")
	
	if closure:
		new_closure = closure + (cell,)
	else:
		new_closure = (cell,)
	
	code = f.__code__
	new_freevars = code.co_freevars + ("_DO_NOT_USE_call_hook",)
	hook_idx = len(new_closure) - 1
	
	new_code = make_code(code, lnotab=b'', freevars=new_freevars,
		codestring=inject_prologue_hook(code.co_code, (
			Op(LOAD_DEREF, hook_idx),
			Op(CALL_FUNCTION, 0),
			Op(POP_TOP, 0),
		))
	)
	
	new_f = FunctionType(new_code, f.__globals__, name=f.__name__, closure=new_closure)
	new_f.__defaults__ = f.__defaults__
	new_f.__kwdefaults__ = f.__kwdefaults__
	
	return new_f

def write_lvalue(frame, lvalue, val):
	attrs = lvalue.attrs
	
	if len(attrs) == 0:
		if lvalue.is_global:
			frame.f_globals[lvalue.name] = val
		else:
			frame.f_locals[lvalue.name] = val
		return
		
	if lvalue.is_global:
		ref = frame.f_globals[lvalue.name]
	else:
		ref = frame.f_locals[lvalue.name]
	
	while len(attrs) > 1:
		attr = attrs.pop(0)
		if isinstance(attr, Subscr):
			ref = ref[attr.arg]
		elif isinstance(attr, Attr):
			ref = getattr(ref, attr.name)
		else:
			assert False
	
	attr = attrs.pop(0)
	if isinstance(attr, Subscr):
		ref[attr.arg] = val
	elif isinstance(attr, Attr):
		setattr(ref, attr.name, val)
	else:
		assert False

def byref(*refs):
	def wrapper(f):
		pos_writebacks_ = analyze_writeback(f, refs)
		f = inject_call_hook(f, byref_call_hook)
		
		def wrapped(*args, **kwargs):
			pos_writebacks = pos_writebacks_
			f_frame = None
			lvalue_writebacks = None
			
			result = f(*args, **kwargs)
			
			caller_frame = stack()[1].frame
			f_locals = f_frame.f_locals
			
			for lvalue_writeback in lvalue_writebacks:
				write_lvalue(caller_frame, lvalue_writeback.dst, f_locals[lvalue_writeback.src])
			
			writeback(caller_frame)
			
			return result
		
		return wrapped
	return wrapper