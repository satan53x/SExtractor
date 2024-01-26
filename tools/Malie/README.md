## 说明
* 密钥取自`Garbro`，需要更多密钥可以在garbro中断点调试`ArcLIB.cs`的`KnownSchemes.Values`。
* 目前仅支持`cfi`加密，暂不支持`camellia`。
* 原包内的对齐填充并不是00，但尚不清楚生成原理，故封包时都写00，请自行测试。
