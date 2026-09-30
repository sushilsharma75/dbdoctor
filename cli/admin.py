"""Trusted, local administrator provisioning: python -m cli.admin --email EMAIL."""

import click
from pydantic import EmailStr, TypeAdapter
from sqlalchemy import select

from webapp.backend.app.auth import Credentials, hash_password
from webapp.backend.app.db import User, get_db


@click.command()
@click.option("--email", required=True)
@click.option(
    "--grant-existing", is_flag=True, help="Grant an existing, independently verified account."
)
@click.option("--revoke", is_flag=True, help="Revoke administrative privileges.")
def main(email, grant_existing, revoke):
    """Run only on the trusted application host. Never grant based on email alone."""
    email = str(TypeAdapter(EmailStr).validate_python(email)).lower()
    sessions = get_db()
    db = next(sessions)
    try:
        user = db.scalar(select(User).where(User.email == email))
        if revoke:
            if user is None:
                raise click.ClickException("Account does not exist")
            user.is_admin = False
        elif user is not None:
            if not grant_existing:
                raise click.ClickException(
                    "Account exists. Verify its ownership independently before --grant-existing."
                )
            user.is_admin = True
        else:
            password = click.prompt("Password", hide_input=True, confirmation_prompt=True)
            Credentials(email=email, password=password)
            db.add(User(email=email, password_hash=hash_password(password), is_admin=True))
        db.commit()
    finally:
        sessions.close()
    click.echo("Administrator privileges updated.")


if __name__ == "__main__":
    main()
