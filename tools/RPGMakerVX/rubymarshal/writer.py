import io
import math
import re

from rubymarshal.classes import (
    Module,
    RubyObject,
    RubyString,
    Symbol,
    UserDef,
    UsrMarshal,
)
from rubymarshal.constants import (
    TYPE_ARRAY,
    TYPE_BIGNUM,
    TYPE_CLASS,
    TYPE_FALSE,
    TYPE_FIXNUM,
    TYPE_FLOAT,
    TYPE_HASH,
    TYPE_IVAR,
    TYPE_LINK,
    TYPE_MODULE,
    TYPE_NIL,
    TYPE_OBJECT,
    TYPE_REGEXP,
    TYPE_STRING,
    TYPE_SYMBOL,
    TYPE_SYMLINK,
    TYPE_TRUE,
    TYPE_USERDEF,
    TYPE_USRMARSHAL,
)
from rubymarshal.utils import write_sbyte, write_ubyte, write_ushort

__author__ = "Matthieu Gallet"

re_class = re.compile("").__class__
simple_float_re = re.compile(r"^\d+\.\d*0+$")


class Writer:
    def __init__(self, fd):
        self.symbols = {}
        self.objects = {}
        self.fd = fd

    def write(self, obj):
        if obj is None:
            self.write_none()
        elif obj is False:
            self.write_false()
        elif obj is True:
            self.write_true()
        elif isinstance(obj, int):
            self.write_int(obj)
        elif isinstance(obj, Symbol):
            self.write_symbol(obj)
        elif isinstance(obj, list):
            self.write_list(obj)
        elif isinstance(obj, dict):
            self.write_dict(obj)
        elif isinstance(obj, bytes):
            self.write_bytes(obj)
        elif isinstance(obj, str):
            self.write_string(obj)
        elif isinstance(obj, RubyString):
            self.write_ruby_string(obj)
        elif isinstance(obj, float):
            self.write_float(obj)
        elif isinstance(obj, re_class):
            self.write_regexp(obj)
        elif isinstance(obj, Module):
            self.write_module(obj)
        elif isinstance(obj, UsrMarshal):
            self.write_usr_marshal(obj)
        elif isinstance(obj, UserDef):
            self.write_user_def(obj)
        elif isinstance(obj, RubyObject):
            self.write_ruby_object(obj)
        elif isinstance(obj, type) and issubclass(obj, RubyObject):
            self.write_class(obj)
        else:
            self.write_python_object(obj)

    def write_python_object(self, obj):
        """override this method to dump new Python classes"""
        raise ValueError("unmarshable object: %s(%r)" % (obj.__class__.__name__, obj))

    def write_true(self):
        self.fd.write(TYPE_TRUE)

    def write_false(self):
        self.fd.write(TYPE_FALSE)

    def write_none(self):
        self.fd.write(TYPE_NIL)

    def write_class(self, obj):
        self.fd.write(TYPE_CLASS)
        self.write_long(len(obj.ruby_class_name.encode()))
        self.fd.write(obj.ruby_class_name.encode())

    def write_ruby_object(self, obj):
        if self.must_write(obj):
            self.fd.write(TYPE_OBJECT)
            self.write(Symbol(obj.ruby_class_name))
            if not isinstance(obj.attributes, dict):
                raise ValueError("%r values is not a dict" % obj)
            self.write_attributes(obj.attributes)

    def write_user_def(self, obj):
        if self.must_write(obj):
            if obj.attributes:
                self.fd.write(TYPE_IVAR)
            self.fd.write(TYPE_USERDEF)
            self.write(Symbol(obj.ruby_class_name))
            # noinspection PyProtectedMember
            bdata = obj._dump()
            self.write_long(len(bdata))
            self.fd.write(bdata)
            if obj.attributes:
                self.write_attributes(obj.attributes)

    def write_usr_marshal(self, obj):
        if self.must_write(obj):
            if obj.attributes:
                self.fd.write(TYPE_IVAR)
            self.fd.write(TYPE_USRMARSHAL)
            self.write(Symbol(obj.ruby_class_name))
            private_data = obj.marshal_dump()
            self.write(private_data)
            if obj.attributes:
                self.write_attributes(obj.attributes)

    def write_module(self, obj):
        self.fd.write(TYPE_MODULE)
        self.write_long(len(obj.ruby_class_name.encode()))
        self.fd.write(obj.ruby_class_name.encode())

    def write_regexp(self, obj):
        flags = 0
        if obj.flags & re.IGNORECASE:
            flags += 1
        if obj.flags & re.MULTILINE:
            flags += 4
        self.fd.write(TYPE_IVAR)
        self.fd.write(TYPE_REGEXP)
        pattern = obj.pattern.encode("utf-8")
        self.write_long(len(pattern))
        self.fd.write(pattern)
        write_ubyte(self.fd, flags)
        self.write_long(1)
        self.write(Symbol("E"))
        self.write(False)

    def write_float(self, obj):
        obj = "%.20g" % obj
        if simple_float_re.match(obj):
            while obj.endswith("0"):
                obj = obj[:-1]
        obj = obj.encode("utf-8")
        self.fd.write(TYPE_FLOAT)
        self.write_long(len(obj))
        self.fd.write(obj)

    def write_ruby_string(self, obj):
        if self.must_write(obj):
            encoding = "utf-8"
            attributes = obj.attributes
            if "E" in attributes and not attributes["E"]:
                encoding = "latin-1"
            elif "encoding" in attributes:
                encoding = attributes["encoding"].decode()
            else:
                attributes["E"] = True
            encoded = obj.encode(encoding)
            self.fd.write(TYPE_IVAR)
            self.write_bytes(encoded)
            self.write_attributes(attributes)

    def write_string(self, obj):
        obj = obj.encode("utf-8")
        self.fd.write(TYPE_IVAR)
        self.write_bytes(obj)
        self.write_long(1)
        self.write(Symbol("E"))
        self.write(True)

    def write_bytes(self, obj):
        self.fd.write(TYPE_STRING)
        self.write_long(len(obj))
        self.fd.write(obj)

    def write_dict(self, obj):
        if self.must_write(obj):
            self.fd.write(TYPE_HASH)
            self.write_long(len(obj))
            for key, value in obj.items():
                self.write(key)
                self.write(value)

    def write_list(self, obj):
        if self.must_write(obj):
            self.fd.write(TYPE_ARRAY)
            self.write_long(len(obj))
            for x in obj:
                self.write(x)

    def write_symbol(self, obj):
        if obj.name in self.symbols:
            self.fd.write(TYPE_SYMLINK)
            self.write_long(self.symbols[obj.name])
        else:
            self.fd.write(TYPE_SYMBOL)
            symbol_index = len(self.symbols)
            self.symbols[obj.name] = symbol_index
            encoded = obj.name.encode("utf-8")
            self.write_long(len(encoded))
            self.fd.write(encoded)

    def write_int(self, obj):
        if obj.bit_length() <= 5 * 8:
            self.fd.write(TYPE_FIXNUM)
            # noinspection PyTypeChecker
            self.write_long(obj)
        else:
            self.fd.write(TYPE_BIGNUM)
            if obj < 0:
                self.fd.write(b"-")
            else:
                self.fd.write(b"+")
            obj = abs(obj)
            size = int(math.ceil(obj.bit_length() / 16.0))
            self.write_long(size)
            for i in range(size):
                self.write_short(obj % 65536)
                obj //= 65536

    def write_attributes(self, attributes):
        self.write_long(len(attributes))
        for attr_name, attr_value in attributes.items():
            self.write(Symbol(attr_name))
            self.write(attr_value)

    def write_short(self, obj):
        write_ushort(self.fd, obj)

    def write_long(self, obj):
        if obj == 0:
            self.fd.write(b"\0")
        elif 0 < obj < 123:
            write_sbyte(self.fd, obj + 5)
        elif -124 < obj < 0:
            write_sbyte(self.fd, obj - 5)
        else:
            size = int(math.ceil(obj.bit_length() / 8.0))
            if size > 5:
                raise ValueError("%d too long for serialization" % obj)
            original_obj = obj
            factor = 256**size
            if obj < 0 and obj == -factor:
                size -= 1
                obj += factor / 256
            elif obj < 0:
                obj += factor
            sign = int(math.copysign(size, original_obj))
            write_sbyte(self.fd, sign)
            for i in range(size):
                write_ubyte(self.fd, obj % 256)
                obj //= 256

    def must_write(self, obj):
        """return False if the object has already been serialized (and write a link to it),
        otherwise return True"""
        if id(obj) in self.objects:
            self.fd.write(TYPE_LINK)
            self.write_long(self.objects[id(obj)])
            return False
        else:
            link_index = len(self.objects)
            self.objects[id(obj)] = link_index
            return True


def write(fd, obj, cls=Writer):
    """write an Python object to a file descriptor

    :param fd: the file descriptor
    :param obj: the object to serialize
    :param cls: Writer class to use. Subclass it to serialize new Python classes
    """
    fd.write(b"\x04\x08")
    writer = cls(fd)
    writer.write(obj)


def writes(obj, cls=Writer):
    """write an Python object to a bytes string

    :param obj: the object to serialize
    :param cls: Writer class to use. Subclass it to serialize new Python classes
    """
    fd = io.BytesIO()
    write(fd, obj, cls=cls)
    return fd.getvalue()
