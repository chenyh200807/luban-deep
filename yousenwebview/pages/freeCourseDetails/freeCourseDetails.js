// package/freeCourseDetails/freeCourseDetails.js
var behavior = require('../../utils/behavior')
import polyv from '../../utils/polyv.js';
var utilMd5 = require('../../utils/md5.js');
Component({
  behaviors: [behavior],

  /**
   * 页面的初始数据
   */
  data: {
    videoSrc: {
      src:'',
      showBeishu:false,
      view:'倍速', 
      autoplay:true,
      isShowBeishu:false
      
    },
    showmulu:true,
    neirong1:false,
    jianyi:false,
    neirong:'',
    show_index:true,
    hdata:'',
    thevideoshow:'',
    chapterid:'',
    kechengmulu:'',
    kechengneirong:'',
    show:false,
    videotitle:'',
  },
  methods: {
    /**
     * 生命周期函数--监听页面加载
     */
    onLoad: function (options) {
      if(options.pk_id){
        this.data.pk_id = options.pk_id
        if(options.chapterid){
          this.data.chapterid = options.chapterid
        }
        this.getGratisDetail()
      }
      
    },
    getGratisDetail(){
      let data = {
        pk_id:this.data.pk_id,
        chapterid:this.data.chapterid,
        fk_user_id:wx.getStorageSync('members')?wx.getStorageSync('members').pk_id:0
      }
      this.isPostHttp('Getmajordetailedzm',data,true).then(res=>{
        //debugger;
        if(res.status == 1){
          res.data.chapter.forEach((item)=>{
            item.flag = false
          })
          if(res.data.play_id !=''){
            this.publicVideo(res.data.play_id)
          }else if(res.data.chapter.length>0){
            this.publicVideo(res.data.chapter[0].play_id)
            res.data.chapter[0].flag = true
            this.setData({
              videotitle : '正在播放：  '+res.data.chapter[0].title
            })
          }
          wx.setNavigationBarTitle({
            title: res.data.name
          })
          
          this.setData({
            gratisDetail:res.data
          })
          if(!this.data.chapterid){
              this.setData({
                chapterid:res.data.chapter[0].id
              })
          }
        //提交版本的时候把这个值调大
        //showvier 控制小程序详细页面是否显示课程等字眼，正式使用的时候，这个值要和后台传的不一样，提交代码的时候要一样

        //暂不能提供在线视频教育类目，进行视频内容下架处理先，等能提供时再上架处理
        let d = res.showvier;
        if(d!=null){
          console.log('资质问题')
        }

        // if(res.showvier == 15){
        //   wx.navigateTo({
        //     url: '/pages/text/text?url='+this.data.showurl
        //   })
        // }
      //showvier 控制小程序详细页面是否显示课程等字眼，正式使用的时候，这个值要和小程序的不一样，提交代码的时候要一样
       //线上版本 
        if(res.showvier == 27){
          wx.redirectTo({
            url: '/pages/freeCourseDetailsonline/freeCourseDetailsonline'
          })
        }else{
          this.setData({
            kechengmulu:res.kechengmulu,
            kechengneirong:res.kechengneirong,
            show:res.show,
          })
        }
         
          
          let hdata = res.hdata[0];
          this.setData({
            neirong : hdata.introduce.replace(/\<img/gi, '<img style="max-width:100%;height:auto"'),
            hdata : hdata,
            thevideoshow : res.data.chapter[0].title,
          })
        }
      }).catch()
    },
    //选择课程播放
  choicePlays:function(e){
    let { video_id,index,flag} = e.currentTarget.dataset
    this.data.gratisDetail.chapter.forEach((item)=>{
      item.flag = false
    })
    this.data.gratisDetail.chapter[index].flag=flag;
    if(flag){
      this.publicVideo(video_id);
    }
    // wx.showToast({
    //   title: '加载中。。。',
    //   icon: 'loading',
    //   duration: 1500
    // })
    this.setData({
      videotitle : '正在播放：  '+this.data.gratisDetail.chapter[index].title
    })
    if(flag){
      setTimeout(() => {
          this.videoContext.play();
      }, 1000);
    }else{
      this.videoContext.pause();
    }
    this.setData({
      gratisDetail:this.data.gratisDetail,
      'videoSrc.isShowBeishu':true
    })
    setTimeout(()=>{
      this.setData({
        'videoSrc.isShowBeishu':false
      })
    },6000)

    debugger;
    this.setData({
      thevideoshow:this.data.gratisDetail.chapter[index].title,
      chapterid:this.data.gratisDetail.chapter[index].id,
    })

  },
    //第三方视频
    publicVideo:function(id){
      let that=this;
      let vid = id;
      //播放web加密需要添加ts和sign参数。
      var timestamp = Date.parse(new Date());
      var secretKey = "mnABa9XMn8";
      var ts = timestamp;
      var sign = utilMd5.hexMD5(secretKey + vid + ts);
      /*获取视频数据*/
      /*获取视频数据*/
      let vidObj = {
        vid: vid,
        callback: function (videoInfo) {
          that.setData({
            'videoSrc.src': videoInfo.src[0]
          });
        }, ts, sign
      };
      polyv.getVideo(vidObj);
    },
    isShowBsClick:function(){
      let that=this;
      this.setData({
        'videoSrc.isShowBeishu':true
      })
      setTimeout(()=>{
        that.setData({
          'videoSrc.isShowBeishu':false
        })
      },6000)
    },
    clickShowBeishu:function(){
      let that=this;
      this.setData({
        'videoSrc.showBeishu':!that.data.videoSrc.showBeishu
      })
    },
    clickShowBeishu2:function(){
      let that=this;
      this.setData({
        'videoSrc.showBeishu':false
      })
    },
    itemClick:function(e){
      let that=this;
      let bei=e.currentTarget.dataset.bei;
      let viewBei=e.currentTarget.dataset.view;
      that.setData({
        'videoSrc.view':viewBei,
        'videoSrc.showBeishu':false,
      })
      wx.createVideoContext('myVideo').playbackRate(Number(bei));
      console.log(e.currentTarget.dataset.bei)
    },

    /**
     * 生命周期函数--监听页面初次渲染完成
     */
    onReady: function () {
      this.videoContext = wx.createVideoContext('myVideo')
    },

    /**
     * 生命周期函数--监听页面显示
     */
    onShow: function () {
      if(wx.getStorageSync('members') && wx.getStorageSync('members').mobile==''){
        this.selectComponent('#phone').setData({
          phoneVisible:true
        })
      }

      
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

    },

    /**
     * 页面上拉触底事件的处理函数
     */
    onReachBottom: function () {

    },

    showmulu: function(){
      console.log('ss');
      this.setData({
        showmulu:true,
        neirong1:false,
        jianyi:false
      })
    },
    showneirong: function(){
      console.log('ss');
      this.setData({
        showmulu:false,
        neirong1:true,
        jianyi:false
      })
    },
    showjianyi: function(){
      console.log('ss');
      //debugger;
      this.setData({
        showmulu:false,
        neirong1:false,
        jianyi:true
      })
    },

    downloadDoc : function(){
      console.log('sss');
      const filePath = 'https://cnd.yousenjiaoyu.com/0d/26a18b84fae565234aa7fa6c234d44.docx?attname=%E6%B5%8B%E8%AF%95.docx'; // 替换为实际的文档路径
      const fileName = 'document.pdf'; // 替换为实际的文档名称
      // wx.openDocument({
      //   filePath: filePath, // 替换为实际的文件路径
      //   success: function(res) {
      //     console.log('文件打开成功');
      //     // 在这里可以添加其他操作，如获取文件信息或进行其他处理
      //   },
      //   fail: function(err) {
      //     console.error('文件打开失败', err);
      //     // 在这里可以添加错误处理逻辑
      //   }
      // });
      // wx.downloadFile({
      //   url: 'https://cnd.yousenjiaoyu.com/0d/26a18b84fae565234aa7fa6c234d44.docx',//仅为示例，并非真实的资源
      //  // filePath: wx.env.USER_DATA_PATH + `1.pdf`,
      //   success (res) {
      //     // 只要服务器有响应数据，就会把响应内容写入文件并进入 success 回调，业务需要自行判断是否下载到了想要的内容
      //     if (res.statusCode === 200) {
      //       wx.playVoice({
      //         filePath: res.tempFilePath
      //       })
      //     }
      //   }
      // })

      wx.downloadFile({

        url: 'https://cnd.yousenjiaoyu.com/0d/26a18b84fae565234aa7fa6c234d44.docx',

        success(res) {

          const filePath = res.tempFilePath    

          wx.openDocument({

            filePath,

            showMenu: true,

            fileType: 'pdf',

            success(res) {

              console.log('打开文档成功', res)

            }

          })

        }

      })
    
    },
    /**
     * 用户点击右上角分享
     */
    onShareAppMessage: function () {
      
      if(this.data.chapterid){
        return {
          title: this.data.hdata.title + '（' + this.data.thevideoshow + '）',
          path: '/pages/freeCourseDetails/freeCourseDetails?pk_id='+this.data.pk_id + '&chapterid=' + this.data.chapterid,
        }
      }else{
        return {
          title: this.data.hdata.title + '（' + this.data.thevideoshow + '）',
          path: '/pages/freeCourseDetails/freeCourseDetails?pk_id='+this.data.pk_id,
        }
      }
    }
  }
})