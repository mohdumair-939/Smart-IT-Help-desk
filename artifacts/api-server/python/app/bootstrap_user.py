"""Create an initial support engineer or administrator account interactively."""

import argparse
import getpass
import re
import sys

from sqlalchemy import select

from app.database import SessionLocal
from app.models import User
from app.security import hash_password


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=("support_engineer", "admin"), required=True)
    args = parser.parse_args()

    name = input("Name: ").strip()
    email = input("Email: ").strip().lower()
    department = input("Department: ").strip()
    password = getpass.getpass("Password (minimum 12 characters): ")
    confirmation = getpass.getpass("Confirm password: ")

    if len(name) < 2 or len(department) < 2 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        print("Enter a valid name, email, and department.", file=sys.stderr)
        return 2
    if len(password) < 12 or password != confirmation:
        print("Passwords must match and contain at least 12 characters.", file=sys.stderr)
        return 2

    with SessionLocal() as db:
        if db.scalar(select(User.id).where(User.email == email)) is not None:
            print("An account with that email already exists.", file=sys.stderr)
            return 2
        db.add(
            User(
                name=name,
                email=email,
                department=department,
                role=args.role,
                password_hash=hash_password(password),
            )
        )
        db.commit()
    print(f"Created {args.role} account for {email}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
