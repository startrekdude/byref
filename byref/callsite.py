from collections import defaultdict
from copy import copy
from dataclasses import dataclass
from dis import opname
from typing import Any

from .distools import make_opcodes_global, Op, op_at

make_opcodes_global()

def analyze_control_flow(cs):
	prev = defaultdict(list)
	
	i = 0
	while i < len(cs):
		op = op_at(cs, i)
		
		if op.code == EXTENDED_ARG:
			raise NotImplementedError("Unable to analyze callsite; EXTENDED_ARG not supported")
		
		if op.code in (JUMP_ABSOLUTE, JUMP_IF_FALSE_OR_POP, JUMP_IF_TRUE_OR_POP,
			POP_JUMP_IF_FALSE, POP_JUMP_IF_TRUE, JUMP_IF_NOT_EXC_MATCH):
			prev[op.arg].append(i)
		elif op.code in (JUMP_FORWARD, FOR_ITER, SETUP_FINALLY, SETUP_WITH, SETUP_ASYNC_WITH):
			prev[i + 2 + op.arg].append(i)
		
		if op.code not in (JUMP_ABSOLUTE, JUMP_FORWARD):
			prev[i + 2].append(i)
		i += 2
	
	return prev

def combine_stacks(stacks):
	result = []
	first_stack, *stacks = stacks
	
	for i, value in enumerate(first_stack):
		for stack in stacks:
			if stack[i] != value:
				result.append(Rvalue())
				break
		else:
			result.append(value)
	
	return result

def analyze_callsite(frame):
	code = frame.f_code
	cs = code.co_code
	prev = analyze_control_flow(cs)
	
	tracers = []
	lasti = frame.f_lasti
	call_op = op_at(cs, lasti)
	
	if call_op.code == DICT_MERGE: # what even, python.
		lasti += 2
		call_op = op_at(cs, lasti)
	
	if call_op.code == CALL_FUNCTION:
		for prev_i in prev[lasti]:
			tracers.append(Tracer(TracerState(call_op.arg, code), prev_i, lasti))
	elif call_op.code == CALL_FUNCTION_KW:
		for prev_i in prev[lasti]:
			tracers.append(Tracer(TracerState(call_op.arg + 1, code), prev_i, lasti))
	elif call_op.code == CALL_FUNCTION_EX:
		for prev_i in prev[lasti]:
			tracers.append(Tracer(TracerState(1 + (call_op.arg & 1 == 1), code, is_cfex=True), prev_i, lasti))
	else:
		raise ValueError("Unable to analyze callsite; not a function call operator")
	
	stacks = []
	
	while tracers:
		for i in range(len(tracers) - 1, -1, -1):
			tracer = tracers[i]
			prev_i = tracer.next_i
			op = op_at(cs, prev_i)
			
			if op.code in (JUMP_IF_FALSE_OR_POP, JUMP_IF_TRUE_OR_POP):
				jumped = tracer.next_i != tracer.prev_i - 2
				if jumped:
					op = Op(NOP, 0)
				else:
					op = Op(POP_TOP, 0)
			
			tracer.state.trace_op(op)		
			
			if tracer.state.stack_size == 0:
				tracer.state.stack.reverse()
				if not tracer.state.is_cfex:
					stacks.append(tracer.state.stack)
				else:
					stacks.append([])
				del tracers[i]
				continue
			
			first_prev, *branches = prev[tracer.next_i]
			tracer.next_i = first_prev
			tracer.prev_i = prev_i
			for branch in branches:
				new_tracer = Tracer(tracer.state.copy(), branch, prev_i)
				tracers.append(new_tracer)
	
	return combine_stacks(stacks)
			
ACTION_SPECIAL_HANDLING = (
	LOAD_CONST,
	LOAD_NAME,
	LOAD_GLOBAL,
	LOAD_FAST,
	LOAD_DEREF,
	LOAD_CLASSDEREF,
	CALL_FUNCTION,
	CALL_FUNCTION_KW,
	CALL_FUNCTION_EX,
	FORMAT_VALUE,
	BINARY_SUBSCR,
	LOAD_ATTR,
	MAKE_FUNCTION,
	DUP_TOP,
	DUP_TOP_TWO,
	ROT_TWO,
	ROT_THREE,
	ROT_FOUR,
	UNPACK_SEQUENCE,
	BUILD_MAP,
	LOAD_METHOD,
	CALL_METHOD,
	BUILD_CONST_KEY_MAP,
	JUMP_IF_FALSE_OR_POP,
	JUMP_IF_TRUE_OR_POP,
	LIST_TO_TUPLE,
	LIST_EXTEND,
)

