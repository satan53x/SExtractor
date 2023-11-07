/*-
 * Copyright 2015 Pupyshev Nikita
 * All rights reserved
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted providing that the following conditions
 * are met:
 * 1. Redistributions of source code must retain the above copyright
 *    notice, this list of conditions and the following disclaimer.
 * 2. Redistributions in binary form must reproduce the above copyright
 *    notice, this list of conditions and the following disclaimer in the
 *    documentation and/or other materials provided with the distribution.
 *
 * THIS SOFTWARE IS PROVIDED BY THE AUTHOR ``AS IS'' AND ANY EXPRESS OR
 * IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
 * WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
 * ARE DISCLAIMED.  IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY
 * DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
 * DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS
 * OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
 * HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT,
 * STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING
 * IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
 * POSSIBILITY OF SUCH DAMAGE.
 */

#ifndef __ibootim__lzss__
#define __ibootim__lzss__

#include <stdint.h>

typedef enum {
	LZSS_OK,
	LZSS_NOMEM,
	LZSS_NODATA,
	LZSS_INVARG
} lzss_error_t;

extern size_t decompress(uint8_t dst[], uint8_t src[]);
extern size_t compress(uint8_t dst[], uint8_t src[]);

/*!
 @function lzss_compress
 @abstract Compresses data using LZSS compression algorithm
 @param src Data to compress
 @param dst Buffer for the compressed data
 @param srclen Length of data to compress
 @param dstlen Length of the destination buffer
 @result Size of compressed data or -1 on failure.
 */

extern size_t lzss_compress(uint8_t *dst, unsigned int dstlen, uint8_t *src, unsigned int srclen);

/*!
 @function lzss_decompress
 @abstract Decompresses LZSS compressed data
 @param src LZSS compressed data buffer
 @param dst Buffer for the decompressed data
 @param srclen Length of LZSS compressed data
 @param dstlen Length of the destination buffer
 @result Size of decompressed data or -1 on failure.
 */

extern size_t lzss_decompress(uint8_t *dst, unsigned int dstlen, uint8_t *src, unsigned int srclen);

extern lzss_error_t lzss_errno;
extern const char *lzss_strerror(lzss_error_t error);

#endif /* defined(__ibootim__lzss__) */
