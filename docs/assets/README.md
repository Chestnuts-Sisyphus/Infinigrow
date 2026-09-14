# 仓库运营资产（assets）

## `social-preview.png`

- **规格**：1280×640（GitHub social preview 推荐尺寸），约 42 KB（上限 1 MB）。
- **设计**：深底（`#0B0D14`）＋单一强调色紫（`#8B5CF6`）＋**唯一一次暖色**（芽尖 `#F0A64B`）；
  右侧的生长符＝一条主干加三处分岔，分岔就是「差异」，最后一处暖色＝刚冒出的芽。
- **怎么用**：仓库 Settings → Social preview → Upload an image → 选这个文件。
  （GitHub 只接受 PNG/JPG/GIF，不接受 SVG，所以这里是位图。）

## 仓库描述与 topics（发布时逐字使用）

描述（Description）：

```
An engine that grows by predicting, reconciling, and turning differences into sprouts.
```

Topics：

```
agent, autonomy, prediction, reconciliation, ledger, self-improving, python
```

一条命令设置（仓库存在后）：

```bash
gh repo edit --description "An engine that grows by predicting, reconciling, and turning differences into sprouts." \
             --add-topic agent,autonomy,prediction,reconciliation,ledger,self-improving,python
```
