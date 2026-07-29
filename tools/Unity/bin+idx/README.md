# scripts.bin / scripts.idx 封包工具（已修复）
* 由`Steins;Gate`提供，针对后缀为bin和idx文件的Unity架构
* 测试游戏：上倉雛のヒミツ ～ごほうびは私のカラダ♪～

## 为什么旧版会卡开始界面？

游戏加载脚本时调用：

```csharp
DecryptBinFile(..., out string obj);  // AES 解密后再 MsgPack.Unpack<string>()
scriptLine = obj.Split('\n');
```

因此 **bin 里每个文件必须是**：

```
AES-256-CBC( MessagePack字符串( 脚本UTF-8文本 ) )
```

旧工具把明文/原始字节直接 AES 了（少了 MsgPack 外壳），`Unpack<string>` 失败，启动卡死。

## 推荐：C# 版（快）

```powershell
cd scripts_pack_tool
dotnet build -c Release
$exe = ".\bin\Release\net9.0\scripts_pack_tool.exe"

# 解包成可编辑文本（自动去掉 MsgPack 外壳）
& $exe unpack ..\scripts.bin ..\scripts.idx ..\_scripts_text

# 改 _scripts_text\scripts\*.snr 后封包（自动加 MsgPack 外壳 + 生成 idx）
& $exe pack ..\_scripts_text\scripts out\scripts.bin out\scripts.idx --prefix /scripts/

# 校验（应对原包得到 byte-identical）
& $exe verify ..\scripts.bin ..\scripts.idx
& $exe selftest
```

已验证：从可编辑文本 repack 后 `scripts.bin` / `scripts.idx` 与原包 **完全一致**。

## 部署

同时覆盖（两个都要换）：

- `KamikuraHinaNoHimitsu_Data\StreamingAssets\scripts.bin`
- `KamikuraHinaNoHimitsu_Data\StreamingAssets\scripts.idx`

## Python 版

`scripts_pack_tool.py` 逻辑已同步修复；无 `pycryptodome`/`cryptography` 时纯 Python AES 会很慢，**建议装其一或用 C# 版**。

```bash
pip install pycryptodome   # 推荐
python scripts_pack_tool.py selftest
python scripts_pack_tool.py unpack scripts.bin scripts.idx out
python scripts_pack_tool.py pack out/scripts scripts.bin scripts.idx --prefix /scripts/
```

## 格式摘要

| 项 | 值 |
|----|----|
| AES | 256-CBC PKCS7 |
| Key | `c6eahbq9sjuawhvdr9kvhpsm5qv393ga` |
| IV | `ARC-PACKPASSWORD`（固定） |
| idx | `int32LE len` + AES(msgpack map fileName/size/index) |
| bin | `int32LE len` + AES(msgpack string) |
| index | 指向 size 后的密文起点 |
