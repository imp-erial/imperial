from copy import deepcopy
from typing import Callable, ClassVar, Dict, List, Optional, overload, Sequence, Union
from collections import OrderedDict

from ..magic import has_special_ref, BoundReferenceHandler
from ..exceptions import ImperialKeyError

PythonValue = Union[int, str, list, float, bool, bytes, tuple]
EitherValue = Union[PythonValue, "ImperialType"]

class KeyMap(OrderedDict):
	"""
	Storage system for keys and values in a struct.
	Provides access to key data as well as methods to query the information.
	"""
	_owner: "ImperialType"

	def __init__(self, *args, owner: "ImperialType"):
		super().__init__(*args)
		self._owner = owner

	def contains(self, name: str, memo: Dict[str, bool]) -> bool:
		if name in memo:
			return memo[name]

		ret = memo[key] = self.contains_quick(name)
		return ret

	def contains_quick(self, name: str) -> bool:
		if self.is_special_ref(name):
			return self.special_ref_exists_quick(name)
		return super().__contains__(name)

	__contains__ = contains_quick

	@staticmethod
	def is_special_ref(ref: str) -> bool:
		"""
		Special refs are references to things that are either
		not normally able to be referenced or locations that
		are relative to this location, such as siblings or parents.
		"""
		return "." in ref or "!" in ref

	def special_ref_exists(self, ref: str, memo: Dict[str, bool]) -> bool:
		if ref in memo:
			return memo[ref]

		ret = memo[key] = has_special_ref(self._owner, ref, False)
		return ret

	def special_ref_exists_quick(self, ref: str) -> bool:
		return has_special_ref(self._owner, ref, True)

	def __deepcopy__(self, memo):
		ret = type(self)(owner=None)
		memo[id(self)] = ret
		for key, value in self.items():
			OrderedDict.__setitem__(ret, key, deepcopy(value, memo))

		return ret


class Meta(type):
	def __new__(cls, name, bases, dct):
		ret = type.__new__(cls, name, bases, dct)
		for name, prop in dct.items():
			if callable(prop) and getattr(prop, "_do_propagate", False):
				if name in ret.propagated_methods:
					raise KeyError(f"{name} is already propagated")
				ret.propagated_methods[name] = prop
		return ret