ACTION_PUSH_RVALUE_POP_ARG = (
	BUILD_TUPLE,
	BUILD_LIST,
	BUILD_SET,
	BUILD_SLICE,
	BUILD_STRING,
)

ACTION_DO_NOTHING = (
	JUMP_FORWARD,
	JUMP_ABSOLUTE,
	NOP,
	SETUP_ANNOTATIONS,
	DELETE_NAME,
	DELETE_GLOBAL,
	DELETE_FAST,
	DELETE_DEREF,
)

ACTION_POP = (
	POP_JUMP_IF_FALSE,
	POP_JUMP_IF_TRUE,
	STORE_NAME,
	STORE_GLOBAL,
	STORE_FAST,
	STORE_DEREF,
	POP_TOP,
	PRINT_EXPR,
	DELETE_ATTR,
)

ACTION_POP_TWO = (
	DELETE_SUBSCR,
	STORE_ATTR,
)

ACTION_POP_THREE = (
	STORE_SUBSCR,
)

ACTION_PUSH_RVALUE = (
	LOAD_CONST,
	GET_ANEXT,
	LOAD_BUILD_CLASS,
	LOAD_ASSERTION_ERROR,
)

ACTION_PUSH_RVALUE_POP = (
	GET_ITER,
	GET_AITER,
	GET_YIELD_FROM_ITER,
	GET_AWAITABLE,
	LIST_TO_TUPLE,
	UNARY_POSITIVE,
	UNARY_NEGATIVE,
	UNARY_NOT,
	UNARY_INVERT,
)

ACTION_PUSH_RVALUE_POP_TWO = (
	COMPARE_OP,
	IS_OP,
	CONTAINS_OP,
	BINARY_ADD,
	BINARY_POWER,
	BINARY_MULTIPLY,
	BINARY_MODULO,
	BINARY_SUBTRACT,
	BINARY_FLOOR_DIVIDE,
	BINARY_TRUE_DIVIDE,
	BINARY_LSHIFT,
	BINARY_RSHIFT,
	BINARY_AND,
	BINARY_XOR,
	BINARY_OR,
	BINARY_MATRIX_MULTIPLY,
	INPLACE_MATRIX_MULTIPLY,
	INPLACE_FLOOR_DIVIDE,
	INPLACE_TRUE_DIVIDE,
	INPLACE_ADD,
	INPLACE_SUBTRACT,
	INPLACE_MULTIPLY,
	INPLACE_MODULO,
	INPLACE_POWER,
	INPLACE_LSHIFT,
	INPLACE_RSHIFT,
	INPLACE_AND,
	INPLACE_XOR,
	INPLACE_OR,
	JUMP_IF_NOT_EXC_MATCH,
	DICT_MERGE,
	DICT_UPDATE,
	LIST_APPEND,
	SET_ADD,
	LIST_EXTEND,
	SET_UPDATE,
)

ACTION_PUSH_RVALUE_POP_THREE = (
	MAP_ADD,
)

ACTION_PANIC = (
	RERAISE,
	WITH_EXCEPT_START,
	BEFORE_ASYNC_WITH,
	END_ASYNC_FOR,
	YIELD_FROM,
	YIELD_VALUE,
	RETURN_VALUE,
	IMPORT_STAR,
	POP_BLOCK,
	POP_EXCEPT,
	FOR_ITER,
	UNPACK_EX,
	IMPORT_NAME,
	IMPORT_FROM,
	SETUP_FINALLY,
	RAISE_VARARGS,
	LOAD_CLOSURE,
	SETUP_WITH,
	EXTENDED_ARG,
	SETUP_ASYNC_WITH,
)

@dataclass(frozen=True)
class Rvalue:
	pass

