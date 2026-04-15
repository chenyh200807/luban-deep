Page({

  /**
   * 页面的初始数据
   */
  data: {

    multiArray: [['小学', '初中', '高中', '大学'], ['语文', '数学']],
    objectMultiArray: [
      [
        {
          id: 0,
          name: '小学'
        },
        {
          id: 1,
          name: '初中'
        },
        {
          id: 2,
          name: '高中'
        },
        {
          id: 3,
          name: '大学'
        }
      ],
      [
        {
          id: 0,
          name: '语文'
        },
        {
          id: 1,
          name: '数学'
        }
      ]
    ],
    multiIndex: [],
  },
  bindMultiPickerChange: function (e) {
    //console.log('picker发送选择改变，携带值为', e.detail.value)
    this.setData({
      multiIndex: e.detail.value
    })
  },
  bindMultiPickerColumnChange: function (e) {
    // console.log('修改的列为', e.detail.column, '，值为', e.detail.value);
    var data = {
      multiArray: this.data.multiArray,
      multiIndex: this.data.multiIndex
    };

   data.multiIndex[e.detail.column] = e.detail.value;
    switch (e.detail.column) {
      case 0:
        switch (data.multiIndex[0]) {
          case 0:
            data.multiArray[1] = ['语文', '数学', '其他'];
            break;
          case 1:
            data.multiArray[1] = ['语文', '数学','英语', '其他'];
            break;
          case 2:
            data.multiArray[1] = ['语文', '数学', '英语', '历史', '其他'];
            break;
          case 3:
            data.multiArray[1] = ['高数', '政治', '专业', '选修', '实验', '其他'];
            break;
        }
        break;
    }
    this.setData(data);
  }
})