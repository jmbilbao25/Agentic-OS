"""Set the login password.

    python -m server.tools.setpass                # prompt, then write to .env
    python -m server.tools.setpass --print        # just print the hash
    python -m server.tools.setpass --generate     # invent a strong one and show it

Writes AUTH_USER and AUTH_PASSWORD_HASH into server/.env and removes any
plaintext AUTH_PASSWORD line it finds. Restart the service afterwards; changing
the password invalidates existing sessions by design.
"""
import argparse
import getpass
import re
import secrets
import string
import sys
from pathlib import Path

from .. import config
from ..auth import hash_password

ENV = Path(__file__).resolve().parent.parent / ".env"


def strong(n=20):
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_=+"
    return "".join(secrets.choice(alphabet) for _ in range(n))


def write_env(user, hashed):
    lines = ENV.read_text().splitlines() if ENV.exists() else []
    out, seen_user, seen_hash = [], False, False
    for line in lines:
        if re.match(r"^\s*AUTH_PASSWORD\s*=", line):
            continue                                  # drop plaintext entirely
        if re.match(r"^\s*AUTH_USER\s*=", line):
            out.append("AUTH_USER=%s" % user); seen_user = True
        elif re.match(r"^\s*AUTH_PASSWORD_HASH\s*=", line):
            out.append("AUTH_PASSWORD_HASH=%s" % hashed); seen_hash = True
        else:
            out.append(line)
    if not seen_user:
        out.append("AUTH_USER=%s" % user)
    if not seen_hash:
        out.append("AUTH_PASSWORD_HASH=%s" % hashed)

    if not any(re.match(r"^\s*SESSION_SECRET\s*=\s*\S", l) for l in out):
        out.append("SESSION_SECRET=%s" % secrets.token_hex(32))
        print("also generated SESSION_SECRET")

    ENV.write_text("\n".join(out).rstrip() + "\n")
    ENV.chmod(0o600)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", default=config.AUTH_USER)
    ap.add_argument("--print", action="store_true", dest="show",
                    help="print the hash, do not touch .env")
    ap.add_argument("--generate", action="store_true",
                    help="generate a strong password instead of prompting")
    args = ap.parse_args()

    if args.generate:
        pw = strong()
        print("\n  generated password:  %s\n  SAVE THIS NOW — it is not recoverable.\n" % pw)
    elif sys.stdin.isatty():
        pw = getpass.getpass("password: ")
        if len(pw) < 10:
            sys.exit("setpass: use at least 10 characters — this is reachable "
                     "from the internet")
        if pw != getpass.getpass("again: "):
            sys.exit("setpass: they do not match")
    else:
        pw = sys.stdin.read().strip()
        if not pw:
            sys.exit("setpass: no password on stdin")

    hashed = hash_password(pw)

    if args.show:
        print("AUTH_USER=%s" % args.user)
        print("AUTH_PASSWORD_HASH=%s" % hashed)
        return

    write_env(args.user, hashed)
    print("wrote %s\n  AUTH_USER=%s\n  AUTH_PASSWORD_HASH=pbkdf2_sha256$…"
          % (ENV, args.user))
    print("\nnow restart:  sudo systemctl restart agentos")


if __name__ == "__main__":
    main()
