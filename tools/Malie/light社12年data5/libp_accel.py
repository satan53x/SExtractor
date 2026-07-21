#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
libp_accel.py — Camellia-128 加速插件
======================================
优先级: C 扩展 > numpy > 纯 Python (不加载本模块)

C 扩展编译:
  gcc -O2 -shared -o libp_camellia.dll libp_camellia.c     (Windows MinGW)
  gcc -O2 -shared -o libp_camellia.so  libp_camellia.c     (Linux)
  cl /O2 /LD libp_camellia.c                               (MSVC)

放在 libp_tool.py 同目录, 自动检测并启用。
"""

import ctypes, struct, time, os, sys, platform

# ═══════════════════════════════════════════════════════════════
#  C 扩展加载
# ═══════════════════════════════════════════════════════════════

_lib = None
_accel_mode = None  # 'c' or 'numpy'

def _find_c_lib():
    """在同目录下找 libp_camellia.dll/.so"""
    d = os.path.dirname(os.path.abspath(__file__))
    if platform.system() == 'Windows':
        names = ['libp_camellia.dll', 'libp_camellia.pyd']
    else:
        names = ['libp_camellia.so']
    for name in names:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return None

def _load_c_lib():
    global _lib
    path = _find_c_lib()
    if not path:
        return False
    try:
        _lib = ctypes.cdll.LoadLibrary(path)
        # 设置函数签名
        _lib.camellia_decrypt.argtypes = [
            ctypes.c_char_p, ctypes.c_int,
            ctypes.POINTER(ctypes.c_uint32), ctypes.c_uint64]
        _lib.camellia_decrypt.restype = ctypes.c_int
        _lib.camellia_encrypt.argtypes = [
            ctypes.c_char_p, ctypes.c_int,
            ctypes.POINTER(ctypes.c_uint32), ctypes.c_uint64]
        _lib.camellia_encrypt.restype = ctypes.c_int
        _lib.camellia_version.restype = ctypes.c_char_p
        ver = _lib.camellia_version().decode()
        print(f'[加速] C 扩展已加载: {ver}')
        return True
    except Exception as e:
        print(f'[提示] C 扩展加载失败: {e}')
        _lib = None
        return False

# ═══════════════════════════════════════════════════════════════
#  C 版 加解密
# ═══════════════════════════════════════════════════════════════

_CHUNK = 64 * 1024 * 1024  # 64MB 分块, 用于进度显示

def _make_kt_arr(kt):
    """Python list → ctypes uint32 array"""
    arr = (ctypes.c_uint32 * 52)(*[x & 0xFFFFFFFF for x in kt[:52]])
    return arr

def decrypt_data_c(data, kt, offset=0):
    total = len(data)
    aligned = (total // 16) * 16
    if aligned == 0:
        return bytearray(data)
    buf = bytearray(data[:aligned])
    kt_arr = _make_kt_arr(kt)
    t0 = time.time()
    n_chunks = (aligned + _CHUNK - 1) // _CHUNK
    for ci, start in enumerate(range(0, aligned, _CHUNK)):
        end = min(start + _CHUNK, aligned)
        chunk_len = end - start
        chunk_ptr = (ctypes.c_char * chunk_len).from_buffer(buf, start)
        _lib.camellia_decrypt(chunk_ptr, chunk_len, kt_arr, ctypes.c_uint64(offset + start))
        elapsed = time.time() - t0
        mb_done = end / 1048576; mb_total = aligned / 1048576
        speed = mb_done / max(elapsed, 0.001)
        eta = (mb_total - mb_done) / max(speed, 0.1)
        print(f'\r[C解密] {ci+1}/{n_chunks} 块 '
              f'({mb_done:.0f}/{mb_total:.0f} MB) '
              f'{elapsed:.0f}s [{speed:.0f} MB/s, 剩余 ~{eta:.0f}s]',
              end='', flush=True)
    elapsed = time.time() - t0
    print(f'\r[C解密] 完成 {aligned/1048576:.1f} MB, '
          f'{elapsed:.1f}s ({aligned/1048576/max(elapsed,0.001):.0f} MB/s)' + ' '*20)
    return buf

def encrypt_data_c(data, kt, offset=0):
    total = len(data)
    aligned = (total // 16) * 16
    if aligned == 0:
        return bytearray(data)
    buf = bytearray(data[:aligned])
    kt_arr = _make_kt_arr(kt)
    t0 = time.time()
    n_chunks = (aligned + _CHUNK - 1) // _CHUNK
    for ci, start in enumerate(range(0, aligned, _CHUNK)):
        end = min(start + _CHUNK, aligned)
        chunk_len = end - start
        chunk_ptr = (ctypes.c_char * chunk_len).from_buffer(buf, start)
        _lib.camellia_encrypt(chunk_ptr, chunk_len, kt_arr, ctypes.c_uint64(offset + start))
        elapsed = time.time() - t0
        mb_done = end / 1048576; mb_total = aligned / 1048576
        speed = mb_done / max(elapsed, 0.001)
        eta = (mb_total - mb_done) / max(speed, 0.1)
        print(f'\r[C加密] {ci+1}/{n_chunks} 块 '
              f'({mb_done:.0f}/{mb_total:.0f} MB) '
              f'{elapsed:.0f}s [{speed:.0f} MB/s, 剩余 ~{eta:.0f}s]',
              end='', flush=True)
    elapsed = time.time() - t0
    print(f'\r[C加密] 完成 {aligned/1048576:.1f} MB, '
          f'{elapsed:.1f}s ({aligned/1048576/max(elapsed,0.001):.0f} MB/s)' + ' '*20)
    return buf

# ═══════════════════════════════════════════════════════════════
#  numpy 版 (降级方案)
# ═══════════════════════════════════════════════════════════════

def _try_numpy():
    try:
        import numpy as np
        return True
    except ImportError:
        return False

def _load_numpy_funcs():
    """延迟加载 numpy 版本"""
    import numpy as np
    import libp_tool as _lt

    _S1n = np.array([x & 0xFFFFFFFF for x in _lt._S1], dtype=np.uint32)
    _S2n = np.array([x & 0xFFFFFFFF for x in _lt._S2], dtype=np.uint32)
    _S3n = np.array([x & 0xFFFFFFFF for x in _lt._S3], dtype=np.uint32)
    _S4n = np.array([x & 0xFFFFFFFF for x in _lt._S4], dtype=np.uint32)
    _U32 = np.uint32; _MASK = _U32(0xFFFFFFFF)

    def _rl(v,n): n%=32; return ((v<<_U32(n))|(v>>_U32(32-n)))&_MASK
    def _rr(v,n): n%=32; return ((v>>_U32(n))|(v<<_U32(32-n)))&_MASK
    def _mv(v): return (_rl(v,8)&_U32(0x00FF00FF))|(_rr(v,8)&_U32(0xFF00FF00))

    def _fh(d0,d1,d2,d3,ka,kb,kc,kd):
        t=_U32(ka)^d0; U=_S3n[(t>>8)&0xFF]^_S4n[t&0xFF]^_S2n[(t>>16)&0xFF]^_S1n[(t>>24)&0xFF]
        t=_U32(kb)^d1; D=_S4n[(t>>8)&0xFF]^_S1n[t&0xFF]^_S3n[(t>>16)&0xFF]^_S2n[(t>>24)&0xFF]
        UD=U^D; d2^=UD; d3^=UD^_rr(U,8)
        t=_U32(kc)^d2; U=_S3n[(t>>8)&0xFF]^_S4n[t&0xFF]^_S2n[(t>>16)&0xFF]^_S1n[(t>>24)&0xFF]
        t=_U32(kd)^d3; D=_S4n[(t>>8)&0xFF]^_S1n[t&0xFF]^_S3n[(t>>16)&0xFF]^_S2n[(t>>24)&0xFF]
        UD=U^D; d0^=UD; d1^=UD^_rr(U,8)
        return d0,d1,d2,d3

    def _dec_chunk(data, kt, offset):
        n = len(data)//16
        if n==0: return bytearray()
        arr = np.frombuffer(data, dtype='<u4', count=n*4).copy().reshape(n,4)
        d0,d1,d2,d3 = arr[:,0],arr[:,1],arr[:,2],arr[:,3]
        offsets = np.arange(n, dtype=np.int64)*16+offset
        rbs = ((offsets>>4)&0x0F).astype(np.int32)+16
        for rb in range(16,32):
            m=rbs==rb
            if not np.any(m): continue
            d0[m]=_rl(d0[m],rb); d1[m]=_rr(d1[m],rb)
            d2[m]=_rl(d2[m],rb); d3[m]=_rr(d3[m],rb)
        d0[:]=_mv(d0); d1[:]=_mv(d1); d2[:]=_mv(d2); d3[:]=_mv(d3)
        k=0
        d0^=_U32(kt[k]); d1^=_U32(kt[k+1]); d2^=_U32(kt[k+2]); d3^=_U32(kt[k+3]); k+=4
        for i in range(3):
            for j in range(3):
                d0,d1,d2,d3=_fh(d0,d1,d2,d3,kt[k+2],kt[k+3],kt[k],kt[k+1]); k+=4
            if i<2:
                d1^=_rl(d0&_U32(kt[k+2]),1); d0^=d1|_U32(kt[k+3])
                d2^=d3|_U32(kt[k+1]); d3^=_rl(d2&_U32(kt[k]),1); k+=4
        d0,d2=d2.copy(),d0.copy(); d1,d3=d3.copy(),d1.copy()
        d0^=_U32(kt[k]); d1^=_U32(kt[k+1]); d2^=_U32(kt[k+2]); d3^=_U32(kt[k+3])
        d0[:]=_mv(d0); d1[:]=_mv(d1); d2[:]=_mv(d2); d3[:]=_mv(d3)
        arr[:,0]=d0; arr[:,1]=d1; arr[:,2]=d2; arr[:,3]=d3
        return bytearray(arr.tobytes())

    def decrypt_np(data, kt, offset=0):
        total=len(data); aligned=(total//16)*16
        if aligned==0: return bytearray(data)
        result=bytearray(aligned); t0=time.time(); nc=(aligned+_CHUNK-1)//_CHUNK
        for ci,start in enumerate(range(0,aligned,_CHUNK)):
            end=min(start+_CHUNK,aligned)
            result[start:end]=_dec_chunk(bytes(data[start:end]),kt,offset+start)
            el=time.time()-t0; md=end/1048576; mt=aligned/1048576
            sp=md/max(el,0.001); eta=(mt-md)/max(sp,0.1)
            print(f'\r[numpy解密] {ci+1}/{nc} 块 ({md:.0f}/{mt:.0f} MB) '
                  f'{el:.0f}s [{sp:.0f} MB/s, 剩余 ~{eta:.0f}s]', end='', flush=True)
        el=time.time()-t0
        print(f'\r[numpy解密] 完成 {aligned/1048576:.1f} MB, '
              f'{el:.1f}s ({aligned/1048576/max(el,0.001):.0f} MB/s)' + ' '*20)
        return result

    # encrypt 同理但太长, 用 C 版或纯 Python 更好
    def encrypt_np(data, kt, offset=0):
        # numpy 加密比较复杂, 直接用纯 Python
        import libp_tool
        return libp_tool.encrypt_data.__wrapped__(data, kt, offset) if hasattr(libp_tool.encrypt_data, '__wrapped__') else _lt.encrypt_data(data, kt, offset)

    return decrypt_np, encrypt_np

# ═══════════════════════════════════════════════════════════════
#  patch 入口
# ═══════════════════════════════════════════════════════════════

def patch(target=None):
    """替换 libp_tool 的 decrypt_data / encrypt_data

    target: 要打补丁的模块对象。不传时默认 import libp_tool（当 libp_tool
    是被 import 进来的普通模块时有效）。但如果 libp_tool.py 是被直接
    `python libp_tool.py ...` 运行的，它在 sys.modules 里的名字是
    '__main__'，而不是 'libp_tool' —— 这时 `import libp_tool` 会得到一个
    完全不同的模块对象（重新执行一遍该文件），补丁打在了这个"影子模块"
    上，真正在跑的 __main__ 里的函数完全没被替换，看起来加载成功但其实
    没生效。所以调用方最好显式传入 sys.modules[__name__]。
    """
    global _accel_mode

    if target is None:
        import libp_tool
        target = libp_tool

    if _load_c_lib():
        target.decrypt_data = decrypt_data_c
        target.encrypt_data = encrypt_data_c
        _accel_mode = 'c'
        return

    if _try_numpy():
        dec_np, enc_np = _load_numpy_funcs()
        target.decrypt_data = dec_np
        # numpy encrypt 太复杂, 保留纯 Python
        # target.encrypt_data = enc_np
        _accel_mode = 'numpy'
        print('[加速] numpy 向量化已启用 (解密)')
        return

    print('[提示] 无加速可用, 使用纯 Python (慢)')

# ═══════════════════════════════════════════════════════════════
#  自测
# ═══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import importlib, libp_tool
    importlib.reload(libp_tool)
    patch()

    from database_malie import database_malie
    kt = database_malie['Zero Infinity -Devil of Maxwell-']['Key'][:52]

    test = os.urandom(4096)
    dec_py = libp_tool.decrypt_data(bytearray(test), kt, 0x100)

    # 纯 Python 解密对照
    dec_ref = bytearray()
    for off in range(0, len(test), 16):
        dec_ref.extend(libp_tool._cam_dec(bytes(test[off:off+16]), kt, 0x100+off))

    print(f'解密一致: {"✅" if dec_py == dec_ref else "❌"}')

    enc = libp_tool.encrypt_data(bytearray(test), kt, 0)
    dec_back = libp_tool.decrypt_data(bytearray(enc), kt, 0)
    print(f'round-trip: {"✅" if dec_back == bytearray(test) else "❌"}')

    # 速度测试
    big = os.urandom(10 * 1024 * 1024)
    t0 = time.time()
    _ = libp_tool.decrypt_data(bytearray(big), kt, 0)
    t1 = time.time()
    print(f'\n10MB 解密: {t1-t0:.2f}s → 500MB 预估: {(t1-t0)*50:.0f}s')
