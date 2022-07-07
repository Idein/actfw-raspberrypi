#!/usr/bin/python3

from enum import Enum
import json
import mmap
import os
import tempfile
import time
import threading
from typing import List, Optional, Union, Callable, Generic, Iterable, Tuple, TypeVar

import libcamera

from actfw_core.capture import Frame
from actfw_core.task import Producer



class _MappedBuffer:
    def __init__(self, request, stream):
        stream = request.picam2.stream_map[stream]
        self.__fb = request.request.buffers[stream]

    def __enter__(self):

        # Check if the buffer is contiguous and find the total length.
        fd = self.__fb.fd(0)
        buflen = 0
        for i in range(self.__fb.num_planes):
            buflen = buflen + self.__fb.length(i)
            if fd != self.__fb.fd(i):
                raise RuntimeError('_MappedBuffer: Cannot map non-contiguous buffer!')

        self.__mm = mmap.mmap(fd, buflen, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)
        return self.__mm

    def __exit__(self, exc_type, exc_value, exc_traceback):
        if self.__mm is not None:
            self.__mm.close()


class CompletedRequest:
    def __init__(self, request, picam2):
        self.request = request
        self.ref_count = 1
        self.lock = threading.Lock()
        self.picam2 = picam2
        self.stop_count = picam2.stop_count
        self.configure_count = picam2.configure_count

    def acquire(self):
        """Acquire a reference to this completed request, which stops it being recycled back to
        the camera system."""
        with self.lock:
            if self.ref_count == 0:
                raise RuntimeError("CompletedRequest: acquiring lock with ref_count 0")
            self.ref_count += 1

    def release(self):
        """Release this completed frame back to the camera system (once its reference count
        reaches zero)."""
        with self.lock:
            self.ref_count -= 1
            if self.ref_count < 0:
                raise RuntimeError("CompletedRequest: lock now has negative ref_count")
            elif self.ref_count == 0:
                # If the camera has been stopped since this request was returned then we
                # can't recycle it.
                if self.stop_count == self.picam2.stop_count:
                    self.request.reuse()
                    with self.picam2.controls_lock:
                        for key, value in self.picam2.controls.items():
                            id = self.picam2.camera.find_control(key)
                            self.request.set_control(id, value)
                        self.picam2.controls = {}
                        self.picam2.camera.queue_request(self.request)
                self.request = None

    def make_buffer(self, name) -> bytes:
        """Make bytes from the named stream's buffer."""
        with _MappedBuffer(self, name) as b:
            return b.read()


STILL = libcamera.StreamRole.StillCapture
RAW = libcamera.StreamRole.Raw
VIDEO = libcamera.StreamRole.VideoRecording
VIEWFINDER = libcamera.StreamRole.Viewfinder


