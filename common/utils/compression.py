import msgpack
import zlib

def encode_dict(data: dict) -> bytes:
    packed = msgpack.packb(data, use_bin_type=True)
    return zlib.compress(packed)


def decode_dict(data: bytes) -> dict:
    unpacked = zlib.decompress(data)
    return msgpack.unpackb(unpacked, raw=False)
