from actfw_raspberrypi.util import is_bullseye, is_buster


class Display(object):
    def __init__(self, display_num=0):  # type: ignore  # noqa F401
        if is_buster():
            from actfw_raspberrypi.vc4.dispmanx import Display  # type: ignore  # noqa F401

            return Display(display_num)
        elif is_bullseye():
            from actfw_raspberrypi.vc4.drm import Display  # type: ignore  # noqa F401

            return Display(display_num)
