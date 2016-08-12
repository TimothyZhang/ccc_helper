var PrefabSynchronizeStrategy = cc.Enum({
    DEFAULT: 0,
    NEVER: 1
})

// TODO: remove this component while publishing
cc.Class({
    extends: cc.Component,

    properties: {
        strategy: {
            default: PrefabSynchronizeStrategy.DEFAULT,
            type: PrefabSynchronizeStrategy,
            tooltip: 'Prefab同步策略'
        },
        
        prefab: {
            default: null,
            type: cc.Prefab
        }
    },

    // use this for initialization
    onLoad: function () {

    },

    // called every frame, uncomment this function to activate update callback
    // update: function (dt) {

    // },
});
