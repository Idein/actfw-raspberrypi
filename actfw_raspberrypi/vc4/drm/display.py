from .drm import *


class Display(object):

    """Display using VideoCore4 dispmanx"""

    def __init__(self, display_num=0):
        pass

    def get_info(self):
        """
        Get display information.
        """
        pass

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
        return Window(self, dst, size, layer)

    def size(self):
        """
        Get display size.

        Returns:
            ((int, int)): (width, height)
        """
        pass

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, ex_type, ex_value, trace):
        self.close()


class Window(object):

    """
    Double buffered window.
    """

    def __init__(self, display, dst, size, layer):
        pass

    def clear(self, rgb=(0, 0, 0)):
        """
        Clear window.

        Args:
            rgb ((int, int, int)): clear color
        """
        pass

    def set_layer(self, layer):
        """
        Set window layer.

        Args:
            layer (int): new layer
        """
        pass

    def swap_layer(self, window):
        """
        Swap window layer.

        Args:
            window (:class:`~actfw_raspberrypi.vc4.display.Window`): target window
        """
        pass

    def blit(self, image):
        """
        Blit image to window.

        Args:
            image (bytes): RGB image with which size is the same as window size
        """
        pass

    def update(self):
        """
        Update window.
        """
        pass

    def close(self):
        """
        Close window.
        """
        pass

    def __enter__(self):
        return self

    def __exit__(self, ex_type, ex_value, trace):
        self.close()
