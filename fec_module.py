"""
fec_module.py — Forward Error Correction for QVSC

Sits between Module 2 (ChaCha20-Poly1305 ciphertext) and Module 4 (embedding)
on the sender side, and between Module 5 (bit extraction) and Module 6
(decryption) on the receiver side.

WHY THIS EXISTS
---------------
The DCT-QIM channel is near-lossless but NOT bit-exact: the uint8 color-space
round-trip and H.264 compression flip a small fraction of bits. Because the
payload is ChaCha20-Poly1305 (AEAD), even ONE wrong bit makes the Poly1305 tag
fail and the whole message is rejected. So we need to deliver the ciphertext
bit-exact. Reed-Solomon (operating on bytes over GF(256)) corrects the residual
errors; block interleaving spreads H.264's clustered errors across many

codewords so each codeword only sees a few correctable symbol errors.
"""
import numpy as np
from reedsolo import RSCodec

# RS(N, K): N-byte codewords carrying K data bytes + (N-K) parity bytes.
# Corrects up to (N-K)/2 byte errors per codeword.
# Defaults: 32 parity -> corrects 16 byte-errors per 255-byte block (~6%).
# For harsher compression (high CRF), raise RS_PARITY (e.g. 64, 96).
RS_N      = 255
# RS_PARITY = 32
RS_PARITY = 64
RS_K      = RS_N - RS_PARITY            # 223 data bytes per codeword
_rsc      = RSCodec(RS_PARITY)


def fec_encode(data: bytes) -> bytes:
    """
    Sender side. Wrap raw ciphertext bytes in Reed-Solomon + interleaving.

    Layout before encoding: [4-byte big-endian length][data][zero padding]
    The length header lives INSIDE the RS protection, so the receiver can
    strip padding even if a few bytes were corrupted.
    """
    blob = len(data).to_bytes(4, 'big') + data
    pad  = (-len(blob)) % RS_K
    blob += b'\x00' * pad

    # RS-encode each K-byte chunk into an N-byte codeword
    codewords = [bytes(_rsc.encode(blob[i:i + RS_K]))
                 for i in range(0, len(blob), RS_K)]
    ncw = len(codewords)

    # Block interleave: stack codewords as (ncw x N), transmit COLUMN by column.
    # A burst of channel errors then lands one symbol in many codewords instead
    # of wiping out a single codeword.
    matrix      = np.frombuffer(b''.join(codewords), np.uint8).reshape(ncw, RS_N)
    interleaved = matrix.T.reshape(-1)          # column-major read-out
    return interleaved.tobytes()


def fec_decode(payload: bytes):
    """
    Receiver side. Inverse of fec_encode(). Returns (recovered_ciphertext,
    n_codewords_failed). If n_codewords_failed == 0 the ciphertext is bit-exact
    and ready for ChaCha20-Poly1305.
    """
    arr = np.frombuffer(payload, np.uint8)
    ncw = len(arr) // RS_N
    arr = arr[:ncw * RS_N]

    # De-interleave: undo the column-major read-out
    matrix = arr.reshape(RS_N, ncw).T           # back to (ncw x N)

    recovered = bytearray()
    failures  = 0
    for row in matrix:
        try:
            recovered += bytes(_rsc.decode(bytes(row))[0])
        except Exception:
            failures += 1
            recovered += bytes(row[:RS_K])      # give back uncorrected chunk
    blob   = bytes(recovered)
    length = int.from_bytes(blob[:4], 'big')
    return blob[4:4 + length], failures


def fec_overhead(data_len: int) -> dict:
    """Report how big the protected payload will be."""
    blob = 4 + data_len
    ncw  = (blob + RS_K - 1) // RS_K
    return {'data_bytes': data_len, 'codewords': ncw,
            'fec_bytes': ncw * RS_N, 'fec_bits': ncw * RS_N * 8,
            'redundancy_pct': round(100 * RS_PARITY / RS_N, 1)}
