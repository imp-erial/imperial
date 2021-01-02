import inspect
from typing import Callable, Dict, Optional, Set, Tuple, Union, TYPE_CHECKING
from operator import attrgetter

from .cache import Cache
from .linkmap import LinkNode
from .exceptions import ImperialLibraryError

if TYPE_CHECKING:
	from .core.base import ImperialType


class SpecialRef:
	def __init__(self, name: str, getter: Optional[Callable] = None):
		self.name = name
		self.getter = getter

	def __repr__(self):
		return f"SpecialRef('{name}')"


NAME = SpecialRef("name", attrgetter("name"))
BASIC = SpecialRef("basic", lambda x: x.caches["basic"])
PACKED = SpecialRef("packed", lambda x: x.caches["packed"])

REF = Union[str, SpecialRef]


def add_help(to: Union[Callable, type], source: Union[Callable, type]):
	to.__name__ = source.__name__
	to.__doc__ = source.__doc__


def make_refs_resolver(fun: Callable) -> "ReferenceHandler":
	"""
	Transform all keyword-only arguments into requests for
	keys by name. Sets up cache links, too.
	"""
	keys = {key: key for key in inspect.getfullargspec(fun).kwonlyargs}
	return ReferenceHandler(fun, keys)


def make_refs_only_resolver(fun: Callable, positional: Tuple[REF] = ()) -> "ReferenceHandler":
	"""
	Transform all arguments into requests for
	keys by name. Sets up cache links, too.
	"""
	spec = inspect.getfullargspec(fun)
	nonself_args = spec.args[1:]
	keys = dict(zip(positional, nonself_args))
	for key in (spec.kwonlyargs if keys else nonself_args):
		keys[key] = key
	return ReferenceHandler(fun, keys)


class ReferenceHandler:
	_fun: Callable
	_keys: Dict[REF, str]
	_refs: Set[REF]

	def __init__(self, fun: Callable, keys: Dict[REF, str]):
		self._fun = fun
		self._keys = keys
		self._refs = set(keys.keys())

	def __call__(self, instance: "ImperialType"):
		name = self._fun.__name__
		if name in instance._ref_handlers:
			return instance._ref_handlers[name]
		ret = instance._ref_handlers[name] = BoundReferenceHandler(self, instance)
		return ret

	def add_to(self, handler):
		handler._refs = self._refs


class BoundReferenceHandler:
	_fun: Callable
	_keys: Dict[REF, str]
	_refs: Set[REF]
	_cache: Cache
	_instance: "ImperialType"

	def __init__(self, base: ReferenceHandler, instance: "ImperialType"):
		self._fun = base._fun
		self._keys = base._keys
		self._refs = base._refs

		self._cache = Cache()
		self._instance = instance

		for key in self._keys.keys():
			instance.add_link(key, invalidates=self._cache)

	def run(self, *args, **kwargs):
		if self._cache.is_valid:
			return self._cache.value
		keyargs = {}
		instance = self._instance
		for origin, kwarg in self._keys.items():
			if isinstance(origin, SpecialRef):
				# Referencing something of the struct that's not a key
				keyargs[kwarg] = origin.getter(instance).value
			elif origin in instance.keys:
				# TODO: use link map to make this safer?
				keyargs[kwarg] = instance.keys[origin].resolve()
			else:
				return None
		ret = self._fun(instance, *args, **kwargs, **keyargs)
		self._cache.cache(ret)
		return ret
