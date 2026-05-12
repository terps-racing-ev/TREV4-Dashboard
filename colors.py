#!/usr/bin/env python3

from typing import Optional, Tuple, Union, Sequence
import re
import string

PRUSSIAN_BLUE = (16, 35, 92)
TERPS_RED = (224, 58, 62)
TERPS_GOLD = (255, 212, 59)

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
DARK_GRAY = (23, 23, 23)
LIGHT_GRAY = (180, 180, 180)

GREEN = (0, 200, 0)
YELLOW = (255, 255, 0)
RED = (255, 0, 0)
ORANGE = (255, 165, 0)


# Type alias for color tuples
Color = Union[Tuple[int, int, int], Tuple[int, int, int, int]]


def _clamp_byte(n: int) -> int:
	try:
		i = int(n)
	except Exception:
		raise ValueError(f"Invalid color component: {n}")
	return max(0, min(255, i))


def _expand_shorthand_hex(s: str) -> str:
	# "abc" -> "aabbcc"
	return ''.join(ch * 2 for ch in s)


def _parse_hex_string(s: str) -> Color:
	s = s.strip().lstrip('#').lstrip('0x')
	if len(s) in (3, 4):
		s = _expand_shorthand_hex(s)
	if len(s) not in (6, 8):
		raise ValueError(f"Invalid hex color: {s}")
	parts = [s[0:2], s[2:4], s[4:6]]
	rgba = tuple(int(p, 16) for p in parts)
	if len(s) == 8:
		a = int(s[6:8], 16)
		return (rgba[0], rgba[1], rgba[2], a)
	return rgba


def _parse_rgb_function(s: str) -> Color:
	m = re.match(r'rgba?\s*\(([^)]+)\)', s, re.I)
	if not m:
		raise ValueError(f"Invalid rgb(...) color: {s}")
	parts = [p.strip() for p in m.group(1).split(',')]
	if len(parts) not in (3, 4):
		raise ValueError(f"Invalid rgb(...) components: {parts}")
	comps = []
	for p in parts:
		if p.endswith('%'):
			val = float(p[:-1]) * 255.0 / 100.0
		else:
			val = float(p)
		comps.append(_clamp_byte(round(val)))
	return tuple(comps)  # type: ignore[return-value]


def _to_color_seq(seq: Sequence[Union[int, float]]) -> Color:
	if len(seq) not in (3, 4):
		raise ValueError("Color sequence must have length 3 or 4")
	comps = tuple(_clamp_byte(x) for x in seq)  # type: ignore[arg-type]
	return comps  # type: ignore[return-value]


# Build a map of named colors (uppercase names -> tuple)
_COLOR_MAP = {
	name: val for name, val in globals().items()
	if name.isupper() and isinstance(val, tuple) and len(val) in (3, 4)
}


def parse_color(value: Union[str, Sequence[Union[int, float]], int, None]) -> Optional[Color]:
	"""
	Parse a JSON-friendly color specification into an (R,G,B) or (R,G,B,A) tuple.

	Accepts:
	- Named color strings like "GREEN" (case-insensitive)
	- Hex strings: "#RRGGBB", "#RGB", "0xRRGGBB", with optional alpha (#RRGGBBAA)
	- CSS-like: "rgb(255,0,0)" or "rgba(100%,0%,0%,0.5)"
	- Comma-separated numbers: "255,0,0" or "255,0,0,128"
	- Sequences/tuples: [255,0,0] or [1.0, 0.0, 0.0]
	- Single int -> treated as gray level

	Returns None if `value` is None.
	"""
	if value is None:
		return None

	# Strings
	if isinstance(value, str):
		s = value.strip()
		if not s:
			return None
		# hex styles
		if s.startswith('#') or s.startswith('0x') or all(c in string.hexdigits for c in s):
			try:
				return _parse_hex_string(s)
			except ValueError:
				pass
		# rgb(...) or rgba(...)
		if s.lower().startswith('rgb'):
			return _parse_rgb_function(s)
		# comma-separated
		if ',' in s:
			parts = [p.strip() for p in s.split(',') if p.strip()]
			nums = []
			for p in parts:
				if p.endswith('%'):
					nums.append(float(p[:-1]) * 255.0 / 100.0)
				else:
					nums.append(float(p))
			return _to_color_seq(nums)
		# Named constant
		key = s.upper()
		if key in _COLOR_MAP:
			return _COLOR_MAP[key]
		raise ValueError(f"Unrecognized color string: {value}")

	# Sequence (list/tuple)
	if isinstance(value, (list, tuple)):
		return _to_color_seq(value)

	# Single integer -> grayscale
	if isinstance(value, int):
		g = _clamp_byte(value)
		return (g, g, g)

	raise TypeError(f"Unsupported color type: {type(value)}")
