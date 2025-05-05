import typing
import base64
from typing import Type

__author__ = "Matthieu Gallet"

def to_dict(obj):
    if isinstance(obj, RubyObject):
        return obj.to_dict()
    elif isinstance(obj, Symbol):
        return obj.to_dict()
    elif isinstance(obj, dict):
        return {to_dict(k): to_dict(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [to_dict(item) for item in obj]
    elif isinstance(obj, bytes):
        return { "bytes": base64.b64encode(obj).decode('ascii') }
    else:
        return obj

def from_dict(data):
    if isinstance(data, dict):
        if 'class' in data:
            class_name = data['class']
            if class_name in class_type:
                obj = class_type[class_name].from_dict(data)
                return obj
            else:
                raise ValueError(f"Unknown class name : {class_name}")
        elif 'ruby_class' in data:
            return RubyObject.from_dict(data)
        elif 'bytes' in data:
            if len(data) != 1:
                raise ValueError("Invalid format for bytes field")
            return base64.b64decode(data['bytes'])
        else:
            return { k: from_dict(v) for k, v in data.items() }
    elif isinstance(data, list):
        return [from_dict(item) for item in data]
    elif isinstance(data, str):
            return data
    else:
        return data

class RubyObject:
    ruby_class_name = None

    def __init__(self, ruby_class_name=None, attributes=None):
        self.ruby_class_name = ruby_class_name or self.ruby_class_name
        self.attributes = attributes or {}

    def set_attributes(self, attributes):
        self.attributes = attributes

    def __eq__(self, other):
        return isinstance(other, self.__class__) and self.attributes == other.attributes

    def __hash__(self):
        if isinstance(self.attributes, typing.Hashable):
            hashed = hash(self.attributes)
        else:
            hashed = hash(repr(self.attributes))
        return hash(f"{self.ruby_class_name} {hashed}")

    def __repr__(self):
        return "%s(%r)" % (self.__class__.__name__, self.attributes)

    def __str__(self):
        return "%s(%r)" % (self.__class__.__name__, self.attributes)

    def to_dict(self):
        data = { "ruby_class": self.ruby_class_name }
        attrs = to_dict(self.attributes)
        for k, v in attrs.items():
            data[k] = v
        return data
    
    @classmethod
    def from_dict(cls, dic):
        attrs = {}
        for k, v in dic.items():
            if k.startswith("@"):
                #attr
                attrs[k] = from_dict(v)
        return cls(dic["ruby_class"], attrs)

class RubyString(RubyObject):
    def __init__(self, text: str, attributes=None):
        self.text = text
        super().__init__("str", attributes=attributes)

    def __eq__(self, other):
        if isinstance(other, str):
            return self.text == other
        elif isinstance(other, RubyString):
            return self.text == other.text and self.attributes == other.attributes
        return False

    def __ne__(self, other):
        if isinstance(other, str):
            return self.text != other
        elif isinstance(other, RubyString):
            return self.text != other.text or self.attributes != other.attributes
        return False

    def __getattr__(self, item):
        return getattr(self.text, item)

    def __add__(self, other):
        return RubyString(self.text + str(other), self.attributes)

    def __hash__(self):
        return hash(self.text)

    def __repr__(self):
        return repr(self.text)

    def __str__(self):
        return self.text

    def __lt__(self, other):
        return self.text < other

    def __gt__(self, other):
        return self.text > other

    def __le__(self, other):
        return self.text <= other

    def __ge__(self, other):
        return self.text >= other

    def __iter__(self):
        yield from self.text

    def __bool__(self):
        return bool(self.text)

    def __getitem__(self, item):
        return self.text[item]

    def __len__(self):
        return len(self.text)

    def to_dict(self):
        return self.text
    
    @classmethod
    def from_dict(cls, text):
        return cls(text) #str转RubyString

class UsrMarshal(RubyObject):
    """object with a user-defined serialization format using the marshal_dump and marshal_load instance methods.
    Upon loading a new instance must be allocated and marshal_load must be called on the instance with the data."""

    def __init__(self, ruby_class_name=None, attributes=None):
        self._private_data = None
        super().__init__(ruby_class_name=ruby_class_name, attributes=attributes)

    def marshal_load(self, private_data):
        self._private_data = private_data

    def marshal_dump(self):
        return self._private_data

    def to_dict(self):
        data = super().to_dict()
        data["data"] = to_dict(self._private_data)
        data["class"] = "UsrMarshal"
        return data
    
    @classmethod
    def from_dict(cls, dic):
        obj = super().from_dict(dic)
        obj._private_data = from_dict(dic["data"])
        return obj

class UserDef(RubyObject):
    """object with a user-defined serialization format using the _dump instance method and _load class method.

    data is a byte sequence containing the user-defined representation of the object.

    The class method _load is called on the class with a string created from the byte-sequence."""

    def __init__(self, ruby_class_name=None, attributes=None):
        self._private_data = None
        super().__init__(ruby_class_name=ruby_class_name, attributes=attributes)

    def _load(self, private_data: bytes):
        self._private_data = private_data

    def _dump(self) -> bytes:
        return self._private_data
    
    def to_dict(self):
        data = super().to_dict()
        data["data"] = to_dict(self._private_data)
        data["class"] = "UserDef"
        return data
    
    @classmethod
    def from_dict(cls, dic):
        obj = super().from_dict(dic)
        obj._private_data = from_dict(dic["data"])
        return obj

class Extended(RubyObject):
    def to_dict(self):
        data = super().to_dict()
        data["class"] = "Extended"
        return data

class Module(RubyObject):
    def to_dict(self):
        data = super().to_dict()
        data["class"] = "Module"
        return data


class Symbol:
    __registered_symbols__ = {}

    def __new__(cls, name):
        if name in cls.__registered_symbols__:
            return cls.__registered_symbols__[name]
        return super(Symbol, cls).__new__(cls)

    def __init__(self, name):
        self.name = name
        self.__registered_symbols__[name] = self

    def __hash__(self):
        return hash("<<<:%s:>>>" % self.name)

    def __repr__(self):
        return 'Symbol("%s")' % self.name

    def __str__(self):
        return ":%s" % self.name

    def encode(self, *args, **kwargs):
        return self.name.encode(*args, **kwargs)
    
    def to_dict(self):
        return { "class": "Symbol", "name": self.name}
    
    @classmethod
    def from_dict(cls, dic):
        return cls(dic["name"])


class ClassRegistry:
    def __init__(self):
        self._registry = {}

    def register(self, cls: Type[RubyObject]):
        assert issubclass(cls, RubyObject)
        self._registry[cls.ruby_class_name] = cls

    def unregister(self, cls: Type[RubyObject]):
        assert issubclass(cls, RubyObject)
        if cls.ruby_class_name in self._registry:
            del self._registry[cls.ruby_class_name]

    def get(self, ruby_class_name: str, default_cls: Type[RubyObject]):
        return self._registry.get(ruby_class_name, default_cls)

    def __contains__(self, item):
        return item in self._registry

    def __getitem__(self, item):
        return self._registry[item]

    def __delitem__(self, key):
        del self._registry[key]


registry = ClassRegistry()
class_type = {
    "UsrMarshal": UsrMarshal,
    "UserDef": UserDef,
    "Extended": Extended,
    "Module": Module,
    "Symbol": Symbol
}
