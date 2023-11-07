# lzssmodule.pyx

# 导入需要的Cython模块
cimport libc.stdint

# 定义lzss_error_t枚举
cdef enum lzss_error_t:
    LZSS_OK
    LZSS_NOMEM
    LZSS_NODATA
    LZSS_INVARG

ctypedef libc.stdint.uint8_t uint8_t

cdef extern from "lzss.c":
    pass

# 定义lzss_compress和lzss_decompress函数
cdef extern from "lzss.h":
    cpdef size_t lzss_compress(uint8_t *dst, unsigned int dstlen, uint8_t *src, unsigned int srclen)
    cpdef size_t lzss_decompress(uint8_t *dst, unsigned int dstlen, uint8_t *src, unsigned int srclen)

# 添加Python包装函数（可选）
cpdef compress(dst, src):
    result = lzss_compress(dst, <unsigned int>len(dst), src, <unsigned int>len(src))
    return result

cpdef decompress(dst, src):
    result = lzss_decompress(dst, <unsigned int>len(dst), src, <unsigned int>len(src))
    return result