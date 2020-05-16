import inspect
from typing import Callable, Dict, Optional, Set, Tuple, Union, TYPE_CHECKING

from .cache import Cache
from .exceptions import ImperialLibraryError

if TYPE_CHECKING:
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

def parse_special_ref(obj: "ImperialType", ref: str) -> Tuple["ImperialType", Optional[str], Optional[str]]:
	key: Optional[str] = None
	special: Optional[str] = None
	if "." in ref:
		relative, key = ref.split(".", 1)
	elif "!" in ref:
		relative, special = ref.split("!", 1)

	if relative == "parent":
		obj = obj.parent
	# TODO: previous/next/more?
	elif relative not in ["", "this"]:
		raise ImperialLibraryError(f"No relation called {relative}")

	return obj, key, special

def resolve_special_ref(obj: "ImperialType", ref: str) -> Optional["ImperialType"]:
	obj, key, special = parse_special_ref(obj, ref)

	if obj is None:
		return None

	if key:
		return obj.resolve_by_key(key)

	if special:
		if special == "children":
			if obj.has_children():
				return obj.children()
			else:
				return None
		elif special == "basic":
			return obj.resolve_basic()
		else:
			raise ImperialLibraryError(f"Unknown internal reference {key}")

	return obj

def has_special_ref(obj: "ImperialType", ref: str, quick: bool) -> bool:
	obj, key, special = parse_special_ref(obj, ref)

	if obj is None:
		return False

	if key:
		return obj.keys.contains_quick(key) if quick else key in obj.keys

	if special:
		if special == "children":
			return obj.has_children()
		elif special == "basic":
			# TODO: check if struct supports a basic
			return True
		else:
			raise ImperialLibraryError(f"Unknown internal reference {key}")

	return True

class ReferenceHandler:
	_fun: Callable
	_keys: Dict[str, str]
	_refs: Set[str]

	def __init__(self, fun: Callable, keys: Dict[str, str]):
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
	_keys: Dict[str, str]
	_refs: Set[str]
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
			if "." in origin or "!" in origin:
				# Using relative referencing
				keyargs[kwarg] = resolve_special_ref(instance, origin)
			elif origin in instance.keys:
				# TODO: use link map to make this safer?
				keyargs[kwarg] = instance.keys[origin].resolve()
			else:
				return None
		ret = self._fun(instance, *args, **kwargs, **keyargs)
		self._cache.cache(ret)
		return ret
