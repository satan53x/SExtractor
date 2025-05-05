"""regroup all struct functions"""
import struct

__author__ = "Matthieu Gallet"


def write_ushort(fd, obj):
    fd.write(struct.pack("<H", obj))


def write_sbyte(fd, obj):
    fd.write(struct.pack("b", obj))


def write_ubyte(fd, obj):
    fd.write(struct.pack("B", obj))


def read_ushort(fd):
    return struct.unpack("<H", fd.read(2))[0]


def read_sbyte(fd):
    return struct.unpack("b", fd.read(1))[0]


def read_ubyte(fd):
    return struct.unpack("B", fd.read(1))[0]