class LibcameraCapture(Producer[Frame[bytes]]):

    """Welcome to the PiCamera2 class."""

    @staticmethod
    def load_tuning_file(tuning_file, dir=None):
        """Load the named tuning file. If dir is given, then only that directory is checked,
        otherwise a list of likely installation directories is searched."""
        if dir is not None:
            dirs = [dir]
        else:
            dirs = ["/home/pi/libcamera/src/ipa/raspberrypi/data",
                    "/usr/local/share/libcamera/ipa/raspberrypi",
                    "/usr/share/libcamera/ipa/raspberrypi"]
        for dir in dirs:
            file = os.path.join(dir, tuning_file)
            if os.path.isfile(file):
                with open(file, 'r') as fp:
                    return json.load(fp)
        raise RuntimeError("Tuning file not found")

    def __init__(
            self,
            camera_num: int = 0,
            tuning: Optional[Union[str, dict]] = None,
            size: Tuple[int, int] = (640, 480),
            framerate: int = 30,
            expected_format: str = "BGR888",
    ) -> None:
        """Initialise camera system and open the camera for use."""
        super().__init__()
        tuning_file = None
        if tuning is not None:
            if isinstance(tuning, str):
                os.environ["LIBCAMERA_RPI_TUNING_FILE"] = tuning
            else:
                tuning_file = tempfile.NamedTemporaryFile('w')
                json.dump(tuning, tuning_file)
                tuning_file.flush()  # but leave it open as closing it will delete it
                os.environ["LIBCAMERA_RPI_TUNING_FILE"] = tuning_file.name
        else:
            os.environ.pop("LIBCAMERA_RPI_TUNING_FILE", None)  # Use default tuning
        self.camera_manager = libcamera.CameraManager.singleton()
        self.camera_idx = camera_num
        self.size = size
        self.framerate = framerate
        self.expected_format = expected_format
        self._reset_flags()
        try:
            self._open_camera()
        except Exception:
            raise RuntimeError("Camera __init__ sequence did not complete.")
        finally:
            if tuning_file is not None:
                tuning_file.close()  # delete the temporary file

    def _reset_flags(self) -> None:
        self.camera = None
        self.is_open = False
        self.camera_controls = None
        self.camera_config = None
        self.libcamera_config = None
        self.streams = None
        self.stream_map = None
        self.started = False
        self.stop_count = 0
        self.configure_count = 0
        self.controls_lock = threading.Lock()
        self.controls = {}
        self.options = {}
        self.completed_requests = []
        self.lock = threading.Lock()  # protects the completed_requests fields
        self.have_event_loop = False
        self.current = None
        self.own_current = False
        self.handle_lock = threading.Lock()

    def capture_size(self):
        return self.size

    @property
    def camera_properties(self) -> dict:
        return {} if self.camera is None else self.camera.properties

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_traceback):
        self.close()

    def __del__(self):
        # Without this libcamera will complain if we shut down without closing the camera.
        self.close()

    def _initialize_camera(self) -> bool:
        if self.camera_manager.cameras:
            if isinstance(self.camera_idx, str):
                try:
                    self.camera = self.camera_manager.get(self.camera_idx)
                except Exception:
                    self.camera = self.camera_manager.find(self.camera_idx)
            elif isinstance(self.camera_idx, int):
                self.camera = self.camera_manager.cameras[self.camera_idx]
        else:
            raise RuntimeError("Camera(s) not found (Do not forget to disable legacy camera with raspi-config).")

        if self.camera is not None:
            self._identify_camera()
            self.camera_controls = self.camera.controls

            # The next two lines could be placed elsewhere?
            self.sensor_resolution = self.camera.properties["PixelArraySize"]
            self.sensor_format = self.camera.generate_configuration([RAW]).at(0).pixel_format

            return True
        else:
            raise RuntimeError("Initialization failed.")

    def _identify_camera(self):
        for idx, address in enumerate(self.camera_manager.cameras):
            if address == self.camera:
                self.camera_idx = idx
                break

    def _open_camera(self) -> None:
        if self._initialize_camera():
            if self.camera.acquire() >= 0:
                self.is_open = True
            else:
                raise RuntimeError("Failed to acquire camera")
        else:
            raise RuntimeError("Failed to initialize camera")

    def close(self) -> None:
        if self.is_open:
            self.stop()
            if self.camera.release() < 0:
                raise RuntimeError("Failed to release camera")
            self.is_open = False
            self.camera_config = None
            self.libcamera_config = None
            self.streams = None
            self.stream_map = None

    def _make_initial_stream_config(self, stream_config: dict, updates: dict) -> dict:
        # Take an initial stream_config and add any user updates.
        if updates is None:
            return None
        valid = ("format", "size")
        for key, value in updates.items():
            if key in valid:
                stream_config[key] = value
            else:
                raise ValueError(f"Bad key '{key}': valid stream configuration keys are {valid}")
        return stream_config

    def _add_display_and_encode(self, config, display, encode) -> None:
        if display is not None and config.get(display, None) is None:
            raise RuntimeError(f"Display stream {display} was not defined")
        if encode is not None and config.get(encode, None) is None:
            raise RuntimeError(f"Encode stream {encode} was not defined")
        config['display'] = display
        config['encode'] = encode

    def create_configuration(self, main={}, lores=None, raw=None, transform=libcamera.Transform(), colour_space=libcamera.ColorSpace.Jpeg(), buffer_count=4, controls={}, display="main", encode="main"):
        "Make a configuration suitable for camera preview."
        if self.camera is None:
            raise RuntimeError("Camera not opened")
        main = self._make_initial_stream_config({"format": self.expected_format, "size": self.size}, main)
        self.align_stream(main)
        lores = self._make_initial_stream_config({"format": "YUV420", "size": main["size"]}, lores)
        raw = self._make_initial_stream_config({"format": self.sensor_format, "size": main["size"]}, raw)
        frame_duration_limits = 1000000 // self.framerate
        controls = {"NoiseReductionMode": libcamera.NoiseReductionMode.Minimal,
                    "FrameDurationLimits": (frame_duration_limits, frame_duration_limits)} | controls
        config = {"use_case": "preview",
                  "transform": transform,
                  "colour_space": colour_space,
                  "buffer_count": buffer_count,
                  "main": main,
                  "lores": lores,
                  "raw": raw,
                  "controls": controls}
        self._add_display_and_encode(config, display, encode)
        return config

    def _check_stream_config(self, stream_config, name) -> None:
        # Check the parameters for a single stream.
        if type(stream_config) is not dict:
            raise RuntimeError(name + " stream should be a dictionary")
        if "format" not in stream_config:
            raise RuntimeError("format not found in " + name + " stream")
        if "size" not in stream_config:
            raise RuntimeError("size not found in " + name + " stream")
        format = stream_config["format"]
        if type(format) is not str:
            raise RuntimeError("format in " + name + " stream should be a string")
        if name == "raw":
            if not self.is_Bayer(format):
                raise RuntimeError("Unrecognised raw format " + format)
        else:
            if not self.is_YUV(format) and not self.is_RGB(format):
                raise RuntimeError("Bad format " + format + " in stream " + name)
        if type(stream_config["size"]) is not tuple or len(stream_config["size"]) != 2:
            raise RuntimeError("size in " + name + " stream should be (width, height)")

    def check_camera_config(self, camera_config: dict) -> None:
        required_keys = ["colour_space", "transform", "main", "lores", "raw"]
        for name in required_keys:
            if name not in camera_config:
                raise RuntimeError(f"'{name}' key expected in camera configuration")

        # Check the entire camera configuration for errors.
        if not isinstance(camera_config["colour_space"], libcamera._libcamera.ColorSpace):
            raise RuntimeError("Colour space has incorrect type")
        if not isinstance(camera_config["transform"], libcamera._libcamera.Transform):
            raise RuntimeError("Transform has incorrect type")

        self._check_stream_config(camera_config["main"], "main")
        if camera_config["lores"] is not None:
            self._check_stream_config(camera_config["lores"], "lores")
            main_w, main_h = camera_config["main"]["size"]
            lores_w, lores_h = camera_config["lores"]["size"]
            if lores_w > main_w or lores_h > main_h:
                raise RuntimeError("lores stream dimensions may not exceed main stream")
            if not self.is_YUV(camera_config["lores"]["format"]):
                raise RuntimeError("lores stream must be YUV")
        if camera_config["raw"] is not None:
            self._check_stream_config(camera_config["raw"], "raw")

    def _update_libcamera_stream_config(self, libcamera_stream_config, stream_config, buffer_count) -> None:
        # Update the libcamera stream config with ours.
        libcamera_stream_config.size = stream_config["size"]
        libcamera_stream_config.pixel_format = stream_config["format"]
        libcamera_stream_config.buffer_count = buffer_count

    def _make_libcamera_config(self, camera_config):
        # Make a libcamera configuration object from our Python configuration.

        # We will create each stream with the "viewfinder" role just to get the stream
        # configuration objects, and note the positions our named streams will have in
        # libcamera's stream list.
        roles = [VIEWFINDER]
        index = 1
        self.main_index = 0
        self.lores_index = -1
        self.raw_index = -1
        if camera_config["lores"] is not None:
            self.lores_index = index
            index += 1
            roles += [VIEWFINDER]
        if camera_config["raw"] is not None:
            self.raw_index = index
            roles += [RAW]

        # Make the libcamera configuration, and then we'll write all our parameters over
        # the ones it gave us.
        libcamera_config = self.camera.generate_configuration(roles)
        libcamera_config.transform = camera_config["transform"]
        buffer_count = camera_config["buffer_count"]
        self._update_libcamera_stream_config(libcamera_config.at(self.main_index), camera_config["main"], buffer_count)
        libcamera_config.at(self.main_index).color_space = camera_config["colour_space"]
        if self.lores_index >= 0:
            self._update_libcamera_stream_config(libcamera_config.at(self.lores_index), camera_config["lores"], buffer_count)
            libcamera_config.at(self.lores_index).color_space = camera_config["colour_space"]
        if self.raw_index >= 0:
            self._update_libcamera_stream_config(libcamera_config.at(self.raw_index), camera_config["raw"], buffer_count)
            libcamera_config.at(self.raw_index).color_space = libcamera.ColorSpace.Raw()

        return libcamera_config

    def align_stream(self, stream_config: dict) -> None:
        # Adjust the image size so that all planes are a mutliple of 32 bytes wide.
        # This matches the hardware behaviour and means we can be more efficient.
        align = 32
        if stream_config["format"] in ("YUV420", "YVU420"):
            align = 64  # because the UV planes will have half this alignment
        elif stream_config["format"] in ("XBGR8888", "XRGB8888"):
            align = 16  # 4 channels per pixel gives us an automatic extra factor of 2
        size = stream_config["size"]
        stream_config["size"] = (size[0] - size[0] % align, size[1] - size[1] % 2)

    def is_YUV(self, fmt) -> bool:
        return fmt in ("NV21", "NV12", "YUV420", "YVU420", "YVYU", "YUYV", "UYVY", "VYUY")

    def is_RGB(self, fmt) -> bool:
        return fmt in ("BGR888", "RGB888", "XBGR8888", "XRGB8888")

    def is_Bayer(self, fmt) -> bool:
        return fmt in ("SBGGR10", "SGBRG10", "SGRBG10", "SRGGB10",
                       "SBGGR10_CSI2P", "SGBRG10_CSI2P", "SGRBG10_CSI2P", "SRGGB10_CSI2P",
                       "SBGGR12", "SGBRG12", "SGRBG12", "SRGGB12",
                       "SBGGR12_CSI2P", "SGBRG12_CSI2P", "SGRBG12_CSI2P", "SRGGB12_CSI2P")

    def _make_requests(self) -> List[libcamera.Request]:
        # Make libcamera request objects. Makes as many as the number of buffers in the
        # stream with the smallest number of buffers.
        num_requests = min([len(self.allocator.buffers(stream)) for stream in self.streams])
        requests = []
        for i in range(num_requests):
            request = self.camera.create_request()
            if request is None:
                raise RuntimeError("Could not create request")

            for stream in self.streams:
                if request.add_buffer(stream, self.allocator.buffers(stream)[i]) < 0:
                    raise RuntimeError("Failed to set request buffer")

            requests.append(request)

        return requests

    def _update_stream_config(self, stream_config, libcamera_stream_config) -> None:
        # Update our stream config from libcamera's.
        stream_config["format"] = libcamera_stream_config.pixel_format
        stream_config["size"] = libcamera_stream_config.size
        stream_config["stride"] = libcamera_stream_config.stride
        stream_config["framesize"] = libcamera_stream_config.frame_size

    def _update_camera_config(self, camera_config, libcamera_config) -> None:
        # Update our camera config from libcamera's.
        camera_config["transform"] = libcamera_config.transform
        camera_config["colour_space"] = libcamera_config.at(0).color_space
        self._update_stream_config(camera_config["main"], libcamera_config.at(0))
        if self.lores_index >= 0:
            self._update_stream_config(camera_config["lores"], libcamera_config.at(self.lores_index))
        if self.raw_index >= 0:
            self._update_stream_config(camera_config["raw"], libcamera_config.at(self.raw_index))

    def configure(self, camera_config) -> None:
        """Configure the camera system with the given configuration."""
        if self.started:
            raise RuntimeError("Camera must be stopped before configuring")

        # Mark ourselves as unconfigured.
        self.libcamera_config = None
        self.camera_config = None

        # Check the config and turn it into a libcamera config.
        self.check_camera_config(camera_config)
        libcamera_config = self._make_libcamera_config(camera_config)

        # Check that libcamera is happy with it.
        status = libcamera_config.validate()
        self._update_camera_config(camera_config, libcamera_config)
        if status == libcamera.CameraConfiguration.Status.Invalid:
            raise RuntimeError("Invalid camera configuration: {}".format(camera_config))
        elif status == libcamera.CameraConfiguration.Status.Adjusted:
            # Adjusted
            pass

        # Configure libcamera.
        if self.camera.configure(libcamera_config):
            raise RuntimeError("Configuration failed: {}".format(camera_config))

        # Record which libcamera stream goes with which of our names.
        self.stream_map = {"main": libcamera_config.at(0).stream}
        self.stream_map["lores"] = libcamera_config.at(self.lores_index).stream if self.lores_index >= 0 else None
        self.stream_map["raw"] = libcamera_config.at(self.raw_index).stream if self.raw_index >= 0 else None

        # These name the streams that we will display/encode.
        self.display_stream_name = camera_config['display']
        if self.display_stream_name is not None and self.display_stream_name not in camera_config:
            raise RuntimeError(f"Display stream {self.display_stream_name} was not defined")
        self.encode_stream_name = camera_config['encode']
        if self.encode_stream_name is not None and self.encode_stream_name not in camera_config:
            raise RuntimeError(f"Encode stream {self.encode_stream_name} was not defined")

        # Allocate all the frame buffers.
        self.streams = [stream_config.stream for stream_config in libcamera_config]
        self.allocator = libcamera.FrameBufferAllocator(self.camera)
        for i, stream in enumerate(self.streams):
            if self.allocator.allocate(stream) < 0:
                raise RuntimeError("Failed to allocate buffers.")
            msg = f"Allocated {len(self.allocator.buffers(stream))} buffers for stream {i}."

        # Mark ourselves as configured.
        self.libcamera_config = libcamera_config
        self.camera_config = camera_config
        # Set the controls directly so as to overwrite whatever is there. No need for the lock
        # here as the camera is not running. Copy it so that subsequent calls to set_controls
        # don't become part of the camera_config.
        self.controls = self.camera_config['controls'].copy()
        self.configure_count += 1

    def camera_configuration(self) -> dict:
        """Return the camera configuration."""
        return self.camera_config

    def stream_configuration(self, name="main") -> dict:
        """Return the stream configuration for the named stream."""
        return self.camera_config[name]

    def list_controls(self):
        """List the controls supported by the camera."""
        return self.camera.controls

    def _handle_request(self):
        completed_request = self._process_requests()
        if completed_request:
            if self.display_stream_name is not None:
                with self.handle_lock:
                    self._outlet(Frame(completed_request.make_buffer("main")))
                    if self.current and self.own_current:
                        self.current.release()
                    self.current = completed_request
                # The pipeline will stall if there's only one buffer and we always hold on to
                # the last one. When we can, however, holding on to them is still preferred.
                config = self.camera_config
                if config is not None and config['buffer_count'] > 1:
                    self.own_current = True
                else:
                    self.own_current = False
                    completed_request.release()
            else:
                completed_request.release()

    def run(self) -> None:
        import selectors
        self.configure(self.create_configuration())
        if self.camera_config is None:
            raise RuntimeError("Camera has not been configured")
        if self.started:
            raise RuntimeError("Camera already started")
        if self.camera.start(self.controls) >= 0:
            for request in self._make_requests():
                self.camera.queue_request(request)
            sel = selectors.DefaultSelector()
            sel.register(self.camera_manager.efd, selectors.EVENT_READ, self._handle_request)
            self.started = True
            while self._is_running():
                events = sel.select(0.1)
                for key, mask in events:
                    callback = key.data
                    callback()

        else:
            raise RuntimeError("Camera did not start properly.")

    def stop_(self, request=None) -> None:
        """Stop the camera. Only call this function directly from within the camera event
        loop, such as in a Qt application."""
        if self.started:
            self.stop_count += 1
            if self.current is not None and self.own_current:
                self.current.release()
            self.camera.stop()
            self.camera_manager.get_ready_requests()  # Could anything here need flushing?
            self.started = False
            self.completed_requests = []
        return True

    def stop(self) -> None:
        """Stop the camera."""
        if not self.started:
            return
        self.stop_()

    def set_controls(self, controls) -> None:
        """Set camera controls. These will be delivered with the next request that gets submitted."""
        with self.controls_lock:
            for key, value in controls.items():
                self.controls[key] = value

    def _get_completed_requests(self) -> List[CompletedRequest]:
        # Return all the requests that libcamera has completed.
        data = os.read(self.camera_manager.efd, 8)
        requests = [CompletedRequest(req, self) for req in self.camera_manager.get_ready_requests()
                    if req.status == libcamera.Request.Status.Complete]
        return requests

    def _process_requests(self) -> None:
        # This is the function that the event loop, which runs externally to us, must
        # call.
        requests = self._get_completed_requests()
        if not requests:
            return

        # It works like this:
        # * We maintain a list of the requests that libcamera has completed (completed_requests).
        #   But we keep only a minimal number here so that we have one available to "return
        #   quickly" if an application asks for it, but the rest get recycled to libcamera to
        #   keep the camera system running.
        # * The lock here protects the completed_requests list (because if it's non-empty, an
        #   application can pop a request from it asynchronously).

        with self.lock:
            # These new requests all have one "use" recorded, which is the one for
            # being in this list.
            self.completed_requests += requests

            # This is the request we'll hand back to be displayed. This counts as a "use" too.
            display_request = self.completed_requests[-1]
            display_request.acquire()

            # We can only hang on to a limited number of requests here, most should be recycled
            # immediately back to libcamera. You could consider customising this number.
            # When there's only one buffer in total, don't hang on to anything as it would stall
            # the pipeline completely.
            max_len = 0 if self.camera_config['buffer_count'] == 1 else 1
            while len(self.completed_requests) > max_len:
                self.completed_requests.pop(0).release()

        # If one of the functions we ran reconfigured the camera since this request came out,
        # then we don't want it going back to the application as the memory is not valid.
        if display_request.configure_count != self.configure_count:
            display_request.release()
            display_request = None

        return display_request
