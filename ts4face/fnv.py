"""FNV hashes as used by The Sims 4 for resource instance IDs.

EA's SimModifier (SMOD) instance IDs are FNV-1 64-bit hashes of the lowercased
modifier name, e.g. fnv64("yfheadNose_Wide").  Verified against 947 of the 957
EA modifier IDs listed in TS4 MorphMaker's ModifierList.txt; the other 10 are
community guesses at the original names.
"""

FNV64_OFFSET = 0xCBF29CE484222325
FNV64_PRIME = 0x100000001B3
FNV32_OFFSET = 0x811C9DC5
FNV32_PRIME = 0x01000193
MASK64 = 0xFFFFFFFFFFFFFFFF
MASK32 = 0xFFFFFFFF


def fnv64(name: str) -> int:
    h = FNV64_OFFSET
    for b in name.lower().encode("ascii"):
        h = (h * FNV64_PRIME) & MASK64
        h ^= b
    return h


def fnv32(name: str) -> int:
    h = FNV32_OFFSET
    for b in name.lower().encode("ascii"):
        h = (h * FNV32_PRIME) & MASK32
        h ^= b
    return h