@dataclass(frozen=True)
class Subscr:
	arg : Any

@dataclass(frozen=True)
class Attr:
	name : str

@dataclass(frozen=True)
class Lvalue:
	name : str
	is_global : bool
	attrs : list

class TracerState:
	def __init__(self, stack_size, code, is_cfex=False):
		self.stack = []
		self.stack_size = stack_size
		self.is_cfex = is_cfex
		self.cfex_seq_position = 0
		self.descent = 0
		self.load_subscr = False
		self.attrs = []
		self.pending = []
		self.code = code
	
	def copy(self):
		new = TracerState(self.stack_size, self.code)
		new.stack = copy(self.stack)
		new.descent = self.descent
		new.load_subscr = self.load_subscr
		new.attrs = copy(self.attrs)
		new.pending = copy(self.pending)
		new.is_cfex = self.is_cfex
		new.cfex_seq_position = self.cfex_seq_position
		return new
	
	def push(self, val):
		if self.pending:
			pending_op = self.pending[-1]
			if self.descent == pending_op.descent:
				pending_op.push(val)
				if pending_op.stack_size == 0:
					del self.pending[-1]
					pending_op.complete(self)
				return
		
		if self.descent == 0:
			self.stack.append(val)
			self.stack_size -= 1
		else:
			self.descent -= 1
	
	def push_rvalue(self):
		self.attrs = []
		self.push(Rvalue())
	
	def push_lvalue(self, name, is_global):
		self.attrs.reverse()
		val = Lvalue(name, is_global, self.attrs)
		self.attrs = []
		self.push(val)
	
	def pop(self, count):
		self.descent += count
	
	def try_apply_cfex_op(self, op):
		if self.stack_size != 1 or self.descent != 0:
			return False
		
		if self.cfex_seq_position == 0:
			return op.code == LIST_TO_TUPLE
		elif self.cfex_seq_position == 1:
			return op.code == LIST_EXTEND
		elif self.cfex_seq_position == 2:
			return op.code in (LOAD_FAST, LOAD_GLOBAL, LOAD_DEREF, LOAD_NAME, LOAD_CLASSDEREF, LOAD_CLOSURE)
		elif self.cfex_seq_position == 3:
			match = op.code == BUILD_LIST
			if match:
				self.is_cfex = False
				self.stack_size = op.arg
				self.stack = []
				return True
			return False
	
	def undo_cfex_op(self):
		self.is_cfex = False
		
		if self.cfex_seq_position >= 1:
			self.trace_op(Op(LIST_TO_TUPLE, 0))
		if self.cfex_seq_position >= 2:
			self.trace_op(Op(LIST_EXTEND, 0))
		if self.cfex_seq_position >= 3:
			self.push_rvalue()
		
		self.is_cfex = True
		self.cfex_seq_position = 0
	
	def handle_cfex_processing(self, op):
		if self.stack_size == 1 and self.descent == 0 and op.code == BUILD_TUPLE:
			self.is_cfex = False
			self.stack_size = op.arg
			self.stack = []
			return True
		
		if self.try_apply_cfex_op(op):
			self.cfex_seq_position += 1
			return True
		else:
			self.undo_cfex_op()
			return False
	
	def trace_op(self, op):
		if self.is_cfex and self.handle_cfex_processing(op):
			return
		
		if self.load_subscr:
			self.load_subscr = False
			if op.code == LOAD_CONST:
				self.attrs.append(Subscr(self.code.co_consts[op.arg]))
				return
			else:
				self.push_rvalue()
				self.pop(2)
		
		if op.code == LOAD_NAME:
			self.push_lvalue(self.code.co_names[op.arg], False)
		elif op.code == LOAD_GLOBAL:
			self.push_lvalue(self.code.co_names[op.arg], True)
		elif op.code == LOAD_FAST:
			self.push_lvalue(self.code.co_varnames[op.arg], False)
		elif op.code in (LOAD_DEREF, LOAD_CLASSDEREF):
			self.push_lvalue(self.code.co_freevars[op.arg], False)
		elif op.code == DUP_TOP:
			self.pending.append(DupTop(self.descent))
		elif op.code == DUP_TOP_TWO:
			self.pending.append(DupTopTwo(self.descent))
		elif op.code == ROT_TWO:
			self.pending.append(RotTwo(self.descent))
		elif op.code == ROT_THREE:
			self.pending.append(RotThree(self.descent))
		elif op.code == ROT_FOUR:
			self.pending.append(RotFour(self.descent))
		elif op.code == CALL_FUNCTION or op.code == BUILD_CONST_KEY_MAP:
			self.push_rvalue()
			self.pop(op.arg + 1)
		elif op.code == CALL_FUNCTION_KW or op.code == CALL_METHOD:
			self.push_rvalue()
			self.pop(op.arg + 2)
		elif op.code == CALL_FUNCTION_EX:
			self.push_rvalue()
			self.pop(2 + (op.arg & 1 == 1))
		elif op.code == LOAD_METHOD:
			self.push_rvalue()
			self.push_rvalue()
			self.pop(1)
		elif op.code == FORMAT_VALUE:
			self.push_rvalue()
			self.pop(1 + (op.arg & 4 == 4))
		elif op.code == LOAD_ATTR:
			self.attrs.append(Attr(self.code.co_names[op.arg]))
		elif op.code == BINARY_SUBSCR:
			self.load_subscr = True
		elif op.code == MAKE_FUNCTION:
			self.push_rvalue()
			self.pop(2 + (op.arg & 8 == 8) + (op.arg & 4 == 4) + (op.arg & 2 == 2) + (op.arg & 1 == 1))
		elif op.code == UNPACK_SEQUENCE:
			for _ in range(op.arg): self.push_rvalue()
			self.pop(1)
		elif op.code == BUILD_MAP:
			self.push_rvalue()
			self.pop(op.arg * 2)
		elif op.code in ACTION_PUSH_RVALUE_POP_ARG:
			self.push_rvalue()
			self.pop(op.arg)
		elif op.code in ACTION_PUSH_RVALUE:
			self.push_rvalue()
		elif op.code in ACTION_PUSH_RVALUE_POP:
			self.push_rvalue()
			self.pop(1)
		elif op.code in ACTION_PUSH_RVALUE_POP_TWO:
			self.push_rvalue()
			self.pop(2)
		elif op.code in ACTION_PUSH_RVALUE_POP_THREE:
			self.push_rvalue()
			self.pop(3)
		elif op.code in ACTION_POP:
			self.pop(1)
		elif op.code in ACTION_POP_TWO:
			self.pop(2)
		elif op.code in ACTION_POP_THREE:
			self.pop(3)
		elif op.code in ACTION_DO_NOTHING:
			pass
		elif op.code in ACTION_PANIC:
			raise ValueError(f"Unable to analyze callsite; panicking on {opname[op.code]}")
		else:
			assert False, opname[op.code]

