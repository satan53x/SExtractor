## GIGA_NEXAS  
戏画引擎解/封包  
解包:ToolName -x <package.pac> <path/to/folder> [CP_ACP|CP_UTF8]  
封包:ToolName -c <no|zlib|zstd> <package.pac> <path/to/folder> [CP_ACP|CP_UTF8]  
老版本采用zlib,新版本采用zstd
不过戏画具体从什么时候开始换的压缩方式我也不太清楚orz
  
### 参考  
https://github.com/pkuislm/NexasPackEdit  
https://github.com/Yggdrasill-Moe/Niflheim/blob/master/NeXAS/pac_unpack/Huffman_dec.h  
优化 by https://github.com/crskycode