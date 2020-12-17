import io
from queue import Full
from actfw_core.task import Producer
from actfw_core.v4l2.video import Video, VideoPort, V4L2_PIX_FMT
from actfw_core.capture import Frame
import enum


class PiCameraCapture(Producer):

    """Captured Frame Producer for Raspberry Pi Camera Module"""

    def __init__(self, camera, *args, **kwargs):
        """

        Args:
            camera (:class:`~picamera.PiCamera`): picamera object

        """
        super(PiCameraCapture, self).__init__()
        self.camera = camera
        self.args = args
        self.kwargs = kwargs
        self.frames = []

    def run(self):
        """Run producer activity"""
        def generator():
            stream = io.BytesIO()
            while self._is_running():
                try:
                    yield stream
                    stream.seek(0)
                    value = stream.getvalue()
                    updated = 0
                    for frame in reversed(self.frames):
                        if frame._update(value):
                            updated += 1
                        else:
                            break
                    self.frames = self.frames[len(self.frames) - updated:]
                    frame = Frame(value)
                    if self._outlet(frame):
                        self.frames.append(frame)
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
