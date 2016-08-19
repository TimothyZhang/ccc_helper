## 警告(Warning)
**本项目并非官方提供的解决方案。使用之前，请务必备份好数据，否则可能会造成数据丢失!**


**This is NOT an official solution, BACKUP you data and use with CAUTION.**

## 介绍(Introduction)
为cocos creator增加Prefab嵌套以及自动同步功能。

#### 特别说明
Kd开头的组件，为作者自定义组件，忽略即可。


## 术语(Terms)
* Prefab Root: Prefab文件的根节点
* Instance Node: 包含KdPrefab组件的Node
* Instance Root: 祖先中没有Instance Node的Instance Node(Prefab Root除外）
* Synchronize: 同步。将Prefab的内容，递归复制到引用到该Prefab的所有Scene或其他Prefab中。

## 限制(Restrictions)
* R1: 每一个Node的Children不可重名
* R2: 每一个Node的Component不可重复
* R3: 每一个Prefab的根节点，必须有KdPrefab组件；反之亦然。
  * R3-1: 其中的prefab属性指向Prefab自身
* R4: Button的clickEvents最多只能有一个元素(如有特殊需要，也可以不限制，但是可能比较容易出错，见R5)
* R5: 数组中间插入/删除元素后，从插入位置开始之后的元素，不一定能增量同步


## 同步策略(Synchronization Strategies)
* SS1: 只有当prefab root和instance root的KdPrefab.strategy都为DEFAULT(0)，才会同步
* SS2: instance root忽略: position, rotation, scale, anchor, skew, name, zOrder, tag, active
* SS3: instance root忽略: Widget(除非prefab root中有Widget而instance中没有)
* SS4: 忽略Node的active和_reorderChildDirty(不太确定是否可以)
* SS5: Node的size/position受Layout/Widget影响时，不同步相应的x/y/w/h(包括KdLayout/KdWidget)
* SS6: 忽略Layout的_layoutSize(其实不是很确定是否应该如此)
* SS7: cc.Label的overflow为NONE时，忽略宽度;overflow为RESIZE_HEIGHT时，忽略高度
* SS8: KdText,忽略Label.string, Sprite.spriteFrame
* SS9: KdLabel,忽略Node的_color, Label的_actualFontSize, _isSystemFontUsed, _N$file, _fontSize, _lineHeight, 以及LabelOutline, KdLabelShadow
* SS10: KdText的i18nKey和args都为空时，不同步

其中SS5, SS6, SS7, SS8, SS9主要是为了减少diff的输出，便于人工查错。


## 自定义规则(Custom Rules)
在`<project_root>/ccc_helper.yaml`中配置，模版见`test_project/ccc_helper.yaml`
* CR1: 完全忽略组件(ignore_components)
* CR2: 忽略组件的指定属性(ignore_component_properties)
* CR3: 忽略组件的空属性(ignore_component_properties_if_empty)，空指prefab中，值为0, "", [], null等，或不存在
* CR4: 忽略特定的prefab中的特定Node的特定组件的特定属性(ignore_prefabs)


## 运行环境(Runtime Environments)
* Python 2.7.x
* pyyaml

如需生成引用关系图，需要用到以下库
* networkx
* pygraphviz(需要安装graphviz)


## 如何使用(How-to)
首先，确保文件`library/bundle.project.js`存在。如果不存在，需用cocos creator打开项目，会自动生成该文件。

* 检查项目中哪些Prefab不一致(Compare prefabs and their referers)
> ccc.py -p test_project verify

* 同步项目中所有不一致的Prefab(synchronize prefabs to their referers)
> ccc.py -p test_project sync

verify或sync结束后，在<project_root>/ccc_helper_backup中会有相应的日志和备份文件。


* 查看项目中所有Prefab/Scene的引用关系
> ccc_graph.py -p test_project

  ![graph of test_project](/test_project.jpg?raw=true)

  A通过箭头指向B，表示A(prefab或scene)中包含了B(prefab)；节点有4种颜色
  * 红色: 场景
  * 粉色: 不被其他Prefab/Scene引用的Prefab
  * 绿色: 不引用其他Prefab的Prefab
  * 蓝色: 既被引用，又引用其他Prefab的Prefab

  注：无任何引用关系的Prefab/Scene，不会包含在图中

## 已知问题(Known Issues)
* 同步后，cocos creator的`回退(Revert)`功能可能会出错或卡死。可能是PrefabInfo的fileId/uuid处理的不对。

## 支持(Support)
* [Cocos Creator论坛](http://forum.cocos.com/c/Creator)上@timium
* [提交issue](https://github.com/TimothyZhang/ccc_helper/issues/new)
* github提交pull request
