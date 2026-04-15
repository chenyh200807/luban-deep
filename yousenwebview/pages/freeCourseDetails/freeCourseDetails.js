// package/freeCourseDetails/freeCourseDetails.js
var behavior = require('../../utils/behavior')
var utilMd5 = require('../../utils/md5.js');

let polyvModule = null;

function getPolyvModule() {
  if (!polyvModule) {
    const loadedModule = require('../../utils/polyv.js');
    polyvModule =
      loadedModule && loadedModule.default ? loadedModule.default : loadedModule;
  }
  return polyvModule;
}

Component({
  behaviors: [behavior],

  /**
   * 页面的初始数据
   */
  data: {
    pk_id: '',
    videoSrc: {
      src: '',
      showBeishu: false,
      view: '倍速',
      autoplay: true,
      isShowBeishu: false
    },
    loadingDetail: true,
    detailError: '',
    showmulu: true,
    neirong1: false,
    neirong: '',
    introHtmlRaw: '',
    introContentReady: false,
    hdata: {
      title: ''
    },
    thevideoshow: '',
    chapterid: '',
    activeChapterIndex: -1,
    kechengmulu: '',
    kechengneirong: '',
    show: false,
    videotitle: '',
    gratisDetail: {
      chapter: []
    }
  },
  methods: {
    clearBeishuTimer: function() {
      if (this.beishuTimer) {
        clearTimeout(this.beishuTimer);
        this.beishuTimer = null;
      }
    },
    scheduleBeishuHide: function() {
      this.clearBeishuTimer();
      this.beishuTimer = setTimeout(() => {
        this.setData({
          'videoSrc.isShowBeishu': false
        });
      }, 6000);
    },
    getSafeChapterList: function(detail) {
      if (detail && Array.isArray(detail.chapter)) {
        return detail.chapter.map(item => Object.assign({}, item));
      }
      return [];
    },
    getSafeIntroData: function(hdataList, fallbackTitle) {
      const source = Array.isArray(hdataList) ? hdataList[0] : hdataList;
      const hdata = source && typeof source === 'object' ? Object.assign({}, source) : {};
      if (!hdata.title && fallbackTitle) {
        hdata.title = fallbackTitle;
      }
      hdata.introduce = hdata.introduce || '';
      return hdata;
    },
    buildRichTextNodes: function(html) {
      return html
        ? html.replace(/\<img/gi, '<img style="max-width:100%;height:auto"')
        : '';
    },
    resolveInitialChapter: function(chapterList, preferredChapterId, preferredPlayId) {
      const byChapterId = preferredChapterId
        ? chapterList.findIndex(item => String(item.id) === String(preferredChapterId))
        : -1;
      if (byChapterId > -1) {
        return {
          index: byChapterId,
          item: chapterList[byChapterId]
        };
      }
      const byPlayId = preferredPlayId
        ? chapterList.findIndex(item => String(item.play_id) === String(preferredPlayId))
        : -1;
      if (byPlayId > -1) {
        return {
          index: byPlayId,
          item: chapterList[byPlayId]
        };
      }
      if (chapterList.length > 0) {
        return {
          index: 0,
          item: chapterList[0]
        };
      }
      return {
        index: -1,
        item: null
      };
    },
    resetVideoState: function() {
      this.clearBeishuTimer();
      this.pendingAutoPlaySeq = 0;
      this.videoRequestSeq = (this.videoRequestSeq || 0) + 1;
      if (this.videoContext && this.videoContext.pause) {
        this.videoContext.pause();
      }
    },
    cleanupPage: function(options) {
      this.resetVideoState();
      this.detailRequestSeq = (this.detailRequestSeq || 0) + 1;
      this.videoRequestSeq = (this.videoRequestSeq || 0) + 1;
      if (options && options.destroy && polyvModule && polyvModule.destroy) {
        polyvModule.destroy();
      }
    },
    requestVideoSrc: function(vid, shouldAutoPlay) {
      if (!vid) {
        return;
      }
      const polyv = getPolyvModule();
      if (!polyv || typeof polyv.getVideo !== 'function') {
        this.pendingAutoPlaySeq = 0;
        console.error('polyv sdk unavailable');
        return;
      }
      const requestSeq = (this.videoRequestSeq || 0) + 1;
      this.videoRequestSeq = requestSeq;
      this.pendingAutoPlaySeq = shouldAutoPlay ? requestSeq : 0;
      const timestamp = Date.parse(new Date());
      const secretKey = 'mnABa9XMn8';
      const ts = timestamp;
      const sign = utilMd5.hexMD5(secretKey + vid + ts);
      const that = this;
      polyv.getVideo({
        vid: vid,
        ts: ts,
        sign: sign,
        callback: function(videoInfo) {
          if (requestSeq !== that.videoRequestSeq) {
            return;
          }
          const src = videoInfo && videoInfo.src
            ? (Array.isArray(videoInfo.src) ? videoInfo.src[0] : videoInfo.src)
            : '';
          if (!src) {
            that.pendingAutoPlaySeq = 0;
            return;
          }
          that.setData({
            'videoSrc.src': src
          });
          if (that.pendingAutoPlaySeq === requestSeq) {
            setTimeout(() => {
              if (that.pendingAutoPlaySeq !== requestSeq) {
                return;
              }
              if (that.videoContext && that.videoContext.play) {
                that.videoContext.play();
              }
            }, 350);
          }
        }
      });
    },
    startInitialVideo: function(detail, initial) {
      const playId =
        detail && detail.play_id
          ? detail.play_id
          : initial && initial.item && initial.item.play_id
            ? initial.item.play_id
            : '';
      if (!playId) {
        return;
      }
      try {
        this.requestVideoSrc(playId, true);
      } catch (error) {
        this.pendingAutoPlaySeq = 0;
        console.error('video init failed', error);
      }
    },
    /**
     * 生命周期函数--监听页面加载
     */
    onLoad: function (options) {
      this.detailRequestSeq = 0;
      this.videoRequestSeq = 0;
      this.pendingAutoPlaySeq = 0;
      this.beishuTimer = null;
      if (options.pk_id) {
        this.setData({
          pk_id: options.pk_id,
          chapterid: options.chapterid || '',
          loadingDetail: true,
          detailError: '',
          show: false,
          gratisDetail: {
            chapter: []
          },
          hdata: {
            title: ''
          },
          neirong: '',
          introHtmlRaw: '',
          introContentReady: false,
          thevideoshow: '',
          videotitle: '',
          activeChapterIndex: -1,
        });
        this.getGratisDetail();
      }
    },
    getGratisDetail() {
      const requestSeq = ++this.detailRequestSeq;
      const members = wx.getStorageSync('members');
      let data = {
        pk_id: this.data.pk_id,
        chapterid: this.data.chapterid,
        fk_user_id: members ? members.pk_id : 0
      };
      this.resetVideoState();
      this.setData({
        loadingDetail: true,
        detailError: '',
        show: false
      });
      this.isPostHttp('Getmajordetailedzm', data, true).then(res => {
        if (requestSeq !== this.detailRequestSeq) {
          return;
        }
        if (res.status == 1) {
          const detail = res.data || {};
          const chapterList = this.getSafeChapterList(detail);
          const hdata = this.getSafeIntroData(res.hdata, detail.name || '');
          const initial = this.resolveInitialChapter(chapterList, this.data.chapterid, detail.play_id);
          const shouldShowVideo = res.show !== false && Boolean(detail.play_id || initial.item);

          wx.setNavigationBarTitle({
            title: detail.name || '佑森好课'
          });

          if (res.showvier == 27) {
            wx.redirectTo({
              url: '/pages/freeCourseDetailsonline/freeCourseDetailsonline'
            });
            return;
          }

          this.setData({
            gratisDetail: Object.assign({}, detail, {
              chapter: chapterList
            }),
            hdata: hdata,
            neirong: '',
            introHtmlRaw: hdata.introduce || '',
            introContentReady: false,
            thevideoshow: initial.item ? initial.item.title : (detail.name || ''),
            chapterid: initial.item && initial.item.id ? initial.item.id : this.data.chapterid,
            activeChapterIndex: initial.index,
            videotitle: initial.item && initial.item.title ? '正在播放：  ' + initial.item.title : '',
            kechengmulu: res.kechengmulu || '',
            kechengneirong: res.kechengneirong || '',
            show: shouldShowVideo,
            loadingDetail: false
          });

          this.startInitialVideo(detail, initial);

        } else {
          this.setData({
            loadingDetail: false,
            detailError: res.msg || '课程内容暂不可用'
          });
        }
      }).catch(() => {
        if (requestSeq !== this.detailRequestSeq) {
          return;
        }
        this.setData({
          loadingDetail: false,
          detailError: '课程加载失败，请稍后重试'
        });
      });
    },
    //选择课程播放
    choicePlays: function(e) {
      let { video_id, index, flag } = e.currentTarget.dataset;
      const chapterList = this.data.gratisDetail && this.data.gratisDetail.chapter ? this.data.gratisDetail.chapter : [];
      const currentChapter = chapterList[index];
      if (!currentChapter) {
        return;
      }
      this.clearBeishuTimer();
      if (flag) {
        this.setData({
          activeChapterIndex: index,
          chapterid: currentChapter.id || this.data.chapterid,
          videotitle: '正在播放：  ' + (currentChapter.title || ''),
          thevideoshow: currentChapter.title || '',
          'videoSrc.isShowBeishu': true
        });
        this.scheduleBeishuHide();
        if (video_id) {
          this.requestVideoSrc(video_id, true);
        }
      } else {
        this.pendingAutoPlaySeq = 0;
        if (this.videoContext && this.videoContext.pause) {
          this.videoContext.pause();
        }
        this.setData({
          activeChapterIndex: -1,
          chapterid: currentChapter.id || this.data.chapterid,
          thevideoshow: currentChapter.title || this.data.thevideoshow,
          'videoSrc.isShowBeishu': true
        });
        this.scheduleBeishuHide();
      }
    },
    //第三方视频
    publicVideo: function(id) {
      this.requestVideoSrc(id, true);
    },
    staPlay: function() {
      this.pendingAutoPlaySeq = 0;
    },
    endPlay: function() {
      return;
    },
    handleVideoReady: function() {
      if (!this.pendingAutoPlaySeq || this.pendingAutoPlaySeq !== this.videoRequestSeq) {
        return;
      }
      if (this.videoContext && this.videoContext.play) {
        this.videoContext.play();
      }
      this.pendingAutoPlaySeq = 0;
    },
    isShowBsClick: function() {
      this.clearBeishuTimer();
      this.setData({
        'videoSrc.isShowBeishu': true
      });
      this.scheduleBeishuHide();
    },
    clickShowBeishu: function() {
      this.setData({
        'videoSrc.showBeishu': !this.data.videoSrc.showBeishu
      });
    },
    clickShowBeishu2: function() {
      this.setData({
        'videoSrc.showBeishu': false
      });
    },
    itemClick: function(e) {
      let bei = e.currentTarget.dataset.bei;
      let viewBei = e.currentTarget.dataset.view;
      this.setData({
        'videoSrc.view': viewBei,
        'videoSrc.showBeishu': false
      });
      wx.createVideoContext('myVideo').playbackRate(Number(bei));
    },

    /**
     * 生命周期函数--监听页面初次渲染完成
     */
    onReady: function () {
      this.videoContext = wx.createVideoContext('myVideo');
      if (this.pendingAutoPlaySeq && this.videoContext && this.videoContext.play) {
        this.videoContext.play();
      }
    },

    /**
     * 生命周期函数--监听页面显示
     */
    onShow: function () {
      const members = wx.getStorageSync('members');
      if (members && members.mobile == '') {
        const phone = this.selectComponent('#phone');
        if (phone) {
          phone.setData({
            phoneVisible: true
          });
        }
      }
    },

    /**
     * 生命周期函数--监听页面隐藏
     */
    onHide: function () {
      this.cleanupPage({ destroy: false });
    },

    /**
     * 生命周期函数--监听页面卸载
     */
    onUnload: function () {
      this.cleanupPage({ destroy: true });
    },

    showmulu: function() {
      this.setData({
        showmulu: true,
        neirong1: false
      });
    },
    showneirong: function() {
      const nextState = {
        showmulu: false,
        neirong1: true
      };
      if (!this.data.introContentReady) {
        nextState.neirong = this.buildRichTextNodes(this.data.introHtmlRaw);
        nextState.introContentReady = true;
      }
      this.setData(nextState);
    },
    /**
     * 用户点击右上角分享
     */
    onShareAppMessage: function () {
      const shareTitle = this.data.hdata && this.data.hdata.title
        ? this.data.hdata.title
        : (this.data.gratisDetail && this.data.gratisDetail.name ? this.data.gratisDetail.name : '佑森好课');
      const videoTitle = this.data.thevideoshow || '课程详情';
      if (this.data.chapterid) {
        return {
          title: shareTitle + '（' + videoTitle + '）',
          path: '/pages/freeCourseDetails/freeCourseDetails?pk_id=' + this.data.pk_id + '&chapterid=' + this.data.chapterid
        };
      } else {
        return {
          title: shareTitle + '（' + videoTitle + '）',
          path: '/pages/freeCourseDetails/freeCourseDetails?pk_id=' + this.data.pk_id
        };
      }
    }
  }
})
