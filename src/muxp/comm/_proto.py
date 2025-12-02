import struct
from typing import Tuple, List

_HEAD_SIZE = 4

def encode_data(data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + data

def decode_data(data: bytes) -> Tuple[List[bytes], bytes]:
    messages: List[bytes] = []
    offset = 0
    while len(data) - offset >= _HEAD_SIZE:
        length = struct.unpack(">I", data[offset:offset + _HEAD_SIZE])[0]
        if len(data) - offset - _HEAD_SIZE >= length:
            start = offset + _HEAD_SIZE
            end = start + length
            messages.append(data[start:end])
            offset = end
        else:
            break
    return messages, data[offset:]
