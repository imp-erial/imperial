from __future__ import annotations

from typing import Callable, cast, List, Optional, Sequence, Tuple, Union

from .key import Key
from .base import propagate, EitherValue, ImperialType, PythonValue
from .dynamic import Dynamic
from ..magic import add_help
from ..exceptions import ImperialKeyError, ImperialValueError

OptionalStrSeq = Union[None, str, Sequence[str]]


def get_data(self: Value) -> Optional[ImperialType]:
	data = self.key("data").data
	if data is self:
		return None
	if isinstance(data, type(self)):
		return data
	return self.convert_from(data)


def number(fun: Callable[[Value, PythonValue], int]) -> Callable[[Value, OptionalStrSeq], int]:
	def handler(self: Value, names: OptionalStrSeq = None) -> int:
		if names is not None:
			return self.resolve(names).number()

		data = get_data(self)
		if data is not None:
			return data.number()
		return fun(self, self.caches["basic"].value)

	add_help(handler, fun)
	return handler


def string(fun: Callable[[Value, PythonValue], str]) -> Callable[[Value, OptionalStrSeq], str]:
	def handler(self: Value, names: OptionalStrSeq = None) -> str:
		if names is not None:
			return self.resolve(names).string()

		data = get_data(self)
		if data is not None:
			return data.string()
		return fun(self, self.caches["basic"].value)

	add_help(handler, fun)
	return handler


def list(fun: Callable[[Value, PythonValue], List]) -> Callable[[Value, OptionalStrSeq], List]:
	def handler(self: Value, names: OptionalStrSeq = None) -> List:
		if names is not None:
			return self.resolve(names).list()

		data = get_data(self)
		if data is not None:
			return data.list()
		return fun(self, self.caches["basic"].value)

	add_help(handler, fun)
	return handler


class Value(Dynamic):
	has_basic = True

	@propagate
	@number
	def number(self, data: PythonValue) -> int:
		"""
		Return the python int form of this value.
		"""
		raise ImperialValueError("not a number")

	@propagate
	@string
	def string(self, data: PythonValue) -> str:
		"""
		Return the python str form of this value.
		"""
		raise ImperialValueError("not a string")

	@propagate
	@list
	def list(self, data: PythonValue) -> List:
		"""
		Return the python list form of this value.
		"""
		raise ImperialValueError("not a list")

	# TODO: value proxy support
	@classmethod
	def _register(cls):
		@cls.register
		class DataKey(Key):
			keyname = "data"

			_py_data: Optional[PythonValue] = None

			def set(self, value: EitherValue):
				if isinstance(value, ImperialType):
					self._py_data = None
					self.data = value
					# TODO: reference group
					self.container.add_link(value.caches["basic"])
					value.add_link(self.container.caches["basic"])
				else:
					# Container will normalize this when it retrieves it
					self._py_data = value
					cb = self.container.caches["basic"]
					vb = cast(ImperialType, self.data).caches["basic"]
					cb.remove_link(vb)
					vb.remove_link(cb)
					del self.data
				self.defaulted = False

			def get_default(self) -> Tuple[bool, ImperialType]:
				return True, self.container

	def refresh_basic(self) -> PythonValue:
		data = self.key("data")
		if data._py_data is None:
			return self.get_by_proxy(data.data)
		return self.get_primitive(data._py_data)

	def get_by_proxy(self, data: ImperialType) -> PythonValue:
		if isinstance(data, type(self)):
			if data is self:
				raise ImperialKeyError("data")
			return data.get_basic()
		return self.convert_from(data).get()

	def get_primitive(self, data: PythonValue) -> PythonValue:
		return data

	def set_basic(self, value: EitherValue):
		if isinstance(value, ImperialType):
			self.set_by_key("data", value)
		else:
			self.caches["basic"].value = self.normalize(value)

	__int__ = number
	__str__ = string
