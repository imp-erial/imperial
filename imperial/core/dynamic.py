from typing import Callable, ClassVar, Dict, Iterator, List, Optional, Sequence, Type
from collections import defaultdict, OrderedDict

from .key import Key
from .base import ImperialType, KeyMap, EitherValue, PythonValue
from ..util import DotMap
from ..exceptions import ImperialKeyError


class DynamicKeyMap(KeyMap):
	"""
	In dynamic structs, keys must be typed and their values
	may or may not exist until directly accessed.

	Keys may be inherited, have default values, or come from
	the result of calculations composed of other, defined keys.
	"""
	def __getitem__(self, name: str) -> Key:
		if name in self:
			return super().__getitem__(name)

		ret = self[name] = self._owner._make_key(name)
		return ret

	def __setitem__(self, key: str, value: Key):
		t = self._owner.key_type(key)
		if isinstance(value, t):
			super().__setitem__(key, value)
		# elif issubclass(t, type(value)):
		# 	k = self._owner._make_key(name, value)
		# 	super().__setitem__(key, k)
		else:
			raise ValueError(value)

	def __contains__(self, name: str) -> bool:
		# TODO: works
		if super().__contains__(name):
			return True
		return self._owner.find_inherited(name) is not None


class Dynamic(ImperialType):
	"""
	The superclass for most structs. It represents structs
	whose data is not represented statically in the struct
	definition. Typically, the data is retrieved from an
	external source, but it may also be algorithmic, for example.

	In a dynamic struct, keys are implicitly typed, may have
	defaults, can inherit their values from parent structs, and
	can have their values calculated from other, defined keys.

	Keys have a meaning, so they can also have translations,
	help information, aliases, etc.

	Additionally, substructs are limited to statics and only
	specifically allowed dynamic structs. They may potentially
	define their own types which are only accessible as
	substructs or keystructs, as well.
	"""
	_keys: ClassVar[Optional[Dict[str, Key]]] = None
	locators: ClassVar[Optional[Dict[str, Key]]] = None
	_overrides: ClassVar[Optional[Dict[Type[ImperialType], Dict[str, Key]]]] = None

	keys: DynamicKeyMap

	def __init__(self, data=None, *, children=(), **kwargs):
		super().__init__(**kwargs)
		self._register()
		self.keys = DynamicKeyMap(owner=self)

		if data is not None:
			self.set(data)

		self.add_children(children)

	@classmethod
	def register(cls, key: Type[Key]) -> Type[Key]:
		"""
		Decorator to register a Key definition to this struct.
		Keys registered in this way are meant to be used directly
		within a struct definition. If the key does not define a
		default, it should be assumed that it must be defined by
		a struct definition (however, it can be defined implicitly).
		"""
		if cls._keys is None:
			cls._keys = {}
		if key.keyname is not None:
			cls._keys[key.keyname] = key
		setattr(cls, key.__name__, key)
		return key

	@classmethod
	def register_locator(cls, key: Type[Key]) -> Type[Key]:
		"""
		Locators are keys which are owned by the struct they're
		registered in but are applied to its substructs. They're
		meant to be used to locate the data the substruct describes
		within this struct.

		When writing a struct definition, these keys are defined in
		the substruct, only when it's a substruct of this struct.

		When un/packing this struct, it may use these keys to select
		which data to give to the substruct or to determine where to
		place the data in the substruct into its own packed form.
		"""
		if cls.locators is None:
			cls.locators = DotMap()
		cls.locators[key.keyname] = key
		return key

	@classmethod
	def register_override(cls, context: Type[ImperialType]) -> Callable[[Type[Key]], Type[Key]]:
		"""
		Override a certain registration of a key with this Key
		only when this struct is a substruct of the given context.
		"""
		def registrar(key: Type[Key]) -> Type[Key]:
			if cls._overrides is None:
				cls._overrides = defaultdict(dict)
			cls._overrides[context][key.keyname] = key
			return key

		return registrar

	def key_type(self, name: str) -> Type[Key]:
		"""
		Get a key's class from its name.
		"""
		if self.context is not None:
			ctx = type(self.context)
			if ctx in self._overrides:
				overrides = self._overrides[ctx]
				if name in overrides:
					return overrides[name]
			elif name in self.context.locators:
				return self.context.locators[name]
		if name in self._keys:
			return self._keys[name]
		raise ImperialKeyError(f"{name} of {self}")

	def _make_key(self, name: str, data=None) -> Key:
		return self.key_type(name)(data, name=name, container=self)

	def localize_key(self, name: str) -> List[str]:
		"""
		Get all localizations of a key name.
		"""
		# TODO: this
		return [name]

	def key_name_from_localization(self, name: str) -> str:
		"""
		Retrieve the internal name of a key from a localized name.
		"""
		# TODO: this
		return name

	def check_constraints(self, name: Optional[str] = None):
		"""
		Run all registered calculations and assert that they have
		the same result. If the key was unset, set it.
		Raises ImperialSanityError if they do not.
		"""
		if name is None:
			for name in self.keys:
				self.check_constraints(name)
			return

		self.keys[name].check_constraints()

	@classmethod
	def normalize(cls, value: EitherValue) -> PythonValue:
		"""
		Unify multiple possible basic values into a single basic
		value or a dict of keys.
		"""
		raise NotImplementedError(f"{cls.__name__} must implement normalize")

	def set_by_key(self, name: str, value: EitherValue):
		self.keys[name].set(value)

	def containers(self) -> Iterator[ImperialType]:
		container = self.container
		while container is not None:
			yield container
			container = container.container

	def parents(self) -> Iterator[ImperialType]:
		parent = self.parent
		while parent is not None:
			yield parent
			parent = parent.parent

	def find_inherited(self, name: str) -> Key:
		aliases = self.localize_key(name)
		for container in self.containers():
			for n in aliases:
				if isinstance(container, Dynamic):
					n = container.key_name_from_localization(n)
				if n in container.keys:
					key = container.keys[n]
					if not key.hidden and not key.defaulted:
						return key
		return None
