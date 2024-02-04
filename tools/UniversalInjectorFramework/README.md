## 相关
原版地址：https://github.com/AtomCrafty/UniversalInjectorFramework

预设字典：https://github.com/XD2333/GalTransl_DumpInjector

## 修改
* 修改了JIS隧道对某些游戏exe无法生效的问题。(`MultiByteToWideCharHook`)
* `character_substitution`模块增加`hook_functions`，可指定需要hook的函数。可选值：`"hook_functions": ["TextOutA", "TextOutW", "GetGlyphOutlineA", "GetGlyphOutlineW", "ExtTextOutA", "ExtTextOutW"]`。
* 没有设置`hook_functions`时默认列表为`"TextOutA", "TextOutW", "GetGlyphOutlineA", "GetGlyphOutlineW"`。
