import inspect
from typing import Callable, Dict, Set, Tuple, Union

from .cache import Cache
from .core.base import ImperialType

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

def make_refs_only_resolver(fun: Callable, positional: Tuple[str] = ()) -> "ReferenceHandler":
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
	_has_run = False
	_other: ImperialType

	_fun: Callable
	_keys: Dict[str, str]
	_cache: Cache

	def __init__(self, fun: Callable, keys: Dict[str, str]):
		self._fun = fun
		self._keys = keys
		self._cache = Cache()

	def __call__(self, other: ImperialType):
		if self._has_run:
			if other is not self._other:
				raise ImperialLibraryError(
					f"{self.__class__.__name__} must only be used for a single struct")
		else:
			for key in self._keys.keys():
				other.add_link(key, invalidates=self._cache)
			self._has_run = True
			self._other = other
		return self

	def run(self, *args, **kwargs):
		if self._cache.is_valid:
			return self._cache.value
		keyargs = {}
		other = self._other
		for origin, kwarg in self._keys.items():
			if origin.startswith("!"):
				if origin == "!children":
					if other.has_children():
						keyargs[kwarg] = other.children()
					else:
						return None
				elif origin == "!basic":
					keyargs[kwarg] = other.resolve_basic()
				else:
					raise ImperialLibraryError(f"Unknown internal reference {key}")
			elif origin in other.keys:
				# TODO: use link map to make this safer?
				keyargs[kwarg] = other.keys[origin].resolve()
			else:
				return None
		ret = self._fun(self._other, *args, **kwargs, **keyargs)
		self._cache.cache(ret)
		return ret
	
	def keys(self) -> Set[str]:
		return set(self._keys.keys())

	def add_to(self, handler):
		handler._refs = self.keys()
		handler._cache = self._cache
