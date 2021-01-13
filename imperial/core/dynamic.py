from typing import Callable, ClassVar, Dict, List, Optional, Type
from collections import defaultdict

from .key import Key
from .base import ImperialType, KeyMap, EitherValue, PythonValue
from ..util import DotMap
from ..exceptions import ImperialKeyError, ImperialLibraryError, ImperialTypeError

Converter = Callable[[ImperialType], ImperialType]


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

	_converters_to: ClassVar[Dict[Type, Converter]]
	_converters_from: ClassVar[Dict[Type, Converter]]

	keys: DynamicKeyMap

	def post_init(self):
		self._register()
		self.keys = DynamicKeyMap(owner=self)

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

	@classmethod
	def register_converter(
		cls, fun: Optional[Converter] = None, *, source: Optional[Type] = None, target: Optional[Type] = None
	):
		"""
		Register a converter from a source to this or from this to a target.
		The conversion function must take in an instance of the source type
		and return a corresponding version of the target type.

		This can be used for simple conversions like string to number or
		it can be used for more complex conversions like BMP to PNG.

		Currently only meant for reversible conversions.
		TODO: Support recoverable, lossy, irreversible
		TODO: Coercion vs conversion?
		"""
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

	def key_type(self, name: str) -> Type[Key]:
		"""
		Get a key's class from its name.
		"""
		if self.manager is not None:
			ctx = type(self.manager)
			if ctx in self._overrides:
				overrides = self._overrides[ctx]
				if name in overrides:
					return overrides[name]
			elif name in self.manager.locators:
				return self.manager.locators[name]
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
		Unify multiple possible basic values into a single form
		of basic value or a dict of keys.
		"""
		raise NotImplementedError(f"{cls.__name__} must implement normalize")

	def set_by_key(self, name: str, value: EitherValue):
		self.keys[name].set(value)

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

	def find_inherited(self, name: str) -> Key:
		aliases = self.localize_key(name)
		for benefactor in self.benefactors():
			for n in aliases:
				if isinstance(benefactor, Dynamic):
					n = benefactor.key_name_from_localization(n)
				if n in benefactor.keys:
					key = benefactor.keys[n]
					if not key.hidden and not key.defaulted:
						return key
		return None