class ImperialType(metaclass=Meta):
	nocopy: ClassVar[List[str]] = ["clones", "parent", "container", "donor"]
	propagated_methods: ClassVar[Dict[str, Callable]] = {}

	name: Optional[str]
	parent: Optional["ImperialType"]
	context: Optional["ImperialType"]
	container: Optional["ImperialType"]

	keys: KeyMap
	children: Dict[str, "ImperialType"]

	donor: "ImperialType"
	clones: List["ImperialType"]

	# For magic key stuff
	_ref_handlers: Dict[str, BoundReferenceHandler]

	def __init__(self,
		data=None,
		*,
		name: Optional[str] = None,
		source=None,  # TODO: type
		children: Sequence["ImperialType"] = (),
		hidden: bool = False,
		parent: Optional["ImperialType"] = None,
		context: Optional["ImperialType"] = None,
		container: Optional["ImperialType"] = None,
		donor: Optional["ImperialType"] = None
	):
		"""
		parent: What @parent should point to.
		context: Context that manages this struct
		container: What this should inherit keys from first.
		donor: What this was cloned from.
		"""
		self.name = name
		self.parent = parent
		self.context = context
		self.container = container

		self.keys = KeyMap(owner=self)
		self.children = OrderedDict()

		self.donor = donor
		self.clones = []

		self._ref_handlers = {}

		if data is not None:
			self.set(data)

		if source is not None:
			self.set_source(source)

		self.add_children(children)

	def __call__(self, data=None, **kwargs):
		"""
		Copy this struct with overridden settings.
		This is mainly only useful if this struct has no basic data
		(and can have basic data) but has defined other structural
		information. Then it can be copied in this way to make multiple
		structs with different data but the same structure.
		"""
		new = deepcopy(self)

		if data is not None:
			new.set(data)

		for kw in (
			"name", "source", "children", "hidden",
			"parent", "container", "donor"
		):
			if kw in kwargs:
				setattr(new, kw, kwargs[kw])

		return new

	def clone(self):
		"""
		Clone this struct for management by another struct.
		This occludes self from being locatable in the source.
		It also ties itself and self into a complex reference
		structure described in the documentation.
		TODO: add link
		"""
		new = self(donor=self)
		new.clones = []
		self.clones.append(new)
		return new

	def __deepcopy__(self, memo):
		ret = object.__new__(self.__class__)
		memo[id(self)] = ret
		for attr, value in self.__dict__.items():
			if attr in self.nocopy:
				setattr(ret, attr, value)
			else:
				v = deepcopy(value, memo)
				if isinstance(v, KeyMap):
					v._owner = self
				setattr(ret, attr, v)

		return ret

	def get(self, names: Union[None, str, Sequence[str]] = None) -> PythonValue:
		"""
		Get the python value of a key.

		Get python value of @struct.r1.r2.key
			struct.get(["r1", "r2", "key"]) -> python value

		Get python value of @struct.key
			struct.get("key") -> python value

		Get python value of @struct (its basic value)
			struct.get() -> python value
		"""
		if isinstance(names, (list, tuple)):
			if len(names) == 1:
				names = names[0]
			elif names:
				return self.resolve(names).get()
		if names:
			return self.get_by_key(names)
		else:
			return self.get_basic()

	@overload
	def set(self, key: Union[str, Sequence[str]], value: EitherValue):
		...

	@overload
	def set(self, key: Dict[str, EitherValue]):
		...

	@overload
	def set(self, value: EitherValue):
		...

	def set(self, *args):
		"""
		Set a key to a value. If the value is a python value,
		it's normalized to the equivalent ImperialType, if available.

		Set the value of @struct.r1.r2.key to value.
			struct.set(["r1", "r2", "key"], value)

		Set the value of @struct.key to value.
			struct.set("key", value)

		Set the values for multiple keys at one time.
			struct.set({"key": value, ...})

		Set the basic value of struct.
			struct.set(value)
		"""
		if not args:
			raise TypeError("set() missing 1 required positional argument: 'value'")

		len_args = len(args)
		if len_args > 2:
			raise TypeError(f"set() takes from 1 to 2 positional arguments but {len(args)} were given")

		if len_args == 2:
			names, value = args
			if isinstance(names, (list, tuple)):
				if len(names) == 1:
					names = names[0]
				elif names:
					self.resolve(names[:-1]).set_by_key(names[-1], value)
					return
			if names:
				self.set_by_key(names, value)
			else:
				self.set_basic(value)
		else:
			value = args[0]
			if isinstance(value, dict):
				self.set_all(value)
			else:
				self.set_basic(value)

	def resolve(self, names: Union[None, str, Sequence[str]] = None) -> "ImperialType":
		"""
		Get the ImperialType value of a key.

		Get value of @struct.r1.r2.key
			struct.resolve(["r1", "r2", "key"]) -> ImperialType

		Get value of @struct.key
			struct.resolve("key") -> ImperialType

		If this is a reference, returns the target of the reference.
		Otherwise it just returns itself.
			struct.resolve() -> ImperialType
		"""
		if isinstance(names, (list, tuple)):
			if len(names) == 1:
				names = names[0]
			elif names:
				base = self
				for name in names:
					base = base.resolve_by_key(name)
				return base
		if names:
			return self.resolve_by_key(names)
		else:
			return self.resolve_basic()

	def get_by_key(self, name: str) -> PythonValue:
		"""
		Override this to change the behavior of retrieving
		the python value of a single key.
		Typically will not need to be overridden.
		"""
		return self.resolve_by_key(name).get()

	def get_basic(self) -> PythonValue:
		"""
		Override this to implement retrieving a basic value for this struct.
		"""
		raise NotImplementedError(f"no basic for {self.__class__.__name__}")

	def set_by_key(self, name: str, value: EitherValue):
		"""
		Override this to change the behavior of setting
		the value of a single key.
		Typically will not need to be overridden.
		"""
		self.keys[name] = self.normalize(value)

	def set_basic(self, value: EitherValue):
		"""
		Override this to implement assigning a basic value to this struct.
		"""
		raise NotImplementedError(f"no basic for {self.__class__.__name__}")

	def set_all(self, values: Dict[str, EitherValue]):
		for key, value in values.items():
			self.set(key, value)

	def resolve_by_key(self, name: str) -> "ImperialType":
		"""
		Override this to change the behavior of retrieving
		the ImperialType value of a single key.
		Typically will not need to be overridden.
		"""
		return self.key(name).data.resolve_basic()

	def resolve_basic(self) -> "ImperialType":
		"""
		Only Reference really needs to override this.
		Typically will not need to be overridden.
		"""
		return self

	def key(self, names: Union[str, Sequence[str]]):
		"""
		Get a key's instance from its name.
		"""
		if isinstance(names, (list, tuple)):
			if len(names) == 1:
				names = names[0]
			else:
				base = self.resolve(names[:-1])
				return base.key(names[-1])
		try:
			return self.keys[names]
		except KeyError:
			raise ImperialKeyError(names) from None

	def has_keys(self, keys: Sequence[str]) -> bool:
		for key in keys:
			if key not in self.keys:
				return False
		return True

	def add_child(self, child: "ImperialType"):
		"""
		Override this in order to support having substructs.
		"""
		raise NotImplementedError(f"{self.__class__.__name__} must implement add_child")

	def add_children(self, children: Sequence["ImperialType"]):
		"""
		Add multiple substructs at one time.
		"""
		for child in children:
			self.add_child(child)

	def set_source(self, source):
		raise NotImplementedError("TODO: set_source")

	@classmethod
	def imperialize(cls, value) -> "ImperialType":
		if isinstance(value, ImperialType):
			return value
		elif isinstance(value, int):
			return Number(value)
		elif isinstance(value, str):
			t = "string"
		elif isinstance(value, bytes):
			return Bin(value)
		elif isinstance(value, (list, tuple)):
			t = "list"
		elif isinstance(value, dict):
			t = "static"
		else:
			raise ValueError(value)
		raise NotImplementedError(t)

	def __getattr__(self, name: str):
		if name in self.propagated_methods:
			self.propagated_methods[name]
		raise AttributeError(name)


def propagate(fun: Callable) -> Callable:
	"""
	Decorator to propagate a method to all struct types.
	Typically the method propagated should be one that
	throws an error indicating it doesn't work for those
	structs that don't specifically implement it.
	"""
	fun._do_propagate = True
	return fun
