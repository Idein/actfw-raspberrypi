# type: ignore
# flake8: noqa

from actfw_raspberrypi.util import is_bullseye, is_buster


class Display(object):
    def __init__(self, display_num=0):
        self.display = None
        if is_buster():
            from actfw_raspberrypi.vc4.dispmanx import Display

            self.display = Display(display_num)
        elif is_bullseye():
            from actfw_raspberrypi.vc4.drm import Display

            self.display = Display(display_num)
        else:
            raise RuntimeError("not support os version.")

    def get_info(self):
        return self.display.get_info()

    def open_window(self, dst, size, layer):
        return self.display.open_window(dst, size, layer)

    def size(self):
        return self.display.size()

    def close(self):
        self.display.close()
        self.display = None

    def __enter__(self):
        return self

    def __exit__(self, ex_type, ex_value, trace):
        self.close()
