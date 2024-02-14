import pytest


@pytest.mark.parametrize(
    "from_, import_",
    [
        ("actfw_raspberrypi", "Display"),
        ("actfw_raspberrypi.capture", "PiCameraCapture"),
        ("actfw_raspberrypi.vc4", "Display"),
    ],
)
def test_import_actfw_raspberrypi(from_: str, import_: str) -> None:
    exec(f"""from {from_} import {import_}""")
