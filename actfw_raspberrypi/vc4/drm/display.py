# type: ignore
# flake8: noqa

import sys

from .drm import *


class Display(object):
    """Display using libdrm"""

    def __init__(self, display_num=0):
        if display_num != 0:
            raise RuntimeError(f"display_num={display_num} is not supported in bullseye.")
        try:
            self.device = Device()
        except RuntimeError as e:
            print(f"Failed to open display: {e}", file=sys.stderr)
            self.device = None

    def get_info(self):
        """
        DEPRECATED: Get display information.
        """
        raise RuntimeError("This API is deprecated. If you need width and height, use Display.size().")

    def open_window(self, dst, size, layer):
        """
        Open new window.

        Args:
            dst ((int, int, int, int)): destination rectangle (left, top, width, height)
            size ((int, int)): window size (width, height)
            layer (int): layer

        Returns:
            :class:`~actfw_raspberrypi.vc4.drm.display.Window`: window
        """
        if self.device is None:
            return DummyWindow(self.device, dst, size, layer)
        return Window(self.device, dst, size, layer)

    def size(self):
        """
        Get display size.
        if display is not found, return (-1, -1)

        Returns:
            ((int, int)): (width, height)
        """
        if self.device is None:
            return (-1, -1)

        return (self.device.width, self.device.height)

    def close(self):
        if self.device is not None:
            self.device.close()

    def __enter__(self):
        return self

    def __exit__(self, ex_type, ex_value, trace):
        self.close()


class Window(object):
    """
    Double buffered window.
    """

    def __init__(self, device, dst, size, layer):
        self.device = device
        self.size = size
        width, height = size
        self.crtc_id = self.device.crtc.crtc_id
        self.src = (0, 0, width, height)
        self.dst = dst
        self.front_fb = self.device.create_fb(width, height)
        self.back_fb = self.device.create_fb(width, height)

        self.plane = self.device.pick_plane(layer)
        self.plane.set(self.crtc_id, self.front_fb.fb_id, self.dst, self.src)

    def clear(self, rgb=(0, 0, 0)):
        """
        Clear window.

        Args:
            rgb ((int, int, int)): clear color
        """
        color = b"".join(map(lambda x: x.to_bytes(1, "little"), rgb))
        self.blit(color * self.size[0] * self.size[1])

    def set_layer(self, layer):
        """
        Set window layer.

        Args:
            layer (int): new layer
        """
        if self.plane.zpos == layer:
            return
        else:
            self.device.free_plane(self.plane)
            self.plane = self.device.pick_plane(layer)
            self.plane.set(self.crtc_id, self.front_fb.fb_id, self.dst, self.src)

    def swap_layer(self, window):
        """
        Swap window layer.

        Args:
            window (:class:`~actfw_raspberrypi.vc4.display.Window`): target window
        """
        zpos0 = self.plane.zpos
        zpos1 = window.plane.zpos
        self.device.free_plane(self.plane)
        window.set_layer(zpos0)
        self.plane = self.device.pick_plane(zpos1)
        self.plane.set(self.crtc_id, self.front_fb.fb_id, self.dst, self.src)

    def blit(self, image):
        """
        Blit image to window.

        Args:
            image (bytes): RGB image with which size is the same as window size
        """
        self.back_fb.write(image)

    def update(self):
        """
        Update window.
        """
        self.plane.set(self.crtc_id, self.back_fb.fb_id, self.dst, self.src)
        self.front_fb, self.back_fb = self.back_fb, self.front_fb

    def close(self):
        """
        Close window.
        """
        self.front_fb.close()
        self.back_fb.close()
        self.device.free_plane(self.plane)

    def __enter__(self):
        return self

    def __exit__(self, ex_type, ex_value, trace):
        self.close()


class DummyWindow(object):
    """
    DummyWindow will be used when failed to open display (e.g. no display found).
    All methods are dummy and do nothing.
    Because if display is not found, we want it to keep running without error.
    """

    def __init__(self, _device, _dst, _size, _layer):
        pass

    def clear(self, _rgb=(0, 0, 0)):
        pass

    def set_layer(self, _layer):
        pass

    def swap_layer(self, _window):
        pass

    def blit(self, _image):
        pass

    def update(self):
        pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, _ex_type, _ex_value, _trace):
        self.close()
