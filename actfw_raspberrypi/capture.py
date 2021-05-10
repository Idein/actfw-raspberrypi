import enum
import io
from queue import Full

from actfw_core.capture import Frame
from actfw_core.task import Producer
from actfw_core.util.pad import _PadBase, _PadDiscardingOld

# reason: actfw-core/actfw_core/v4l2/video.py is type ignored.
from actfw_core.v4l2.video import V4L2_PIX_FMT, Video, VideoPort  # type: ignore


class PiCameraCapture(Producer[Frame[bytes]]):

    """Captured Frame Producer for Raspberry Pi Camera Module"""

    def __init__(self, camera, *args, **kwargs):
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

    def run(self):
        """Run producer activity"""

        def generator():
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

    def _outlet(self, o):
        length = len(self.out_queues)
        while self._is_running():
            try:
                self.out_queues[self.out_queue_id].put(o, block=False)
                self.out_queue_id = (self.out_queue_id + 1) % length
                return True
            except Full:
                return False
            except:
                traceback.print_exc()
        return False
