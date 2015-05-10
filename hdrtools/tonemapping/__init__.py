import sys
import subprocess
import numpy as np
import numpy.linalg as linalg
import hdrio
from itertools import chain
from functools import partial

# sRGB, D65 (same as pfstools)
rgb2xyz_mat = np.array([[0.412453, 0.357580, 0.180423],
                         [0.212671, 0.715160, 0.072169],
                         [0.019334, 0.119193, 0.950227]], dtype="float32")
xyz2rgb_mat = linalg.inv(rgb2xyz_mat)

_availToneMappers = subprocess.check_output(["compgen -c pfstmo"], stderr=subprocess.STDOUT, shell=True).decode('ascii').strip().split("\n")


def convertToXYZ(rgbimg):
    # Normalize RGB
    rgbimg /= rgbimg.max()
    rgbimg = np.clip(rgbimg, 0.0, 1.0)

    # Convert to XYZ (sRGB, D65)
    pixelVec = rgbimg.reshape(-1, 3)

    # Convert float32 (mandatory for PFS)
    imgXYZ = np.dot(rgb2xyz_mat, pixelVec.T).T.reshape(rgbimg.shape).astype("float32")

    return imgXYZ


def convertFromXYZ(xyzimg):
    # Convert XYZ to RGB
    pixelVec = xyzimg.reshape(-1, 3)
    img = np.dot(xyz2rgb_mat, pixelVec.T).T.reshape(xyzimg.shape)

    # The image will be returned with RGB values in the [0, 1] range, type=float32 !
    return img


def writePFS(hdrimg):
    """
    Return a bytes object encapsulating the hdrimg given as argument,
    including a valid header.
    The hdrimg should be a valid RGB image (HDR or not).
    """
    header = "PFS1\n{} {}\n{}\n0\nX\n0\nY\n0\nZ\n0\nENDH".format(hdrimg.shape[1], hdrimg.shape[0], hdrimg.shape[2])
    b = bytes(header, "ascii")

    imgXYZ = convertToXYZ(hdrimg)
    for c in range(imgXYZ.shape[2]):
        b += imgXYZ[..., c].tobytes()
    return b


def readPFS(data):
    """
    Return the image (HDR or not contained in the PFS data). The data argument
    should be a bytes object or an equivalent (bytearray, etc.) containing the
    PFS output, including the header.
    """
    headerEnd = data.find(b"\nENDH") + 5
    assert headerEnd != 4, "Invalid PFS file (no header end marker)!"

    headerLines = data[:headerEnd].decode('ascii').split("\n")

    # Read the header and extract width, height, and number of channels
    # TODO : Use the LUMINANCE tag from PFS? Is it useful?
    assert "PFS1" in headerLines[0], "Invalid PFS file (no PFS1 identifier)!"
    w, h = map(int, headerLines[1].split())
    channelsCount = int(headerLines[2])
    shape = (h, w, channelsCount)

    # Create the output image
    img = np.empty(shape)

    # Fill it with values from PFS
    p = headerEnd
    s = w * h * 4   # 4 = sizeof(float32)
    for c in range(channelsCount):
        img[..., c] = np.fromstring(data[p:p+s], dtype='float32').reshape((w, h))
        p += s

    # Return its RGB representation
    return convertFromXYZ(img)


def _tonemapping(hdrimg, exec_, **kwargs):
    inPFS = writePFS(hdrimg)

    listArgs = []
    for k,v in kwargs.items():
        listArgs.append("--"+str(k))
        listArgs.append(str(v))

    p = subprocess.Popen([exec_]+listArgs, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    output, err = p.communicate(inPFS)

    ldrimgRGB = readPFS(output)
    ldrimgRGB *= 255
    ldrimgRGB = np.clip(ldrimgRGB, 0, 255).astype('uint8')

    return ldrimgRGB

def getAvailableToneMappers():
    """
    Return the available tone mappers on the current platform,
    as a list of strings. These names are the ones that should be
    used as function names to actually use these tone mappers.
    """
    return [tm[7:] for tm in _availToneMappers]


# Dynamically create the tone mapping functions
for tm,tmName in zip(_availToneMappers, getAvailableToneMappers()):
    setattr(sys.modules[__name__], tmName, partial(_tonemapping, exec_=tm))

