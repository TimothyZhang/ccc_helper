介绍(Introduction)
=================
为cocos creator增加Prefab嵌套以及自动同步功能。


警告(Warning)
============
本项目并非官方提供的功能，可能会造成数据丢失。使用之前，请务必备份好数据!


使用(Usage)
==========
* ccc.py -p <path> verify
  检查项目中哪些Prefab不一致

* ccc.py -p <path> sync
  同步项目中所有不一致的Prefab

* ccc_graph.py -p <path>
  ** 红色节点：场景
  ** 绿色节点: 没有子节点的Prefab（不嵌套包含其他Prefab）
  ** 蓝色节点：嵌套包含其他Prefab的Prefab
  ![Alt text](/test_project.png?raw=true "test_project.jpg")


术语(Terms)
==========
* Prefab Root: Prefab文件的根节点
* Instance Node: 包含KdPrefab组件的Node
* Instance Root: 祖先中没有Instance Node的Instance Node(Prefab Root除外）


限制(Restrictions)
=================
* R1: 每一个Node的Children不可重名
* R2: 每一个Node的Component不可重复
* R3: 每一个Prefab的根节点，必须有KdPrefab组件；反之亦然。
  ** R3-1: 其中的prefab属性指向Prefab自身
* R4: Button的clickEvents最多只能有一个元素(如有特殊需要，也可以不限制，但是可能比较容易出错，见R5)
* R5: 数组中间插入/删除元素后，从插入位置开始之后的元素，不一定能增量同步
* R6: Layout只能包含已知的Type和ResizeMode(以防ccc增加了新的类型）


同步策略(Synchronization Strategies)
==================================
* SS1: 只有当prefab root和instance root的KdPrefab.strategy都为DEFAULT(0)，才会同步
* SS2: instance root忽略: position, rotation, scale, anchor, skew, name, zOrder, tag, active
* SS3: instance root忽略: Widget(除非prefab root中有Widget而instance中没有)
* SS4: 忽略Node.active
* SS5: Node的size/position受Layout/Widget影响时，不同步相应的x/y/w/h(包括KdLayout/KdWidget)
* SS6: 忽略Layout的_layoutSize


自定义规则(Custom Rules)
======================
在ccc_helper.yaml中配置
* CR1: 完全忽略组件(ignore_components)
* CR2: 忽略组件的指定属性(ignore_component_properties)
* CR3: 忽略组件的空属性(ignore_component_properties_if_empty)，空指prefab中，值为0, "", [], null等，或不存在
* CR4: 忽略特定的prefab中的特定Node的特定组件的特定属性
