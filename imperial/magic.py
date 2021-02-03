from __future__ import annotations

import inspect
from typing import Any, Callable, cast, Dict, Optional, Protocol, Set, Tuple, Union, TYPE_CHECKING
from operator import attrgetter

if TYPE_CHECKING:
	from .core.base import ImperialType


class SpecialRef:
	def __init__(self, name: str, getter: Optional[Callable] = None):
		self.name = name
		self.getter = getter

	def __repr__(self):
		return f"SpecialRef('{self.name}')"


NAME = SpecialRef("name", attrgetter("name"))
BASIC = SpecialRef("basic", lambda x: x.caches["basic"])
PACKED = SpecialRef("packed", lambda x: x.caches["packed"])

REF = Union[str, SpecialRef]
InsConv = Optional[Callable[[Any], "ImperialType"]]


def add_help(to: Union[Callable, type], source: Union[Callable, type]):
	to.__name__ = source.__name__
	to.__doc__ = source.__doc__


class HasContainer(Protocol):
	container: ImperialType


def make_container_resolver(rh: ReferenceHandler) -> Callable:
	def handler(thing: HasContainer, *args, **kwargs):
		return rh(thing.container, *args, **kwargs)

	return handler


class ReferenceHandler:
	_fun: Callable
	_keys: Dict[REF, str]
	_refs: Set[REF]
	_to_instance: InsConv

	def __init__(self, fun: Callable, keys: Dict[REF, str], *, to_instance: InsConv = None):
		self._fun = fun
		self._keys = keys
		self._refs = set(keys.keys())
		self._to_instance = to_instance

	@classmethod
	def from_method_using_args(cls, fun: Callable, *args, positional: Tuple[REF] = (), **kwargs) -> ReferenceHandler:
		"""
		Transform all arguments into requests for
		keys by name. Sets up cache links, too.
		"""
		spec = inspect.getfullargspec(fun)
		nonself_args = spec.args[1:]
		keys = dict(zip(positional, nonself_args))
		for key in (spec.kwonlyargs if keys else nonself_args):
			keys[key] = key
		return cls(fun, keys, *args, **kwargs)

	@classmethod
	def from_method_using_kwargs(cls, fun: Callable, *args, **kwargs) -> ReferenceHandler:
		"""
		Transform all keyword-only arguments into requests for
		keys by name. Sets up cache links, too.
		"""
		keys = {key: key for key in inspect.getfullargspec(fun).kwonlyargs}
		return cls(fun, keys, *args, **kwargs)

	def __call__(self, instance: ImperialType, *args, **kwargs):
		keyargs = {}
		for origin, kwarg in self._keys.items():
			if isinstance(origin, SpecialRef):
				# Referencing something of the struct that's not a key
				keyargs[kwarg] = origin.getter(instance).value
			elif origin in instance.keys:
				keyargs[kwarg] = instance.keys[origin].resolve()
			else:
				return None

		return self._fun(instance, *args, **kwargs, **keyargs)

	def add_to(self, handler):
		handler._refs = self._refs


class CachingReferenceHandler(ReferenceHandler):
	_cache_name: str

	def __init__(self, fun: Callable, keys: Dict[REF, str], cache_name: str, **kwargs):
		super().__init__(fun, keys, **kwargs)
		self._cache_name = cache_name

	def __call__(self, instance: ImperialType, *args, **kwargs):
		node = instance.caches[self._cache_name]
		if node.valid:
			return node.value

		keyargs = {}
		for origin, kwarg in self._keys.items():
			if isinstance(origin, SpecialRef):
				# Referencing something of the struct that's not a key
				to_link = origin.getter(instance)
				keyargs[kwarg] = to_link.value
				to_link.add_link(node)
			elif origin in instance.keys:
				to_link = keyargs[kwarg] = instance.keys[origin].resolve()
				to_link.add_link(node)
			else:
				return None

		node.value = ret = self._fun(instance, *args, **kwargs, **keyargs)
		return ret
