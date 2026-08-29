"""Password hashing, and the CLI that mints one.

    python -m server.passwd

PBKDF2-HMAC-SHA256 from the standard library rather than argon2 or bcrypt,
because this is one password for one person and adding a compiled dependency to
the install path is a worse trade than the extra CPU. 600k iterations is the
current OWASP figure for PBKDF2-SHA256; it costs a fraction of a second on the
login path and nothing anywhere else.

Format, one line, safe to paste into .env:

    pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>
"""
import hashlib
import hmac
import os
import secrets
import sys

ALGO = "pbkdf2_sha256"
ITERATIONS = int(os.getenv("AGENTOS_PBKDF2_ITERATIONS", "600000"))
SALT_BYTES = 16
DK_BYTES = 32


def hash_password(password: str, iterations: int = ITERATIONS,
                  salt: bytes = None) -> str:
    if not password:
        raise ValueError("empty password")
    salt = salt or secrets.token_bytes(SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt,
                             iterations, dklen=DK_BYTES)
    return "%s$%d$%s$%s" % (ALGO, iterations, salt.hex(), dk.hex())


def verify(password: str, encoded: str) -> bool:
    """Constant-time check. Returns False for anything malformed rather than
    raising, so a corrupted .env fails closed instead of 500-ing the login page."""
    if not password or not encoded:
        return False
    try:
        algo, iters, salt_hex, want_hex = encoded.strip().split("$", 3)
        if algo != ALGO:
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                 bytes.fromhex(salt_hex), int(iters),
                                 dklen=len(bytes.fromhex(want_hex)))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(dk.hex(), want_hex)


def looks_hashed(value: str) -> bool:
    return bool(value) and value.strip().startswith(ALGO + "$")


def main():
    import getpass
    tty = sys.stdin.isatty()

    # Only prompt on a terminal. `input()` on a pipe consumed the first line —
    # the password — as the username, and then hashed the second line, so
    # `printf 'pw\npw' | python -m server.passwd` silently minted a credential
    # whose username WAS the password.
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        user = sys.argv[1]
    elif tty:
        user = input("Username [admin]: ").strip() or "admin"
    else:
        user = "admin"

    if tty:
        pw = getpass.getpass("Password: ")
        again = getpass.getpass("Again: ")
        if pw != again:
            sys.exit("Passwords do not match.")
    else:                                  # piped: read one line
        pw = sys.stdin.readline().rstrip("\n")

    if len(pw) < 10:
        sys.exit("Use at least 10 characters. This is the only lock on the door.")

    # These are ENV VAR names, and they are not the attribute names. config.py
    # does `AUTH_USER = os.getenv("AGENTOS_USER")`, so the variable in .env is
    # AGENTOS_USER while the Python attribute is config.AUTH_USER. Reading
    # auth.py alone makes the attribute look like the contract; it is not.
    # The selfcheck below pins these to whatever config.py actually reads.
    print("\n# Paste into server/.env — and never commit that file.")
    print("AGENTOS_USER=%s" % user)
    print("AGENTOS_PASSWORD_HASH=%s" % hash_password(pw))
    print("\n# While you are here, if SESSION_SECRET is still empty:")
    print("SESSION_SECRET=%s" % secrets.token_hex(32))


# ponytail: one runnable check. `python -m server.passwd --selfcheck`
def _selfcheck():
    h = hash_password("correct horse battery staple")
    assert verify("correct horse battery staple", h)
    assert not verify("Correct horse battery staple", h), "case-insensitive match"
    assert not verify("", h) and not verify("x", h)
    assert not verify("pw", ""), "empty hash accepted"
    assert not verify("pw", "garbage"), "malformed hash must fail closed"
    assert not verify("pw", "pbkdf2_sha256$notanint$aa$bb")
    assert not verify("pw", "sha1$1$aa$bb"), "wrong algorithm accepted"
    assert hash_password("x", salt=b"\x01" * 16) == \
        hash_password("x", salt=b"\x01" * 16), "not deterministic for a fixed salt"
    assert hash_password("x") != hash_password("x"), "salt is not random"
    assert looks_hashed(h) and not looks_hashed("plaintext")
    # a cheap-iteration hash still verifies: the count travels in the string
    cheap = hash_password("x", iterations=1000)
    assert verify("x", cheap) and "$1000$" in cheap

    # The env var names this CLI prints must be the ones config.py actually reads
    # with os.getenv. Nothing else enforces that: config exposes them under
    # *different* attribute names (AGENTOS_USER -> config.AUTH_USER), so reading
    # auth.py suggests a contract that does not exist, and getting it wrong
    # produces a .env the app ignores — which locks the owner out of their own
    # instance while every command reports success.
    import inspect
    import pathlib
    import re
    src = inspect.getsource(main)
    cfg = (pathlib.Path(__file__).with_name("config.py")).read_text()
    for attr in ("AUTH_USER", "AUTH_PASSWORD_HASH"):
        m = re.search(r'^%s\s*=\s*os\.getenv\(\s*"([A-Z0-9_]+)"' % attr, cfg, re.M)
        assert m, "config.py no longer reads %s from an env var" % attr
        envvar = m.group(1)
        assert 'print("%s=' % envvar in src, \
            "passwd prints the wrong env var for %s: config reads %s" % (attr, envvar)
    print("passwd selfcheck OK")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()
    else:
        main()
