import hmac
import hashlib
import secrets


class Signature:
    """
    套接字数据加密解密
    """
    # 参数配置
    KEY_LENGTH = 32  # 256位密钥
    NONCE_LENGTH = 16
    HMAC_LENGTH = 32
    PBKDF2_ITER = 100_000

    @staticmethod
    def encrypt(data: bytes, sig_key: str = "hello") -> bytes:
        salt = secrets.token_bytes(16)
        nonce = secrets.token_bytes(Signature.NONCE_LENGTH)
        key = Signature.derive_key(salt + nonce, sig_key)
        ciphertext = Signature.stream_cipher(data, key)
        mac = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()

        # Magic header: b"ENC"
        return b"ENC" +  salt + nonce + ciphertext + mac

    @staticmethod
    def decrypt(data: bytes, sig_key: str = "hello") -> bytes:
        if not data.startswith(b"ENC"):
            raise ValueError("解密数据格式无效")

        salt = data[3:19]
        nonce = data[19:19 + Signature.NONCE_LENGTH]
        mac_offset = len(data) - Signature.HMAC_LENGTH
        ciphertext = data[19 + Signature.NONCE_LENGTH:mac_offset]
        mac = data[mac_offset:]

        key = Signature.derive_key(salt + nonce, sig_key)
        expected_mac = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()

        if not hmac.compare_digest(mac, expected_mac):
            raise ValueError("HMAC 认证失败, 数据可能已经被篡改或修改过.")

        return Signature.stream_cipher(ciphertext, key)

    @classmethod
    def derive_key(cls, salt: bytes, sig_key: str = "hello world") -> bytes:
        return hashlib.pbkdf2_hmac('sha256', sig_key.encode(), salt, Signature.PBKDF2_ITER, Signature.KEY_LENGTH)

    @classmethod
    def stream_cipher(cls, data: bytes, key: bytes) -> bytes:
        # 伪随机流加密（基于 key 生成伪随机字节流，和数据异或）
        keystream = hashlib.sha256(key).digest()
        output = bytearray()
        i = 0
        for b in data:
            if i >= len(keystream):
                keystream = hashlib.sha256(keystream).digest()
                i = 0
            output.append(b ^ keystream[i])
            i += 1
        return bytes(output)


