# TtT fnt.pak 全字库重绘包

## 产物

- `fnt_chs_fullredraw.pak`：已经回封好的 `fnt.pak` 替换文件。
- `fnt_fullredraw/font12.fd0`：12px 正文字库，全槽位重绘。
- `fnt_fullredraw/font12.fk0`：12px 阴影 / mask 层，全槽位重绘。
- `fnt_fullredraw/font24.fd0`：24px 正文字库，全槽位重绘。
- `fnt_fullredraw/font24.fk0`：24px 阴影 / mask 层，全槽位重绘。
- `atlas_fullredraw/*.png`：全字库 atlas 预览。
- `fnt_fullredraw/sample_sheet.png`：常用样例预览。
- `fnt_fullredraw/full_redraw_report.json`：本次重绘统计。
- `tools/ttt_fnt_full_redraw.py`：本次使用的全槽位重绘工具。
- `tools/ttt_fnt_tool.py`：字库分析 / atlas 导出辅助工具。
- `tools/kcap_pak_tool.py`：KCAP `.pak` 解包封包工具。

包内没有包含用户提供的 `.ttf/.ttc` 字体文件。

## 本次处理策略

这次不是只改 `subs_cn_jp.json` 中出现的映射槽，而是对 `font12/font24` 的 `fd0/fk0` 四个文件做了全槽位重绘：

1. 映射表命中的槽位：
   - 脚本实际写入 CP932/SJIS 可编码字。
   - 字库槽位画成对应简体字。
   - 例如槽位 `這` 绘制为 `这`，槽位 `説` 绘制为 `说`。

2. 映射表没有命中的槽位：
   - 仍按该槽位原本的 CP932 解码字符重新绘制。
   - 这样可以避免游戏里出现新旧字体混杂。

3. `fk0`：
   - 按对应 `fk0` 文件头 margin 生成扩展 mask。
   - `font12.fk0` margin = 1。
   - `font24.fk0` margin = 2。
   - mask 层使用 dilation/MaxFilter 方式生成，不是直接复制 fd0。

4. 标点：
   - 不按标点自身 bbox 居中。
   - 使用 `国` 字作为统一基准，保持同一 baseline。
   - 再对标点做轻微右下偏移。

## 本次统计

- 映射表条目：3018。
- 唯一 CP932 槽位：3018。
- 每个字库文件绘制槽位：7123。
- 每个字库文件中映射命中槽位：3018。
- 每个字库文件中按原 CP932 字符重绘槽位：4105。
- 每个字库文件中不可解码槽位：57，保持空白。

## 重新生成命令

假设已解包出原始 `fnt.pak`：

```bat
python tools\kcap_pak_tool.py unpack fnt.pak fnt_original
```

全槽位重绘：

```bat
python tools\ttt_fnt_full_redraw.py fnt_original subs_cn_jp.json fnt_fullredraw --ttf path\to\alyce_humming.ttf --size12 12 --size24 24
```

回封：

```bat
python tools\kcap_pak_tool.py pack fnt_fullredraw fnt_chs_fullredraw.pak --mode raw
```

校验：

```bat
python tools\kcap_pak_tool.py verify fnt_chs_fullredraw.pak fnt_fullredraw
```

## 替换方式

把 `fnt_chs_fullredraw.pak` 改名为游戏原本使用的 `fnt.pak` 后替换。

建议先备份原始 `fnt.pak`。
