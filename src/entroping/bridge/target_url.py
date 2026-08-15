from typing import Final

_UNSAFE_AUTHORITY_CHARACTERS: Final = "".join(map(chr, (*range(32), 127))) + '"|<>\\'
_UNSAFE_AUTHORITY_TRANSLATION: Final = str.maketrans("", "", _UNSAFE_AUTHORITY_CHARACTERS)


def contains_unsafe_target_authority(value: str) -> bool:
    """Return whether a URL's raw authority can alter generated Hurl syntax."""
    authority = value.partition("://")[2]
    for terminator in "/?#":
        authority = authority.partition(terminator)[0]
    return len(authority.translate(_UNSAFE_AUTHORITY_TRANSLATION)) != len(authority) or any(
        character.isspace() for character in authority
    )


def host_with_port(hostname: str, port: int | None) -> str:
    host = f"[{hostname}]" if ":" in hostname and not hostname.startswith("[") else hostname
    return host if port is None else f"{host}:{port}"
