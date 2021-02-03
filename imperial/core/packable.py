from collections import defaultdict

from .base import Meta
from .dynamic import Dynamic
from ..magic import SpecialRef, PACKED


class PackableMeta(Meta):
	def __new__(cls, name, bases, dct):
		ret = type.__new__(cls, name, bases, dct)
		tmp = defaultdict(lambda: [None, None])
		for value in dct.values():
			if callable(value):
				mode: str
				direction: int
				refs: set = getattr(value, "_refs", set())
				mode, direction = getattr(value, "_pack", ("", -10))
				if mode and refs:
					tmp[mode][direction] = refs

		# TODO: frozen dict
		ret._pack_links = dict(tmp)

		return ret


class Packable(Dynamic, metaclass=PackableMeta):
	_pack_links = {}

	def has_special_ref(self, ref: SpecialRef) -> bool:
		if ref is PACKED:
			return True
		return super().has_special_ref(ref)
