"""Cryptographic primitives for the Autonomy Boundary Framework.

Provides zero-dependency RFC 8032 Ed25519 asymmetric digital signatures alongside
HMAC-SHA256. With Ed25519, the human approval surface or agent enclave holds the
32-byte private seed while the Policy Enforcement Point (PEP) holds only the
32-byte public verification key — making it mathematically impossible for a
compromised PEP to forge human approvals.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass

# RFC 8032 Ed25519 curve parameters: -x^2 + y^2 = 1 + d*x^2*y^2 mod p
_P = 2**255 - 19
_L = 2**252 + 27742317777372353535851937790883648493
_D = (-121665 * pow(121666, _P - 2, _P)) % _P
_I = pow(2, (_P - 1) // 4, _P)


def _xrecover(y: int) -> int:
    xx = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P) % _P
    x = pow(xx, (_P + 3) // 8, _P)
    if (x * x - xx) % _P != 0:
        x = (x * _I) % _P
    if x % 2 != 0:
        x = _P - x
    return x


_BY = (4 * pow(5, _P - 2, _P)) % _P
_BX = _xrecover(_BY)
_B = (_BX % _P, _BY % _P, 1, (_BX * _BY) % _P)
_ZERO = (0, 1, 1, 0)


def _edwards_add(p1: tuple[int, int, int, int], p2: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    x1, y1, z1, t1 = p1
    x2, y2, z2, t2 = p2
    a = (y1 - x1) * (y2 - x2) % _P
    b = (y1 + x1) * (y2 + x2) % _P
    c = t1 * 2 * _D * t2 % _P
    d = z1 * 2 * z2 % _P
    e = (b - a) % _P
    f = (d - c) % _P
    g = (d + c) % _P
    h = (b + a) % _P
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _scalarmult(pt: tuple[int, int, int, int], e: int) -> tuple[int, int, int, int]:
    res = _ZERO
    cur = pt
    while e > 0:
        if e & 1:
            res = _edwards_add(res, cur)
        cur = _edwards_add(cur, cur)
        e >>= 1
    return res


def _encodepoint(pt: tuple[int, int, int, int]) -> bytes:
    x, y, z, _ = pt
    zi = pow(z, _P - 2, _P)
    x = (x * zi) % _P
    y = (y * zi) % _P
    bits = y | ((x & 1) << 255)
    return bits.to_bytes(32, "little")


def _decodepoint(s: bytes) -> tuple[int, int, int, int]:
    if len(s) != 32:
        raise ValueError("invalid Ed25519 point length")
    unclamped = int.from_bytes(s, "little")
    y = unclamped & ((1 << 255) - 1)
    x_sign = unclamped >> 255
    if y >= _P:
        raise ValueError("y coordinate out of range")
    x = _xrecover(y)
    if (x & 1) != x_sign:
        x = _P - x
    pt = (x, y, 1, (x * y) % _P)
    if (-x * x + y * y - 1 - _D * x * x * y * y) % _P != 0:
        raise ValueError("point not on Ed25519 curve")
    return pt


def _clamp_scalar(seed: bytes) -> tuple[int, bytes]:
    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:64]


def ed25519_public_key(private_seed: bytes) -> bytes:
    """Derives the 32-byte Ed25519 public key from a 32-byte private seed."""
    if len(private_seed) != 32:
        raise ValueError("Ed25519 private seed must be 32 bytes")
    a, _ = _clamp_scalar(private_seed)
    return _encodepoint(_scalarmult(_B, a))


def ed25519_sign(private_seed: bytes, message: bytes) -> str:
    """Signs `message` with a 32-byte Ed25519 private seed; returns hex signature."""
    if len(private_seed) != 32:
        raise ValueError("Ed25519 private seed must be 32 bytes")
    a, prefix = _clamp_scalar(private_seed)
    pub = _encodepoint(_scalarmult(_B, a))
    r = int.from_bytes(hashlib.sha512(prefix + message).digest(), "little") % _L
    r_pt = _encodepoint(_scalarmult(_B, r))
    k = int.from_bytes(hashlib.sha512(r_pt + pub + message).digest(), "little") % _L
    s = (r + k * a) % _L
    return (r_pt + s.to_bytes(32, "little")).hex()


def ed25519_verify(public_key: bytes, message: bytes, signature_hex: str) -> bool:
    """Verifies a hex Ed25519 signature against a 32-byte public key."""
    try:
        sig = bytes.fromhex(signature_hex)
        if len(sig) != 64 or len(public_key) != 32:
            return False
        r_pt = _decodepoint(sig[:32])
        a_pt = _decodepoint(public_key)
        s = int.from_bytes(sig[32:], "little")
        if s >= _L:
            return False
        k = int.from_bytes(hashlib.sha512(sig[:32] + public_key + message).digest(), "little") % _L
        lhs = _encodepoint(_scalarmult(_B, s))
        rhs = _encodepoint(_edwards_add(r_pt, _scalarmult(a_pt, k)))
        return hmac.compare_digest(lhs, rhs)
    except Exception:
        return False


@dataclass(frozen=True)
class Ed25519Keypair:
    """Asymmetric Ed25519 keypair for split-custody signing and verification."""

    private_key: bytes
    public_key: bytes

    @classmethod
    def generate(cls, seed: bytes | None = None) -> "Ed25519Keypair":
        priv = seed if seed is not None else os.urandom(32)
        return cls(private_key=priv, public_key=ed25519_public_key(priv))

    @classmethod
    def from_seed(cls, seed: bytes) -> "Ed25519Keypair":
        return cls.generate(seed=seed)

    def sign(self, message: bytes) -> str:
        return "ed25519:" + ed25519_sign(self.private_key, message)

    @staticmethod
    def verify(public_key: bytes, message: bytes, signature: str) -> bool:
        raw_sig = signature[8:] if signature.startswith("ed25519:") else signature
        return ed25519_verify(public_key, message, raw_sig)
