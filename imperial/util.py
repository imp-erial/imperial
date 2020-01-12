from typing import Any

class DotMap(dict):
	def __getattr__(self, name: str) -> Any:
		return self[name]
