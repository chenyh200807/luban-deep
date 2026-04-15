// package/freeCourse/freeCourse.js
var behavior = require('../../utils/behavior')
Component({
  behaviors: [behavior],

  /**
   * 页面的初始数据
   */
  data: {
    panelAnimation: {},
    panelAnimationhidden: {},
    isPanelShow: true,
    isPanelShowhidden: false,
    showModal: false,
    showurl:'',
    shownum:1,
    showurl1:'',
    showurl2:'',
    showimg:'',
    page:1,
    getGratisCourseList:[],
    noData:false,
    major_id:10,
    subject_id : 0,  //科目id
    cate_id : 0,    //专业id
    allmajor:{'一级建造师':{'建筑实务':63,'市政实务':61,'机电实务':60,'水利实务':491,'项目管理':58,'相关法规':62,'工程经济':59}, 
              '二级建造师':{'建筑实务':480,'市政实务':461,'机电实务':460,'施工管理':459,'相关法规':458}, 
              '造价工程师':{'案例分析':273,'水利案例':'496','交通案例':'497','土建计量':274,'安装计量':275,'交通计量':277,'水利计量':276,'造价管理':279,'工程计价':278}, 
              '监理工程师':{'监理案例':66,'合同管理':259,'理论与法规':260,'监理三控':65},
              '咨询工程师':{'现代咨询方法与实务':313,'项目决策分析与评价':312},
              '实操':{'造价实操':398,'高阶管理实操':406},
              '名师讲座':{'名师讲座':999},
              '黄皮书配套课程':{'一建建筑实务':800,'一建机电实务':801,'一建水利实务':802,'一建项目管理':810,'一造案例分析':803,'一造水利案例':804,'一造水利计量':805,'一造交通案例':808,'一造交通计量':809,'咨询实务':806,'咨询评价':807,'监理三控':811},
            },
    multiArray: [['一级建造师', '二级建造师', '造价工程师', '监理工程师','咨询工程师','实操','名师讲座','黄皮书配套课程'],
     ['建筑实务',
      '市政实务',
      '机电实务',
      '项目管理',
      '工程经济',
      '相关法规',
      '水利实务',
      '综合实训']], 
    objectMultiArray: [
      [
        {
          id: 0,
          name: '一级建造师'
        },
        {
          id: 1,
          name: '二级建造师'
        },
        {
          id: 2,
          name: '造价工程师'
        },
        {
          id: 3,
          name: '监理工程师'
        },
        {
          id: 4,
          name: '咨询工程师'
        },
        {
          id: 5,
          name: '实操'
        },
        {
          id: 6,
          name: '名师讲座'
        },
        {
          id: 7,
          name: '黄皮书配套课程'
        }
        
      ],
      [
        {
          id: 0,
          name: '建筑实务'
        },
        {
          id: 1,
          name: '市政实务1'
        }
      ]
    ],
    multiIndex: [],
    zw:'&ensp;&ensp;&ensp;&ensp;&ensp;&ensp;&ensp;&ensp;&ensp;&ensp;&ensp;&ensp;',
    imageUrl: '/images/icon/play_icon_02.png', // 设置图片地址，可以替换为自己的图片路径
    rotateAngle: 0 ,// 初始化旋转角度为0
    ggimage:'',
    ggimageurl:'',
    shoponlie : '',
  },
  methods: {
    rotateImage: function() {
      // debugger;
      var animation = wx.createAnimation({
        duration: 300,  // 动画持续时间，单位ms
        timingFunction: 'linear'  // 线性动画
      });
      animation.rotate(180).step();  // 旋转360度
      this.setData({
        rotationAnim: animation.export(),
        imageUrl: '/images/icon/play_icon_02_1.png'
      });
    },
    stopRotateImage: function() {
      var animation = wx.createAnimation();
      animation.rotate(0).step();  // 旋转到初始状态
      this.setData({
        rotationAnim: animation.export(),
        imageUrl: '/images/icon/play_icon_02.png'
      });
    },
    
    bindMultiPickerChange: function (e) {
      //console.log('picker发送选择改变，携带值为', e.detail.value)
      this.stopRotateImage();
      console.log('ss');
      this.setData({
        multiIndex: e.detail.value
      })
      if(this.data.multiArray[0][e.detail.value[0]] == undefined){
        this.data.multiArray[0][e.detail.value[0]] = Object.keys(this.data.allmajor)[0];
      }
      console.log(this.data.multiArray[0][e.detail.value[0]]);
      console.log(this.data.multiArray[1][e.detail.value[1]]);
      this.data.subject_id = this.data.allmajor[this.data.multiArray[0][e.detail.value[0]]][this.data.multiArray[1][e.detail.value[1]]];
      this.data.cate_id = 4;
      this.data.getGratisCourseList = [];
      this.setData({
        page : 1
      })
      this.getGratisCourse()
    },
    bindMultiPickerColumnChange: function (e) {
      // console.log('修改的列为', e.detail.column, '，值为', e.detail.value);
      this.rotateImage();
      console.log('ss111');
      var data = {
        multiArray: this.data.multiArray,
        multiIndex: this.data.multiIndex
      };

    data.multiIndex[e.detail.column] = e.detail.value;
      switch (e.detail.column) {
        case 0:
          switch (data.multiIndex[0]) {
            case 0:
              debugger;
              data.multiArray[1] = Object.keys(this.data.allmajor[data.multiArray[0][data.multiIndex[0]]]);
              break;
            case 1:
              data.multiArray[1] = Object.keys(this.data.allmajor[data.multiArray[0][data.multiIndex[0]]]);
              break;
            case 2:
              data.multiArray[1] = Object.keys(this.data.allmajor[data.multiArray[0][data.multiIndex[0]]]);
              break;
            case 3:
              data.multiArray[1] = Object.keys(this.data.allmajor[data.multiArray[0][data.multiIndex[0]]]);
              break;
            case 4:
              data.multiArray[1] = Object.keys(this.data.allmajor[data.multiArray[0][data.multiIndex[0]]]);
              break;
            case 5:
              data.multiArray[1] = Object.keys(this.data.allmajor[data.multiArray[0][data.multiIndex[0]]]);
              break;
            case 6:
              data.multiArray[1] = Object.keys(this.data.allmajor[data.multiArray[0][data.multiIndex[0]]]);
              break;
            case 7:
              data.multiArray[1] = Object.keys(this.data.allmajor[data.multiArray[0][data.multiIndex[0]]]);
              break;
          }
          break;
      }
      this.setData(data);
    },
    /**
     * 生命周期函数--监听页面加载
     */
    onLoad: function (options) {
      this.data.major_id = wx.getStorageSync('major_id')
      this.data.major_id = 10
      //如果没有传值进来，就直接默认
      this.data.subject_id = 63;
      this.data.cate_id = 4;
      //debugger;
      this.data.multiArray[0] = Object.keys(this.data.allmajor);
      this.data.multiArray[1] = Object.keys(this.data.allmajor['一级建造师'])
      
      var data = {
        multiArray: this.data.multiArray,
        multiIndex: [0, 0]
      };
      this.setData(data);
      //debugger;
      
      this.animation = wx.createAnimation({
        duration: 350,
        timingFunction: 'cubic-bezier(0.1, 0.57, 0.1, 1)'
      })
      this.animationhidden = wx.createAnimation({
        duration: 350,
        timingFunction: 'cubic-bezier(0.1, 0.57, 0.1, 1)'
      })

    },

    togglePanel() {
      if (this.data.isPanelShow) {
        console.log('隐藏入口');
        this.animation.translateX('-100%').step()
        this.animationhidden.translateX('0').step()
      } else {
        console.log('显示入口');
        this.animation.translateX('0').step()
        this.animationhidden.translateX('-100%').step()
      }
      
      this.setData({
        panelAnimation: this.animation.export(),
        isPanelShow: !this.data.isPanelShow,
        panelAnimationhidden: this.animationhidden.export(),
        isPanelShowhidden: !this.data.isPanelShowhidden
      })
    },

    //关闭弹窗
    closeModal: function () {
      this.setData({
        showModal: false,
      });
    },

    //广告跳转
    gotoModalurl: function(){
      if(this.data.showurl){
        wx.navigateTo({
          url: '/pages/text/text?url='+this.data.showurl
        })
      }
      
    },
    //左边跳转
    goToLeftTopPage: function(){
      // debugger;
      console.log('left');
      if(this.data.shownum == 1){
        if(this.data.showurl){
          wx.navigateTo({
            url: '/pages/text/text?url='+this.data.showurl
          })
        }
      }else if(this.data.shownum == 2){
        if(this.data.showurl1){
          wx.navigateTo({
            url: '/pages/text/text?url='+this.data.showurl1
          })
        }
      }
    },
    //右边跳转
    goToRightBottomPage: function(){
      console.log('right');
      // debugger;
      if(this.data.shownum == 1){
        if(this.data.showurl){
          wx.navigateTo({
            url: '/pages/text/text?url='+this.data.showurl
          })
        }
      }else if(this.data.shownum == 2){
        if(this.data.showurl2){
          wx.navigateTo({
            url: '/pages/text/text?url='+this.data.showurl2
          })
        }
      }
      
    },

    //头部广告跳转
    goToggimageurl: function(){
      if(this.data.ggimageurl){
        wx.navigateTo({
          url: '/pages/text/text?url='+this.data.ggimageurl
        })
      }
    },

       //用户入口页面
    onuserline: function(){
        if(this.data.ggimageurl){
          wx.navigateTo({
            url: '/pages/text/text?url=https://user.yousenjiaoyu.com/user/index.html'
          })
        }
      },

    //获取免费课程
    getGratisCourse(){
      // debugger;
      let data = {
        page:this.data.page,
        fk_user_id:0,
        fk_major_id:this.data.major_id,
        subject_id:this.data.subject_id,
        cate_id:this.data.cate_id,
        project:this.data.multiArray[0][[this.data.multiIndex[0]]]
      }
      let _this = this;
      this.isPostHttp('Getmajorzm',data).then(res=>{
       // debugger;
        if (res.status==1){
          let getGratisCourseList = this.data.getGratisCourseList.concat(res.data)
          
          this.setData({
            getGratisCourseList: getGratisCourseList,
            noData:false,
            ggimageurl:res.ggimageurl,
            ggimage:res.ggimage,
            shoponlie:res.shoponlie
          })

          //广告内容
          this.setData({
            shownum:res.shownum,
            showurl1:res.showurl1,
            showurl2:res.showurl2
          });

         

          const showkey = wx.getStorageSync('showkey');
          const now = new Date();
          var key = false;
          if(showkey > now.getTime()){
            key = true;
          }
          // key = false;
         // debugger;
          if(!res.showimg||key){
            this.setData({
              showModal: false
            })
          }else{    
            // const expireTime = Date.now() + 1 * 1 * 3 * 1000; // 三个小时后的时间戳  
            // // const expireTime = Date.now() + 3 * 60 * 60 * 1000; // 三个小时后的时间戳
            // wx.setStorageSync('showkey', 'value', {
            //   expires: expireTime
            // });     
            const now = new Date();
            const threeMinutesLater = now.getTime() + 3 * 60 * 60 * 1000; // 三个小时后的时间戳
            wx.setStorageSync('showkey', threeMinutesLater);
            //广告弹窗
              //debugger;
              // const value = wx.getStorageSync('showkey');
              if (!_this.data.showimg) {
                // debugger;
                var that = this;
                setTimeout(function () {
                  // 等待一秒后执行的代码
                  that.setData({
                    showModal: true,
                    showimg:res.showimg,                    
                    showurl:res.showurl
                  });


                }, 1000);
              }
          }

        }else if(res.status !=1 && this.data.page==1){
          this.setData({
            noData:true
          })

          if(!res.showimg){
            this.setData({
              showModal: false
            })
          }else{                  
            //广告弹窗
              const hasShownModal = wx.getStorageSync('hasShownModal');
              //debugger;
              if (!_this.data.showimg) {
                _this.setData({
                  showModal: true,
                  showimg:res.showimg,
                  showurl:res.showurl,
                });
                wx.setStorageSync('hasShownModal', 'true');
              }
          }
        }
      }).catch()
    },
    //点击导航
    switchTab(e){
      if(e.detail == this.data.major_id){
        return
      }
      this.setData({
        major_id:e.detail,
        page:1,
        getGratisCourseList:[]
      })
      this.getGratisCourse()
    },
    /**
     * 生命周期函数--监听页面初次渲染完成
     */
    onReady: function () {


    },

    /**
     * 生命周期函数--监听页面显示
     */
    onShow: function () {
      this.setData({
        page:1,
        getGratisCourseList:[]
      })
      console.log('开局显示');
      this.getGratisCourse()
        //this.getBrotherMajor()

    },

    /**
     * 生命周期函数--监听页面隐藏
     */
    onHide: function () {
  
    },

    /**
     * 生命周期函数--监听页面卸载
     */
    onUnload: function () {

    },

    /**
   * 页面相关事件处理函数--监听用户下拉动作
   */
  onPullDownRefresh: function () {
    this.setData({
      page: 1,
      getGratisCourseList:[]
    })
    this.getGratisCourse();
   // this.getBrotherMajor()
    setTimeout(function () {
      wx.stopPullDownRefresh()
    }, 2000)
  },

  /**
   * 页面上拉触底事件的处理函数
   */
  onReachBottom: function () {
    let that = this;
   // debugger;
    wx.showLoading({ title: '正在加载更多', mask: true });
    setTimeout(() => {
      that.data.page++;
      that.getGratisCourse();
      wx.hideLoading()
    }, 1000)
  },

    /**
     * 用户点击右上角分享
     */
    onShareAppMessage: function () {
      debugger;
      return {
        title: '佑森好课',
        path: 'pages/freeCourse/freeCourse?top_id='+wx.getStorageSync('members').pk_id+'&major_id='+wx.getStorageSync('major_id')+'&major_title='+wx.getStorageSync('major_title'),
      }
    },

    //省略标题内容
    gettitle:function(e){
      console.log(e);
      return 1;
    },

    //跳转到 DeepTutor 模块
    navigateToShop:function(e){
      console.log('跳转到 DeepTutor');
      wx.switchTab({
        url: '/pages/chat/chat',
        fail() {
          wx.showToast({
            title: 'DeepTutor 模块未接入当前版本',
            icon: 'none',
            duration: 2500
          });
        }
      })
    }
    
  }
})
