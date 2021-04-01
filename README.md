# actfw-raspberrypi

actfw's components for Raspberry Pi.
actfw is a framework for Actcast Application written in Python.

## Installation

```console
sudo apt-get update
sudo apt-get install -y python3-pip python3-pil 
pip3 install actfw-raspberrypi
```

## Document

* [API References](https://idein.github.io/actfw-raspberrypi/latest/)

## Usage

See [actfw-core](https://github.com/Idein/actfw-core) for basic usage.

actfw-raspberrypi provides:

* `actfw_raspberrypi.capture.PiCameraCapture` : Generate CSI camera capture image
* `actfw_raspberrypi.Display` : Display using PiCamera Overlay
* `actfw_raspberrypi.vc4.Display` : Display using VideoCore IV
* `actfw_raspberrypi.vc4.Window` : Double buffered window

## Example

* `example/hello` : The most simple application example
  * Use HDMI display as 640x480 area
  * Capture 320x240 RGB image from CSI camera
  * Draw "Hello, Actcast!" text
  * Display it as 640x480 image (with x2 scaling)
  * Notice message for each frame
  * Support application setting
  * Support application heartbeat
  * Support "Take Photo" command
  * Depends: python3-picamera fonts-dejavu-core
* `example/grayscale` : Next level application example
  * Use HDMI display as 640x480 area
  * Capture 320x240 RGB image from CSI camera
  * Convert it to grayscale
  * Display it as 640x480 image (with x2 scaling)
  * Notice message for each frame
  * Support application setting
  * Support application heartbeat
  * Support "Take Photo" command
  * Depends: python3-picamera
* `example/parallel_grayscale` : Paralell processing application example
  * Use HDMI display as 640x480 area
  * Capture 320x240 RGB image from CSI camera
  * Convert it to grayscale
    * There exists 2 converter task
    * Round-robin task scheduling
  * Display it as 640x480 image (with x2 scaling)
  * Notice message for each frame
    * Show which converter processes image
  * Support application setting
  * Support application heartbeat
  * Support "Take Photo" command
  * Depends: python3-picamera
* `example/uvccamera` : UVC camera capture example
  * `picamera` is unnecessary
  * Use HDMI display center 640x480 area
  * Capture 320x240 RGB image from UVC camera
  * Convert it to grayscale
  * Display it as 640x480 image (with x2 scaling)
  * Notice grayscale pixel data histogram
  * Support application setting
  * Support application heartbeat
  * Support "Take Photo" command
  * Depends: libv4l-0 libv4lconvert0

## Development Guide

### Installation of dev requirements

```console
pip3 install poetry
poetry install
```

### Running tests

```console
poetry run nose2 -v
```

### Running examples

On a Raspberry Pi connected to HDMI display:

```console
poetry run python example/hello
```

### Releasing package & API doc

CI will automatically do.
Follow the following branch/tag rules.

1. Make changes for next version in `master` branch (via pull-requests).
2. Make a PR that updates version in `pyproject.toml` and merge it to `master` branch.
3. Create Git tag from `master` branch's HEAD named `release-<New version>`. E.g. `release-1.4.0`.
4. Then CI will build/upload package to PyPI & API doc to GitHub Pages.
