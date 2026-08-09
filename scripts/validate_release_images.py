import os
import re


IMAGE_INPUTS = (
    "KARIZ_APP_IMAGE",
    "PYTHON_BASE_IMAGE",
    "KARIZ_POSTGRES_IMAGE",
    "KARIZ_NGINX_IMAGE",
)
DIGEST_REFERENCE = re.compile(r"\A[^\s@]+@sha256:[0-9a-f]{64}\Z")


def validate_release_images(environment):
    for name in IMAGE_INPUTS:
        value = environment.get(name, "").strip()
        if value.startswith("replace-with-") or not DIGEST_REFERENCE.fullmatch(value):
            raise ValueError(
                f"{name} must be one reviewed repository@sha256:64-lowercase-hex reference."
            )


if __name__ == "__main__":
    try:
        validate_release_images(os.environ)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    print("Release image reference check passed.")
