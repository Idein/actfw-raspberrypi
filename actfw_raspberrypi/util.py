def get_debian_version() -> int:
    with open("/etc/debian_version", "r") as f:
        raw_version = f.readline()
    return int(float(raw_version.rstrip()))


def is_buster() -> bool:
    version = get_debian_version()
    return version == 10


def is_bullseye() -> bool:
    version = get_debian_version()
    return version == 11
