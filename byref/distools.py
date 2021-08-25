from dataclasses import dataclass
from dis import hasjabs, opname
from inspect import stack
from types import CodeType

def make_opcodes_global():
	globals = stack()[1].frame.f_globals
	for code, name in enumerate(opname):
		globals[name] = code

make_opcodes_global()

@dataclass(repr=False, frozen=True)
class Op:
	code : int
	arg  : int
	
	def __repr__(self):
		return f"Op(code={opname[self.code]}, arg={self.arg})"

def assemble_single(op):
	if op.arg > 255:
		raise NotImplementedError("EXTENDED_ARG not supported")
	return bytes((op.code, op.arg))

def assemble_all(ops):
	return b"".join(assemble_single(op) for op in ops)

def op_at(cs, i):
	return Op(cs[i], cs[i + 1])

def iter_ops(cs):
	i = 0
	while i < len(cs):
		yield op_at(cs, i)
		i += 2

def inject_prologue_hook(cs, ops):
	new_cs = assemble_all(ops)
	off = len(ops) * 2
	
	for op in iter_ops(cs):
		if op.code in hasjabs:
			new_cs += assemble_single(Op(op.code, op.arg + off))
		else:
			new_cs += assemble_single(op)
	
	return new_cs

def make_code(code, **kwargs):
	copy_args = {
		"argcount": code.co_argcount,
		"posonlyargcount": code.co_posonlyargcount,
		"kwonlyargcount": code.co_kwonlyargcount,
		"nlocals": code.co_nlocals,
		"stacksize": code.co_stacksize,
		"flags": code.co_flags,
		"codestring": code.co_code,
		"constants": code.co_consts,
		"names": code.co_names,
		"varnames": code.co_varnames,
		"filename": code.co_filename,
		"name": code.co_name,
		"firstlineno": code.co_firstlineno,
		"lnotab": code.co_lnotab,
		"freevars": code.co_freevars,
		"cellvars": code.co_cellvars,
	}
	args = copy_args | kwargs
	return CodeType(*args.values())