### 测试游戏：シロクロv1.1
* 目录结构：`Archives/base_div0_archive.arc`

### 解包
* 命令行：`python arc_unpack.py <ARC文件路径> [输出目录]`
* 解包完无视后缀名，看文件头，如果是UnityFS则是AssetBunble包。

### 封包
* 命令行：`python arc_pack.py <输入目录> [输出ARC文件]`

### AssetBunble批量导出
* https://github.com/aelurum/AssetStudio
* 导出设置里选format带`@pathID`，再全部按raw导出

### AssetBunble批量导入
* 本文件夹下的`UnityAssetBundlePatcher.exe --overwrite <bundle> <*@pathID.dat>`
* 原版项目（非UnityFS）：https://github.com/3ter/unity-asset-bundle-patcher
