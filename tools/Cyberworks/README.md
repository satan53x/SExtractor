### CSystemArc
* Arc00.dat仅限UTF-16编码
* Arc04.dat不再转换b0到png，而是直接导出raw。
* unpack时缓存未知字节到cache.xml，封包时需使用相同xml。
* `-v 23`可以指定资源版本`21-24`，pack时存在cache.xml则无需指定。
* `-i 2`可以指定索引版本`1-2`，测试游戏：`ムジナ・臭`

### CSystemArc_JIS
原版地址：https://github.com/arcusmaximus/CSystemTools
* 修改：Arc00.dat中，`csystem/config/item-5`从text改为binary导出。