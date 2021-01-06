from typing import Callable, cast, ClassVar, Dict, List, Optional, Sequence, Tuple, Type, Union

from .key import Key
from .base import propagate, EitherValue, ImperialType, PythonValue
from .dynamic import Dynamic
from ..magic import add_help
from ..exceptions import ImperialKeyError, ImperialLibraryError, ImperialTypeError, ImperialValueError

OptionalStrSeq = Union[None, str, Sequence[str]]


def number(fun: Callable[["Value", PythonValue], int]) -> Callable[["Value", OptionalStrSeq], int]:
	def handler(self: "Value", names: OptionalStrSeq = None) -> int:
		if names is not None:
			return self.resolve(names).number()

		if self.caches["basic"].valid:
			return fun(self, self.caches["basic"].value)

		data = self.key("data")
		if data._py_data is None:
			if isinstance(data.data, type(self)):
				if data.data is self:
					raise ImperialKeyError("data")
				return data.data.number()
			return self.convert_from(data.data).number()
		return fun(self, data._py_data)

	add_help(handler, fun)
	return handler


def string(fun: Callable[["Value", PythonValue], str]) -> Callable[["Value", OptionalStrSeq], str]:
	def handler(self: "Value", names: OptionalStrSeq = None) -> str:
		if names is not None:
			return self.resolve(names).string()

		if self.caches["basic"].valid:
			return fun(self, self.caches["basic"].value)

		data = self.key("data")
		if data._py_data is None:
			if isinstance(data.data, type(self)):
				if data.data is self:
					raise ImperialKeyError("data")
				return data.data.string()
			return self.convert_from(data.data).string()
		return fun(self, data._py_data)

	add_help(handler, fun)
	return handler


def list(fun: Callable[["Value", PythonValue], List]) -> Callable[["Value", OptionalStrSeq], List]:
	def handler(self: "Value", names: OptionalStrSeq = None) -> List:
		if names is not None:
			return self.resolve(names).list()

		if self.caches["basic"].valid:
			return fun(self, self.caches["basic"].value)

		data = self.key("data")
		if data._py_data is None:
			if isinstance(data.data, type(self)):
				if data.data is self:
					raise ImperialKeyError("data")
				return data.data.list()
			return self.convert_from(data.data).list()
		return fun(self, data._py_data)

	add_help(handler, fun)
	return handler


Converter = Callable[[ImperialType], ImperialType]


class Value(Dynamic):
	has_basic = True

	# Define allowable Python types
	types: ClassVar[Tuple[Type]]
	_converters_to: ClassVar[Dict[Type, Converter]]
	_converters_from: ClassVar[Dict[Type, Converter]]

	@classmethod
	def register_converter(
		cls, fun: Optional[Converter] = None, *, source: Optional[Type] = None, target: Optional[Type] = None
	):
		if source is not None and target is not None:
			raise ImperialLibraryError("cannot register a converter with both a source and target")
		elif source is None and target is None:
			raise ImperialLibraryError("registering a converter must specify either a source or target")

		def handler(fun: Converter):
			if target is not None:
				cls._converters_to[target] = fun
			elif source is not None:
				cls._converters_from[source] = fun

		if fun is not None:
			handler(fun)
			return

		return handler

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

	def get_basic(self) -> PythonValue:
		return self.caches["basic"].value

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

	def convert_to(self, type: Type[ImperialType]) -> ImperialType:
		"""
		Convert this struct into another struct type.
		Override this in order to do more generalized conversions.
		"""
		if type in self._converters_to:
			return self._converters_to[type](self)
		raise ImperialTypeError(f"no conversion from {self.__class__.__name__} to {type.__name__} known")

	def convert_from(self, data: ImperialType) -> ImperialType:
		"""
		Convert another struct into this struct type.
		Override this in order to do more generalized conversions.
		"""
		type_data = type(data)
		if type_data in self._converters_from:
			return self._converters_from[type_data](data)
		return data.convert_to(type(self))

	__int__ = number
	__str__ = string
