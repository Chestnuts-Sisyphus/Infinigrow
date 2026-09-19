# 哨兵样例（**故意**留着三条命中）

这个文件是给隐私闸「项目层」当哨兵用的：它里面的三行**必须**被
`tests/data/privacy-deny-sample.txt` 咬出来。清零它就等于宣告这条闸失效——所以
`tests/test_privacy_deny_layer.py` 同时钉住两个方向：命中要报命中，删掉命中要报零命中。

写在这里的都是合成词，不含任何真实路径、身份词或凭据；通用层（绝对路径／凭据／邮箱）
对本文件应当零命中，仓库整体扫描也因此不受影响。

<!-- 以下三行是哨兵载荷，不要删：删了就等于把 CI 上的项目层禁列重新变成一条空话 -->
TTL-DEMO-SECRET-0001
not-a-real-collaborator-name
demo-private-infra-7
