from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Protocol, Set, Sequence
from weakref import ref, WeakValueDictionary, WeakSet
from collections import defaultdict


class Linkable(Protocol):
	# TODO: origin/origins should be Linkables, pylance can't handle it tho
	def add_link(self, origin):
		...

	def add_links(self, origins: Sequence):
		...

	def invalidate(self, memo: Optional[Set[int]] = None):
		...


class LinkMap(WeakValueDictionary[str, "BaseLinkNode"]):
	"""
	Access the overall link tree and wait for nodes to be created.
	Keys should be of the form:
	  BaseStruct{SubStruct}.keyname/basic
	RHS of the slash can be:
	  * name - the name of the struct as specified after the type
	  * basic - the basic value of the struct/key
	  * packed - the packed form of the struct (serialiazed, stringified, etc)
	"""
	parent: Optional[LinkMap]

	def __init__(self, *args, parent: Optional[LinkMap] = None, **kwargs):
		super().__init__(*args, **kwargs)
		self.parent = parent
		self.staged = defaultdict(WeakSet)

	def __setitem__(self, name: str, node: BaseLinkNode):
		if name in self:
			del self[name]

		# TODO: check if name exists in parent, and steal nodes with self in map hierarchy

		super().__setitem__(name, node)

		# Link anything waiting to be linked to this
		if name in self.staged:
			node.references_in.update(self.staged[name])
			del self.staged[name]
			# TODO: delete out of parents too

	def __delitem__(self, name: str):
		# Remove any node that starts with name and throw links in staged
		# TODO: more efficient?
		name, *ex = name.rsplit("/", 1)
		deletables = []
		for key, node in self.items():
			if key.startswith(name):
				# TODO: also add to parents?
				self.staged[key].update(node.references_in)
				deletables.append(key)

		for key in deletables:
			super().__delitem__(key)

	def add_reference(self, origin: BaseLinkNode, target: str):
		if target in self.nodes:
			self[target].add_reference(origin)
		else:
			self.staged[target].add(origin)
			if self.parent is not None:
				self.parent.add_reference(origin, target)

	def add_references(self, origin: BaseLinkNode, targets: Sequence[str]):
		for name in targets:
			if name in self.nodes:
				self[name].add_reference(origin)
			else:
				self.staged[name].add(origin)
				if self.parent is not None:
					self.parent.add_reference(origin, name)

	def remove_references(self, origin: BaseLinkNode, targets: Sequence[str]):
		for name in targets:
			if name in self.nodes:
				self[name].remove_reference(origin)
			if name in self.staged:
				self.staged[name].remove(origin)
		if self.parent is not None:
			self.parent.remove_references(origin, targets)

	def parents(self):
		parent = self.parent
		while parent is not None:
			yield parent
			parent = parent.parent


class BaseLinkNode:
	value: Any = None
	valid: bool = False
	rigid: bool

	def __init__(self, *, rigid: bool = False):
		self.rigid = rigid

		self.links_in: WeakSet[BaseLinkNode] = WeakSet()
		self.references_in: WeakSet[BaseLinkNode] = WeakSet()
		self.references_out: Set[str] = set()

	def add_link(self, origin: Linkable):
		self.links_in.add(origin)

	def add_links(self, origins: Sequence[Linkable]):
		self.links_in.update(origins)

	def add_reference(self, origin):
		self.references_in.add(origin)

	def remove_link(self, origin):
		self.links_in.remove(origin)

	def remove_reference(self, origin):
		self.references_in.remove(origin)

	def set_links_out(self, names: Sequence[str], maps: Sequence[LinkMap]):
		snames = set(names)
		added = snames - self.references_out
		removed = self.references_out - snames

		if removed:
			# Clear them out of the targets
			for lmap in maps:
				lmap.remove_references(self, removed)

		if added:
			for lmap in maps:
				lmap.add_references(self, added)

		self.references_out = snames

	def invalidate(self, memo: Optional[Set[int]] = None):
		if not self.rigid:
			if memo is None:
				memo = set()

			if id(self) not in memo:
				memo.add(id(self))
				self.valid = False

				for x in self.links_in:
					x.invalidate(memo)
				for x in self.references_in:
					x.invalidate(memo)


class LinkNode(BaseLinkNode):
	def __init__(self, *value, refresh, **kwargs):
		self.refresh = refresh

		if value:
			self._value = value[0]
			self.valid = True
		else:
			self._value = None
			self.valid = False

		super().__init__(**kwargs)

	@property
	def value(self):
		if not self.valid:
			self._value = self.refresh()
			self.valid = True
		return self._value

	@value.setter
	def value(self, value):
		if self._value is not value:
			self._value = value
			self.valid = True

			memo = {id(self)}
			for x in self.links_in:
				x.invalidate(memo)
			for x in self.references_in:
				x.invalidate(memo)


class StringLinkNode(BaseLinkNode):
	def __init__(self, value: str, **kwargs):
		super().__init__(**kwargs)
		self._value = value

	@property
	def value(self) -> str:
		return self._value

	@property
	def valid(self) -> bool:
		return True


class BigBlobLinkNode(LinkNode):
	def __init__(self, *value, refresh, **kwargs):
		super().__init__(*map(ref, value), refresh=refresh, **kwargs)

	@property
	def value(self):
		if not self.valid:
			self._value = ref(self.refresh())
			self.valid = True
		return self._value()

	@value.setter
	def value(self, value):
		if self._value is not value:
			self._value = ref(value)
			self.valid = True
			for x in self.connections:
				x.invalidate()
