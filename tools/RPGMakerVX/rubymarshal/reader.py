import io
import re

from rubymarshal.classes import (
    Extended,
    Module,
    RubyObject,
    RubyString,
    Symbol,
    UserDef,
    UsrMarshal,
)
from rubymarshal.classes import registry as global_registry
from rubymarshal.constants import (
    TYPE_ARRAY,
    TYPE_BIGNUM,
    TYPE_CLASS,
    TYPE_DATA,
    TYPE_EXTENDED,
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
    TYPE_STRUCT,
    TYPE_SYMBOL,
    TYPE_SYMLINK,
    TYPE_TRUE,
    TYPE_USERDEF,
    TYPE_USRMARSHAL,
)
from rubymarshal.utils import read_sbyte, read_ubyte, read_ushort

__author__ = "Matthieu Gallet"


class Reader:
    def __init__(self, fd, registry=None):
        self.symbols = []
        self.objects = []
        self.fd = fd
        self.registry = registry or global_registry

    def read(self, in_ivar=False):
        result = None
        object_index = None
        re_flags = None

        token = self.fd.read(1)

        # From https://docs.ruby-lang.org/en/2.1.0/marshal_rdoc.html:
        # The stream contains only one copy of each object for all objects except
        # true, false, nil, Fixnums and Symbols.
        if token in (
            # TYPE_EXTENDED, TYPE_UCLASS, ????
            TYPE_CLASS,
            TYPE_MODULE,
            TYPE_FLOAT,
            TYPE_BIGNUM,
            TYPE_STRING,
            TYPE_REGEXP,
            TYPE_ARRAY,
            TYPE_HASH,
            TYPE_STRUCT,
            TYPE_OBJECT,
            TYPE_DATA,
            TYPE_USRMARSHAL,
            TYPE_USERDEF,
        ):
            object_index = len(self.objects)
            # placeholder for incomplete type
            self.objects.append(None)

        if token == TYPE_NIL:
            pass
        elif token == TYPE_TRUE:
            result = True
        elif token == TYPE_FALSE:
            result = False
        elif token == TYPE_IVAR:
            result = self.read(in_ivar=True)
        elif token == TYPE_STRING:
            result = self.read_blob()
        elif token == TYPE_SYMBOL:
            result = self.read_symreal()
        elif token == TYPE_FIXNUM:
            result = self.read_long()
        elif token == TYPE_ARRAY:
            num_elements = self.read_long()
            # noinspection PyUnusedLocal
            result = [self.read() for x in range(num_elements)]
        elif token == TYPE_HASH:
            num_elements = self.read_long()
            result = {}
            for x in range(num_elements):
                key = self.ensure_hashable(self.read())
                value = self.read()
                result[key] = value
            result = result
        elif token == TYPE_FLOAT:
            floatn = self.read_blob()
            floatn = floatn.split(b"\0")
            result = float(floatn[0].decode("utf-8"))
        elif token == TYPE_BIGNUM:
            sign = 1 if self.fd.read(1) == b"+" else -1
            num_elements = self.read_long()
            result = 0
            factor = 1
            for x in range(num_elements):
                result += self.read_short() * factor
                factor *= 2**16
            result *= sign
        elif token == TYPE_REGEXP:
            result = self.read_blob()
            options = ord(self.fd.read(1))
            re_flags = 0
            if options & 1:
                re_flags |= re.IGNORECASE
            if options & 4:
                re_flags |= re.MULTILINE
        elif token == TYPE_USRMARSHAL:
            class_symbol = self.read()
            if not isinstance(class_symbol, Symbol):
                raise ValueError("invalid class name: %r" % class_symbol)
            class_name = class_symbol.name
            attr_list = self.read()
            python_class = self.registry.get(class_name, UsrMarshal)
            if not issubclass(python_class, UsrMarshal):
                raise ValueError(
                    "invalid class mapping for %r: %r should be a subclass of %r."
                    % (class_name, python_class, UsrMarshal)
                )
            result = python_class(class_name)
            result.marshal_load(attr_list)
        elif token == TYPE_SYMLINK:
            result = self.read_symlink()
        elif token == TYPE_LINK:
            link_id = self.read_long()
            if link_id > len(self.objects):
                raise ValueError(
                    "invalid link destination: %d should be lower than %d or equal."
                    % (link_id, len(self.objects))
                )
            # According to the documentation, objects are counted from 1.
            # But it looks like they did not take the outermost object into account.
            result = self.objects[link_id]
            if result is None:
                # link to incomplete object
                raise ValueError(
                    "invalid link destination: Object id %d is not yet unmarshaled."
                    % (link_id)
                )
        elif token == TYPE_USERDEF:
            class_symbol = self.read()
            private_data = self.read_blob()
            if not isinstance(class_symbol, Symbol):
                raise ValueError("invalid class name: %r" % class_symbol)
            class_name = class_symbol.name
            python_class = self.registry.get(class_name, UserDef)
            if not issubclass(python_class, UserDef):
                raise ValueError(
                    "invalid class mapping for %r: %r should be a subclass of %r."
                    % (class_name, python_class, UserDef)
                )
            result = python_class(class_name)
            # noinspection PyProtectedMember
            result._load(private_data)
        elif token == TYPE_MODULE:
            data = self.read_blob()
            module_name = data.decode()
            result = Module(module_name, None)
        elif token == TYPE_OBJECT:
            class_symbol = self.read()
            assert isinstance(class_symbol, Symbol)
            class_name = class_symbol.name
            python_class = self.registry.get(class_name, RubyObject)
            if not issubclass(python_class, RubyObject):
                raise ValueError(
                    "invalid class mapping for %r: %r should be a subclass of %r."
                    % (class_name, python_class, RubyObject)
                )
            attributes = self.read_attributes()
            result = python_class(class_name, attributes)
        elif token == TYPE_EXTENDED:
            class_name = self.read_blob()
            result = Extended(class_name, None)
        elif token == TYPE_CLASS:
            data = self.read_blob()
            class_name = data.decode()
            if class_name in self.registry:
                result = self.registry[class_name]
            else:
                result = type(
                    class_name.rpartition(":")[2],
                    (RubyObject,),
                    {"ruby_class_name": class_name},
                )
        else:
            raise ValueError("token %s is not recognized" % token)

        if in_ivar:
            # The object has attributes.
            attributes = self.read_attributes()
            if token in (TYPE_STRING, TYPE_REGEXP):
                encoding = self._get_encoding(attributes)
                try:
                    result = result.decode(encoding)
                except UnicodeDecodeError:
                    result = result.decode("unicode-escape")
                # string instance attributes are discarded (on regex?)
                if attributes and token == TYPE_STRING:
                    result = RubyString(result, attributes)
            elif attributes:
                result.set_attributes(attributes)

        if token == TYPE_REGEXP:
            result = re.compile(str(result), re_flags)

        if object_index is not None:
            self.objects[object_index] = result
        return result

    @staticmethod
    def _get_encoding(attrs):
        encoding = "latin1"
        if attrs.get("E") is True:
            encoding = "utf-8"
        elif "encoding" in attrs:
            encoding = attrs["encoding"].decode()
        return encoding

    def read_attributes(self):
        attr_count = self.read_long()
        attrs = {}
        for x in range(attr_count):
            attr_name = self.read()
            attr_value = self.read()
            attrs[attr_name.name] = attr_value
        return attrs

    def read_short(self):
        return read_ushort(self.fd)

    def read_long(self):
        length = read_sbyte(self.fd)
        if length == 0:
            return 0
        if 5 < length < 128:
            return length - 5
        elif -129 < length < -5:
            return length + 5
        result = 0
        factor = 1
        for s in range(abs(length)):
            result += read_ubyte(self.fd) * factor
            factor *= 256
        if length < 0:
            result = result - factor
        return result

    def read_blob(self):
        size = self.read_long()
        return self.fd.read(size)

    def read_symbol(self):
        ivar = 0
        while True:
            token = self.fd.read(1)
            if token == TYPE_IVAR:
                ivar = 1
                continue
            elif token == TYPE_SYMBOL:
                return self.read_symreal()
            elif token == TYPE_SYMLINK:
                if ivar:
                    raise ValueError("dump format error (symlink with encoding)")
                return self.read_symlink()
            raise ValueError("error while reading symbol with token %r" % token)

    def read_symlink(self):
        symlink_id = self.read_long()
        return self.symbols[symlink_id]

    def read_symreal(self):
        result = self.read_blob()
        result = Symbol(result.decode("utf-8"))
        self.symbols.append(result)
        return result

    def ensure_hashable(self, value):
        """Convert unhashable objects to hashable ones.

        Currently only patches list objects  https://github.com/d9pouces/RubyMarshal/issues/10 .
        """
        if isinstance(value, list):
            return tuple(self.ensure_hashable(x) for x in value)
        return value


def load(fd, registry=None):
    if fd.read(1) != b"\x04":
        raise ValueError(r"Expected token \x04")
    if fd.read(1) != b"\x08":
        raise ValueError(r"Expected token \x08")

    loader = Reader(fd, registry=registry)
    return loader.read()


def loads(byte_text, registry=None):
    return load(io.BytesIO(byte_text), registry=registry)
