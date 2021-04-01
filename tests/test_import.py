from nose2.tools import params


@params(
    {"from": "actfw_raspberrypi", "import": "Display"},
    {"from": "actfw_raspberrypi.capture", "import": "PiCameraCapture"},
    {"from": "actfw_raspberrypi.vc4", "import": "Display"},
    {"from": "actfw_raspberrypi.vc4", "import": "Window"},
)
def test_import_actfw_raspberrypi(param):
    exec(f"""from {param['from']} import {param['import']}""")