class PendingOp:
	def __init__(self, descent, stack_size):
		self.descent = descent
		self.stack = []
		self.stack_size = stack_size
	def push(self, val):
		self.stack.append(val)
		self.stack_size -= 1

class DupTop(PendingOp):
	def __init__(self, descent):
		super().__init__(descent, 1)
	def complete(self, state):
		state.push(self.stack[0])
		state.push(self.stack[0])

class DupTopTwo(PendingOp):
	def __init__(self, descent):
		super().__init__(descent, 2)
	def complete(self, state):
		state.push(self.stack[1])
		state.push(self.stack[0])
		state.push(self.stack[1])
		state.push(self.stack[0])

class RotTwo(PendingOp):
	def __init__(self, descent):
		super().__init__(descent, 2)
	def complete(self, state):
		state.push(self.stack[1])
		state.push(self.stack[0])

class RotThree(PendingOp):
	def __init__(self, descent):
		super().__init__(descent, 3)
	def complete(self, state):
		state.push(self.stack[1])
		state.push(self.stack[2])
		state.push(self.stack[0])

class RotFour(PendingOp):
	def __init__(self, descent):
		super().__init__(descent, 4)
	def complete(self, state):
		state.push(self.stack[1])
		state.push(self.stack[2])
		state.push(self.stack[3])
		state.push(self.stack[0])

@dataclass
class Tracer:
	state : TracerState
	next_i : int
	prev_i : int