from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, cast, ClassVar, Dict, Iterator, List, Optional, overload, Sequence, Set, Union
from collections import defaultdict, OrderedDict

from ..magic import SpecialRef, NAME, BASIC
from ..linkmap import Linkable, LinkNode, StringLinkNode, LinkMap
from ..exceptions import ImperialKeyError

PythonValue = Union[int, str, list, float, bool, bytes, tuple]
EitherValue = Union[PythonValue, "ImperialType"]


class KeyMap(OrderedDict[str, Linkable]):
	"""
	Storage system for keys and values in a struct.
	Provides access to key data as well as methods to query the information.
	"""
	_owner: ImperialType
	_reference_staging: Dict[str, Set[ImperialType]]

	def __init__(self, *args, owner: ImperialType):
		super().__init__(*args)
		self._owner = owner
		self._reference_staging = defaultdict(set)

	def __setitem__(self, name: str, value: Linkable):
		if name in self._reference_staging:
			value.add_links(self._reference_staging[name])
			del self._reference_staging[name]
		super().__setitem__(name, value)

	def __deepcopy__(self, memo: Dict[int, Any]):
		ret = type(self)(owner=None)
		memo[id(self)] = ret
		for key, value in self.items():
			OrderedDict.__setitem__(ret, key, deepcopy(value, memo))

		return ret

	def is_ready(self, key: str) -> bool:
		return super().__contains__(key)


class Meta(type):
	def __new__(cls, name, bases, dct):
		ret = cast("ImperialType", type.__new__(cls, name, bases, dct))
		for name, prop in dct.items():
			if callable(prop) and getattr(prop, "_do_propagate", False):
				if name in ret.propagated_methods:
					raise KeyError(f"{name} is already propagated")
				ret.propagated_methods[name] = prop
		return ret


