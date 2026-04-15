// components/tabNav/tabNav.js
Component({
  /**
   * 组件的属性列表
   */
  properties: {
    tabNavList:{
      type:Object,
      value:''
    },
    itemWidth:{
      type:String,
      value:''
    }
  },
  externalClasses: ['active-class'],
  options: {
    styleIsolation: 'shared',
    multipleSlots: true
  },
  ready(){
    this.setData({
      active_index:wx.getStorageSync('major_id')
    })
  },
  pageLifetimes: {
    show: function() {
      
    },
    hide: function() {
      // 页面被隐藏
    },
    resize: function(size) {
      // 页面尺寸变化
    }
  },
  /**
   * 组件的初始数据
   */
  data: {
    active_index:0
  },

  /**
   * 组件的方法列表
   */
  methods: {
    switchs(e){
      let { pk_id } = e.currentTarget.dataset
      this.setData({
        active_index:pk_id
      })
      this.triggerEvent('changeNav', pk_id)
    }
  }
})
