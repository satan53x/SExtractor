## CSystemArc
原版地址：https://github.com/arcusmaximus/CSystemTools

#### CSystemArc修改：
1. Arc00.dat仅限UTF-16编码。
2. Arc04.dat不再转换b0到png，而是直接导出raw。
3. Arc04.dat解包时缓存未知字节到cache.xml，封包时需使用相同xml。

#### CSystemArc_JIS修改：
1. Arc00.dat中，`csystem/config/item-5`从text改为binary导出。