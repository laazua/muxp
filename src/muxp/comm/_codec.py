import json
from typing import Any, Dict

class JSONCodec:
    @staticmethod
    def encode(obj: Dict[Any, Any]) -> bytes:
        return json.dumps(obj).encode('utf-8')

    @staticmethod
    def decode(data: bytes) -> Any:
        return json.loads(data.decode('utf-8'))
