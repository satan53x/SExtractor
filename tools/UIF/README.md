## 相关
原版地址：https://github.com/AtomCrafty/UniversalInjectorFramework
改版地址：https://github.com/satan53x/UniversalInjectorFramework

## 修改
* 修改了JIS隧道对某些游戏exe无法生效的问题。(`MultiByteToWideCharHook`)
* `character_substitution`模块增加`hook_functions`，可指定需要hook的函数。可选值：`"hook_functions": ["TextOutA", "TextOutW", "GetGlyphOutlineA", "GetGlyphOutlineW", "ExtTextOutA", "ExtTextOutW"]`。
* 没有设置`hook_functions`时默认列表为`"TextOutA", "TextOutW", "GetGlyphOutlineA", "GetGlyphOutlineW"`。
* `font_manager`下`spoof_creation`添加了支持的参数：`override_height`和`override_width`

