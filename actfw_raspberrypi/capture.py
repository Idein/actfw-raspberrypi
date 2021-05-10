import enum
import io
from queue import Full
from typing import Any, Generator

from actfw_core.capture import Frame
from actfw_core.task import Producer
from actfw_core.util.pad import _PadBase, _PadDiscardingOld

# reason: actfw-core/actfw_core/v4l2/video.py is type ignored.
from actfw_core.v4l2.video import V4L2_PIX_FMT, Video, VideoPort  # type: ignore


class PiCameraCapture(Producer[Frame[bytes]]):
    camera: "picamera.PiCamera"  # type: ignore  # reason: can't depend on picamera
    args: Any
    kwargs: Any

    """Captured Frame Producer for Raspberry Pi Camera Module"""

    def __init__(
        self,
        camera: "picamera.PiCamera",  # type: ignore  # reason: can't depend on picamera
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """

        Args:
            camera (:class:`~picamera.PiCamera`): picamera object

        """
        super().__init__()
        self.camera = camera
        self.args = args
        self.kwargs = kwargs

    def _new_pad(self) -> _PadBase[Frame[bytes]]:
        return _PadDiscardingOld()

    def run(self) -> None:
        """Run producer activity"""

        def generator() -> Generator[io.BytesIO, None, None]:
            stream = io.BytesIO()
            while self._is_running():
                try:
                    yield stream
                    stream.seek(0)
                    value = stream.getvalue()
                    frame = Frame(value)
                    self._outlet(frame)
                    stream.seek(0)
                    stream.truncate()
                except GeneratorExit:
                    break

        self.camera.capture_sequence(generator(), *self.args, **self.kwargs)
