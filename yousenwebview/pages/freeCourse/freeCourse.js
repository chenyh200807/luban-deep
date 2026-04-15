// package/freeCourse/freeCourse.js
var behavior = require('../../utils/behavior')
var analytics = require('../../utils/analytics')
Component({
  behaviors: [behavior],

  /**
   * 页面的初始数据
   */
  data: {
    showModal: false,
    showurl:'',
    shownum:1,
    showurl1:'',
    showurl2:'',
    showimg:'',
    modalImageLoading: false,
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
    imageUrl: '/images/icon/play_icon_02.png', // 设置图片地址，可以替换为自己的图片路径
    ggimage:'',
    ggimageurl:'',
    selectedMajorLabel: '一级建造师',
    selectedSubjectLabel: '建筑实务',
    currentCourseCount: 0,
    featuredCourseTitle: '',
    featuredCourseImage: '',
    deeptutorEntryEnabled: true,
    deeptutorEntryVisible: true,
    deeptutorEntryConfig: {
      title: "鲁班AI智考",
      subtitle: "智能答疑入口",
      tip: "点击进入",
      badge: "AI",
      variant: "blue",
    },
  },
  lifetimes: {
    attached() {
      this.syncDeeptutorEntryState();
    },
  },
  pageLifetimes: {
    show() {
      this.syncDeeptutorEntryState();
      this.trackDeeptutorEntryExposure();
    },
    hide() {
      this._deeptutorEntryExposureTracked = false;
    },
  },
  methods: {
    initGratisCourseState: function() {
      this.gratisCourseRequestSeq = 0;
      this.gratisCourseLoaded = false;
      this.gratisCourseHasMore = true;
      this.gratisCourseLoading = false;
    },
    buildGratisCourseRequest: function(targetPage) {
      return {
        page: targetPage,
        fk_user_id: 0,
        fk_major_id: this.data.major_id,
        subject_id: this.data.subject_id,
        cate_id: this.data.cate_id,
        project: this.data.multiArray[0][this.data.multiIndex[0]]
      };
    },
    refreshSelectionSummary: function() {
      const majorIndex = this.data.multiIndex[0] || 0;
      const subjectIndex = this.data.multiIndex[1] || 0;
      const majorList = this.data.multiArray[0] || [];
      const subjectList = this.data.multiArray[1] || [];
      this.setData({
        selectedMajorLabel: majorList[majorIndex] || majorList[0] || '',
        selectedSubjectLabel: subjectList[subjectIndex] || subjectList[0] || ''
      });
    },
    updateGratisCoursePromotion: function(res) {
      this.setData({
        ggimageurl: res.ggimageurl,
        ggimage: res.ggimage,
        shownum: res.shownum,
        showurl1: res.showurl1,
        showurl2: res.showurl2
      });
    },
    normalizeGratisCourseList: function(courseList) {
      const source = Array.isArray(courseList) ? courseList : [];
      return source.map((item, courseIndex) => {
        const teachers = Array.isArray(item.teacher) ? item.teacher : [];
        return Object.assign({}, item, {
          teacher: teachers.map((teacher, teacherIndex) => {
            const stableKey =
              teacher && teacher.id !== undefined && teacher.id !== null && teacher.id !== ""
                ? String(teacher.id)
                : teacher && teacher.pk_id !== undefined && teacher.pk_id !== null && teacher.pk_id !== ""
                  ? String(teacher.pk_id)
                  : teacher && teacher.teacher_id !== undefined && teacher.teacher_id !== null && teacher.teacher_id !== ""
                    ? String(teacher.teacher_id)
                    : teacher && teacher.user_id !== undefined && teacher.user_id !== null && teacher.user_id !== ""
                      ? String(teacher.user_id)
                      : teacher && teacher.uid !== undefined && teacher.uid !== null && teacher.uid !== ""
                        ? String(teacher.uid)
                        : `teacher-${courseIndex}-${teacherIndex}`;
            return Object.assign({}, teacher, {
              __teacherKey: stableKey
            });
          })
        });
      });
    },
    syncGratisCourseModal: function(res) {
      const showkey = wx.getStorageSync('showkey');
      const now = Date.now();
      const modalLocked = showkey > now;
      if (this.modalDisplayTimer) {
        clearTimeout(this.modalDisplayTimer);
        this.modalDisplayTimer = null;
      }
      if (!res.showimg || modalLocked) {
        if (this.data.showModal) {
          this.setData({
            showModal: false,
            modalImageLoading: false
          });
        }
        return;
      }
      wx.setStorageSync('showkey', now + 3 * 60 * 60 * 1000);
      this.modalDisplayTimer = setTimeout(() => {
        this.setData({
          showModal: true,
          showimg: res.showimg,
          showurl: res.showurl || '',
          modalImageLoading: true
        });
        this.modalDisplayTimer = null;
      }, 450);
    },
    finalizeGratisCourseRequest: function(options) {
      if (options && options.stopPullDownRefresh) {
        wx.stopPullDownRefresh();
      }
      if (options && options.showLoadMore) {
        wx.hideLoading();
      }
      this.gratisCourseLoading = false;
    },
    requestGratisCourse: function(options) {
      const requestOptions = options || {};
      const reset = Boolean(requestOptions.reset);
      const targetPage = reset ? 1 : this.data.page + 1;
      if (this.gratisCourseLoading) {
        if (requestOptions.stopPullDownRefresh) {
          wx.stopPullDownRefresh();
        }
        return Promise.resolve(false);
      }
      if (!reset && !this.gratisCourseHasMore) {
        return Promise.resolve(false);
      }
      const requestSeq = ++this.gratisCourseRequestSeq;
      this.gratisCourseLoading = true;
      if (requestOptions.showLoadMore) {
        wx.showLoading({
          title: '正在加载更多',
          mask: true
        });
      }
      return this.isPostHttp('Getmajorzm', this.buildGratisCourseRequest(targetPage)).then(res => {
        if (requestSeq !== this.gratisCourseRequestSeq) {
          return false;
        }
        this.syncDeeptutorEntryStateFromPayload(res);
        this.updateGratisCoursePromotion(res);
        const pageData = Array.isArray(res.data) ? res.data : [];
        const normalizedPageData = this.normalizeGratisCourseList(pageData);
        const hasPageData = res.status == 1 && pageData.length > 0;
        const nextList = reset
          ? normalizedPageData
          : this.data.getGratisCourseList.concat(normalizedPageData);
        this.gratisCourseLoaded = true;
        this.gratisCourseHasMore = hasPageData;
        return new Promise(resolve => {
          const featuredCourse = nextList.length > 0 ? nextList[0] : null;
          this.setData({
            page: hasPageData ? targetPage : (reset ? 1 : this.data.page),
            getGratisCourseList: nextList,
            noData: nextList.length === 0,
            currentCourseCount: nextList.length,
            featuredCourseTitle: featuredCourse ? featuredCourse.title : '',
            featuredCourseImage: featuredCourse && featuredCourse.cart_image ? featuredCourse.cart_image : (res.ggimage || '')
          }, () => {
            this.syncGratisCourseModal(res);
            resolve(hasPageData);
          });
        });
      }).catch(() => {
        return false;
      }).finally(() => {
        this.finalizeGratisCourseRequest(requestOptions);
      });
    },
    getGratisCourse: function(options) {
      return this.requestGratisCourse(options);
    },
    syncDeeptutorEntryState() {
      const app = getApp();
      const enabled =
        app && typeof app.getDeeptutorEntryEnabled === "function"
          ? app.getDeeptutorEntryEnabled()
          : !(
              app &&
              app.globalData &&
              app.globalData.deeptutorEntryEnabled === false
            );
      const config =
        app && typeof app.getDeeptutorEntryConfig === "function"
          ? app.getDeeptutorEntryConfig()
          : this.data.deeptutorEntryConfig;
      const currentConfig = JSON.stringify(this.data.deeptutorEntryConfig || {});
      const nextConfig = JSON.stringify(config || {});
      if (
        enabled !== this.data.deeptutorEntryEnabled ||
        enabled !== this.data.deeptutorEntryVisible ||
        currentConfig !== nextConfig
      ) {
        this.setData({
          deeptutorEntryEnabled: enabled,
          deeptutorEntryVisible: enabled,
          deeptutorEntryConfig: config,
        });
      }
      return enabled;
    },
    syncDeeptutorEntryStateFromPayload(payload) {
      const app = getApp();
      if (app && typeof app.syncDeeptutorEntryFlagFromPayload === "function") {
        app.syncDeeptutorEntryFlagFromPayload(payload);
      }
      return this.syncDeeptutorEntryState();
    },
    showDeeptutorEntryDisabledToast() {
      wx.showToast({
        title: "鲁班AI智考已关闭",
        icon: "none",
        duration: 2200,
      });
    },
    trackDeeptutorEntryExposure() {
      if (!this.data.deeptutorEntryVisible || this._deeptutorEntryExposureTracked) {
        return;
      }
      this._deeptutorEntryExposureTracked = true;
      analytics.track('deeptutor_entry_expose', {
        entry_source: 'free_course_inline_entry',
        entry_title: this.data.deeptutorEntryConfig.title,
        entry_variant: this.data.deeptutorEntryConfig.variant,
      });
    },
    rotateImage: function() {
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
      this.stopRotateImage();
      this.setData({
        multiIndex: e.detail.value
      })
      this.refreshSelectionSummary();
      if(this.data.multiArray[0][e.detail.value[0]] == undefined){
        this.data.multiArray[0][e.detail.value[0]] = Object.keys(this.data.allmajor)[0];
      }
      this.data.subject_id = this.data.allmajor[this.data.multiArray[0][e.detail.value[0]]][this.data.multiArray[1][e.detail.value[1]]];
      this.data.cate_id = 4;
      this.gratisCourseHasMore = true;
      this.getGratisCourse({
        reset: true
      })
    },
    bindMultiPickerColumnChange: function (e) {
      this.rotateImage();
      var data = {
        multiArray: this.data.multiArray,
        multiIndex: this.data.multiIndex
      };

    data.multiIndex[e.detail.column] = e.detail.value;
      switch (e.detail.column) {
        case 0:
          switch (data.multiIndex[0]) {
            case 0:
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
      this.refreshSelectionSummary();
    },
    /**
     * 生命周期函数--监听页面加载
     */
    onLoad: function (options) {
      this.initGratisCourseState();
      this.data.major_id = wx.getStorageSync('major_id')
      this.data.major_id = 10
      //如果没有传值进来，就直接默认
      this.data.subject_id = 63;
      this.data.cate_id = 4;
      this.data.multiArray[0] = Object.keys(this.data.allmajor);
      this.data.multiArray[1] = Object.keys(this.data.allmajor['一级建造师'])
      
      var data = {
        multiArray: this.data.multiArray,
        multiIndex: [0, 0]
      };
      this.setData(data);
      this.refreshSelectionSummary();
    },

    //关闭弹窗
    closeModal: function () {
      if (this.modalDisplayTimer) {
        clearTimeout(this.modalDisplayTimer);
        this.modalDisplayTimer = null;
      }
      this.setData({
        showModal: false,
        modalImageLoading: false
      });
    },
    handleModalImageLoad: function() {
      if (!this.data.showModal) {
        return;
      }
      this.setData({
        modalImageLoading: false
      });
    },
    handleModalImageError: function() {
      this.closeModal();
      wx.showToast({
        title: '广告加载失败',
        icon: 'none',
        duration: 1800
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

    //点击导航
    switchTab(e){
      if(e.detail == this.data.major_id){
        return
      }
      this.gratisCourseHasMore = true;
      this.setData({
        major_id:e.detail,
        page:1,
        getGratisCourseList:[]
      })
      this.getGratisCourse({
        reset: true
      })
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
      if (!this.gratisCourseLoaded) {
        this.getGratisCourse({
          reset: true
        })
      }

    },

    /**
     * 生命周期函数--监听页面隐藏
     */
    onHide: function () {
      if (this.modalDisplayTimer) {
        clearTimeout(this.modalDisplayTimer);
        this.modalDisplayTimer = null;
      }
    },

    /**
     * 生命周期函数--监听页面卸载
     */
    onUnload: function () {
      if (this.modalDisplayTimer) {
        clearTimeout(this.modalDisplayTimer);
        this.modalDisplayTimer = null;
      }
    },

    /**
   * 页面相关事件处理函数--监听用户下拉动作
   */
  onPullDownRefresh: function () {
    this.gratisCourseHasMore = true;
    this.getGratisCourse({
      reset: true,
      stopPullDownRefresh: true
    });
  },

  /**
   * 页面上拉触底事件的处理函数
   */
  onReachBottom: function () {
    this.getGratisCourse({
      showLoadMore: true
    });
  },

    /**
     * 用户点击右上角分享
     */
    onShareAppMessage: function () {
      return {
        title: '佑森好课',
        path: 'pages/freeCourse/freeCourse?top_id='+wx.getStorageSync('members').pk_id+'&major_id='+wx.getStorageSync('major_id')+'&major_title='+wx.getStorageSync('major_title'),
      }
    },

    //省略标题内容
    gettitle:function(e){
      return 1;
    },

    // 跳转到鲁班AI智考原生分包入口
    navigateToShop:function(e){
      if (!this.syncDeeptutorEntryState()) {
        this.showDeeptutorEntryDisabledToast();
        return;
      }
      const entrySource = 'free_course_inline_entry';
      const returnTo = '/packageDeeptutor/pages/chat/chat?entry_source=' + entrySource;
      analytics.track('deeptutor_entry_click', {
        entry_source: entrySource,
        entry_title: this.data.deeptutorEntryConfig.title,
        entry_variant: this.data.deeptutorEntryConfig.variant,
      });
      wx.navigateTo({
        url:
          '/packageDeeptutor/pages/login/login?entrySource=' +
          encodeURIComponent(entrySource) +
          '&returnTo=' +
          encodeURIComponent(returnTo),
        fail: () => {
          wx.showToast({
            title: '鲁班AI智考暂时无法打开',
            icon: 'none',
            duration: 2500
          });
        }
      })
    }
    
  }
})