class ImperialType(metaclass=Meta):
	# Whether or not get_basic can function for this class under some condition
	# Override has_special_ref if there are any conditions in order to specify them
	has_basic: ClassVar[bool] = False

	nocopy: ClassVar[List[str]] = [
		"propagated_methods", "clones", "_this", "parent", "benefactor", "container", "donor", "manager", "linkmap",
		"caches"
	]
	propagated_methods: ClassVar[Dict[str, Callable]] = {}

	name: LinkNode
	link_prefix: str

	_this: Optional[ImperialType]
	parent: Optional[ImperialType]
	benefactor: Optional[ImperialType]
	container: Optional[Any]
	manager: Optional[ImperialType]

	keys: KeyMap
	children: Dict[str, ImperialType]

	donor: Optional[ImperialType]
	clones: List[ImperialType]

	linkmap: LinkMap
	caches: Dict[str, LinkNode]

	# Pulled from basic node
	add_link: Callable[[Any], None]
	add_links: Callable[[Sequence], None]
	invalidate: Callable[[Optional[Set[int]]], None]

	def __init__(
		self,
		data=None,
		*,
		name: Optional[str] = None,
		source=None,  # TODO: type
		children: Sequence[ImperialType] = (),
		this: Optional[ImperialType] = None,
		parent: Optional[ImperialType] = None,
		benefactor: Optional[ImperialType] = None,
		container: Optional[Any] = None,
		donor: Optional[ImperialType] = None,
		manager: Optional[ImperialType] = None,
	):
		"""
		this: What @this should point to; None means self.
		parent: What @parent should point to.
		benefactor: What this should inherit keys from first.
		container: Parent in a literal sense. ImperialType or Key.
		donor: What this was cloned from.
		manager: The struct which controls this one's locator keys, if any.
		"""
		self._this = this
		self.parent = parent
		self.benefactor = benefactor
		self.container = container
		self.manager = manager

		self.keys = KeyMap(owner=self)
		self.children = OrderedDict()

		self.donor = donor
		self.clones = []

		n = name or str(id(self))
		lp = self.link_prefix = n if parent is None else parent.link_prefix + "{%s}" % (n, )
		lm = self.linkmap = LinkMap() if parent is None else self.root.linkmap
		self.caches = {}

		lm[f"{lp}/name"] = self.name = StringLinkNode(name, rigid=True)

		if self.has_basic:
			b = lm[f"{lp}/basic"] = self.caches["basic"] = LinkNode(refresh=self.refresh_basic)
			self.add_link = b.add_link
			self.add_links = b.add_links
			self.invalidate = b.invalidate

		self.post_init()

		if data is not None:
			self.set(data)

		if source is not None:
			self.set_source(source)

		self.add_children(children)

	def post_init(self):
		"""
		Override this to hook into __init__ after setup before data assignment.
		"""
		pass

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

		if "this" in kwargs:
			new._this = kwargs["this"]

		for kw in ("source", "children", "parent", "benefactor", "container", "donor", "manager"):
			if kw in kwargs:
				setattr(new, kw, kwargs[kw])

		if "name" in kwargs:
			n = kwargs["name"] or str(id(self))
			new.link_prefix = n if kwargs["parent"] is None else kwargs["parent"].link_prefix + "{%s}" % (n, )
			new.name = StringLinkNode(new.link_prefix + "/name", kwargs["name"])

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
		# Skip calling __init__
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

	@property
	def root(self) -> ImperialType:
		if self.parent is None:
			return self
		return self.parent.root

	@property
	def this(self) -> ImperialType:
		if self._this is None:
			return self
		return self._this

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

	def resolve(self, names: Union[None, str, Sequence[str]] = None) -> ImperialType:
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
		if "basic" in self.caches:
			return self.caches["basic"].value
		raise NotImplementedError(f"no basic for {self.__class__.__name__}")

	def refresh_basic(self) -> PythonValue:
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
		self.keys[name] = self.imperialize(value)

	def set_basic(self, value: EitherValue):
		"""
		Override this to implement assigning a basic value to this struct.
		"""
		raise NotImplementedError(f"no basic for {self.__class__.__name__}")

	def set_all(self, values: Dict[str, EitherValue]):
		for key, value in values.items():
			self.set(key, value)

	def resolve_by_key(self, name: str) -> ImperialType:
		"""
		Override this to change the behavior of retrieving
		the ImperialType value of a single key.
		Typically will not need to be overridden.
		"""
		return self.key(name).data.resolve_basic()

	def resolve_basic(self) -> ImperialType:
		"""
		Only Reference really needs to override this.
		Typically will not need to be overridden.
		"""
		return self

	def add_links_to_keys(self, keys: Sequence[str], *, invalidates: Linkable):
		for key in keys:
			if self.keys.is_ready(key):
				self.keys[key].add_link(invalidates)
			else:
				self.keys._reference_staging[key].add(invalidates)

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
			if isinstance(key, SpecialRef):
				if not self.has_special_ref(key):
					return False
			elif key not in self.keys:
				return False
		return True

	def has_special_ref(self, ref: SpecialRef) -> bool:
		if ref is NAME:
			if self.name:
				return True
		elif ref is BASIC:
			return self.has_basic
		# If it's not known by us it's not here
		return False

	def add_child(self, child: ImperialType):
		"""
		Override this in order to support having substructs.
		"""
		raise NotImplementedError(f"{self.__class__.__name__} must implement add_child")

	def add_children(self, children: Sequence[ImperialType]):
		"""
		Add multiple substructs at one time.
		"""
		for child in children:
			self.add_child(child)

	def set_source(self, source):
		raise NotImplementedError("TODO: set_source")

	@classmethod
	def imperialize(cls, value) -> ImperialType:
		if isinstance(value, ImperialType):
			return value
		elif isinstance(value, int):
			from .number import Number
			return Number(value)
		elif isinstance(value, str):
			t = "string"
		elif isinstance(value, bytes):
			t = "bin"
		elif isinstance(value, (list, tuple)):
			t = "list"
		elif isinstance(value, dict):
			t = "static"
		else:
			raise ValueError(value)
		raise NotImplementedError(t)

	def parents(self) -> Iterator[ImperialType]:
		parent = self.parent
		while parent is not None:
			yield parent
			parent = parent.parent

	def benefactors(self) -> Iterator[ImperialType]:
		benefactor = self.benefactor
		while benefactor is not None:
			yield benefactor
			benefactor = benefactor.container

	def containers(self) -> Iterator[Any]:
		container = self.container
		while container is not None:
			yield container
			container = container.container

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
