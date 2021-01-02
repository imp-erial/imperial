from typing import Any, Callable, ClassVar, List, Optional, overload, Set, Tuple, Type
from functools import reduce

from .base import ImperialType, EitherValue
from ..magic import add_help, make_refs_only_resolver
from ..exceptions import ImperialKeyError, ImperialSanityError

NO_DEFAULT = object()


class KeyMeta(type):
	def __new__(cls, name, bases, dct):
		ret = type.__new__(cls, name, bases, dct)
		for value in dct.values():
			if callable(value):
				if getattr(value, "_is_estimation", False):
					if ret._estimations:
						ret._estimations.append(value)
					else:
						ret._estimations = [value]
				elif getattr(value, "_is_calculation", False):
					if ret._calculations:
						ret._calculations.append(value)
						ret._calc_links = value._refs
					else:
						ret._calculations = [value]
						ret._calc_links = value._refs.copy()
		ret._estimations = tuple(ret._estimations)
		ret._calculations = tuple(ret._calculations)
		return ret


class Key(metaclass=KeyMeta):
	"""
	A key for a dynamic struct.
	"""
	# Must define keyname
	type: ClassVar[Type[ImperialType]]
	keyname: ClassVar[Optional[str]]
	default: ClassVar[Any] = NO_DEFAULT

	# TODO: should use some locality manager which can change languages
	aliases: ClassVar[List[str]] = []
	_estimations: ClassVar[List[Callable]] = []
	_calculations: ClassVar[List[Callable]] = []
	_calc_links: ClassVar[Set[str]] = set()

	_data: Optional[ImperialType] = None
	defaulted: bool = False

	name: str
	container: Optional[ImperialType]

	def __init__(self, data=None, *, name: str = "", container: Optional[ImperialType] = None):
		self.name = name or self.keyname
		self.container = container

		if data is not None:
			self.set(data)

	@property
	def data(self):
		if self._data is None:
			inherited = self.container.find_inherited(self.name)
			if inherited is not None:
				# TODO: Reference
				self._data = Reference(origin=self, to=inherited)
			else:
				is_valid, default = self.get_default()
				if not is_valid:
					raise ImperialKeyError(self.name)
				self._data = default
				self.defaulted = True
				self.container.add_links(self._calc_links, invalidates=self)
		return self._data

	@data.setter
	def data(self, value: ImperialType):
		# TODO: type checking, superset casting?
		self._data = value(container=self.container)

	@data.deleter
	def data(self):
		self._data = None

	def get_default(self) -> Tuple[bool, Any]:
		"""
		Returns the validity of the value and the default value.
		Only override this in order to produce complex default values.
		For calculated values you can define @calculate methods.
		For static values, assign the value to the ClassVar `default`
		and an ImperialType to the ClassVar `type`.
		"""
		it = (calc(self) for calc in self._calculations if self.container.has_keys(calc._refs))
		try:
			res = next(it)
		except StopIteration:
			pass
		else:
			first_value = self.imperialize(res)
			# TODO: is setting parent here correct?
			base = self.type(first_value, parent=self.container, container=self.container)
			if any(base != x for x in it):
				raise ImperialSanityError()
			return True, base

		if self.default is NO_DEFAULT:
			return False, None
		return True, self.type(self.default)

	def set(self, value: EitherValue):
		self.data = self.imperialize(value)
		self.defaulted = False

	def resolve(self) -> ImperialType:
		return self.data.resolve()

	@classmethod
	def imperialize(cls, value: EitherValue) -> ImperialType:
		"""
		This is run by set in order to convert the values to a standard
		ImperialType via the `type` ClassVar.
		Override this entirely if there are any translations to be done
		between what is set to a key vs the struct type it actually holds.
		For instance, if this should return a tuple-type list, but can
		accept one of the members when defined and default the other(s).
		"""
		if isinstance(value, cls.type):
			return value
		return cls.type(value)

	def check_constraints(self):
		it = (calc(self) for calc in self._calculations if self.container.has_keys(calc._refs))
		if not reduce(lambda x, y: x == y, it):
			raise ImperialSanityError()


@overload
def calculate(*args: str) -> Callable[[Callable], Callable[[Optional[ImperialType]], Any]]:
	...


@overload
def calculate(fun: Callable) -> Callable[[Optional[ImperialType]], Any]:
	...


def calculate(*args, estimation=False):
	"""
	Decorator for defining a method of calculating a Key
	from other keys. The arguments defined in the method
	are the names of the other keys or the names for
	special references defined in the decorator call.

		@calculate
		def from_whatever(k1, k2):
			return k1.get() + k2.get()

	When passing references to the decorator, the number
	of references must be the same as the number of positional
	arguments. In order to also request keys directly in that
	case, pass them as keyword only arguments.

		@calculate("!basic")
		def from_whatever(basic, *, k1, k2):
			return basic + k1.get() + k2.get()
	"""
	refs: Tuple[str] = ()

	def wrapper(fun: Callable) -> Callable[[Optional[ImperialType]], Any]:
		resolver = make_refs_only_resolver(fun, refs)

		def handler(self) -> Any:
			return resolver(self.container).run()

		if estimation:
			handler._is_estimation = True
		else:
			handler._is_calculation = True
		resolver.add_to(handler)
		add_help(handler, fun)
		return handler

	if len(args) == 1 and callable(args[0]):
		return wrapper(args[0])
	else:
		refs = args
		return wrapper


@overload
def estimate(*args: str) -> Callable[[Callable], Callable[[Optional[ImperialType]], Any]]:
	...


@overload
def estimate(fun: Callable) -> Callable[[Optional[ImperialType]], Any]:
	...


def estimate(*args):
	"""
	Works like calculate, but does not assert anything about
	the sanity of the data. They're simply used if there's no
	other recourse for data inferrence and it's necessary to
	do so.
	"""
	return calculate(*args, estimation=True)
