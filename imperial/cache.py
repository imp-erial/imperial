from typing import Any

class Cache:
	value: Any
	is_valid: bool = False

	def __init__(self):
		self._invalidations = []
	
	def invalidate(self):
		self.is_valid = False
	
	def add_invalidation(self, invalidation):
		if hasattr(invalidation, "_cache"):
			invalidation = invalidation._cache
		if isinstance(invalidation, Cache):
			self._invalidations.append(invalidation)
		else:
			raise ValueError(invalidation)

	def cache(self, value):
		self.value = value
		self.is_valid = True
