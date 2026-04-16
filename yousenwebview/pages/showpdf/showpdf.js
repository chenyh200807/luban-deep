const ONLINE_PDF_CACHE_KEY = 'showpdf_online_pdf_cache_v1';
const ONLINE_PDF_CACHE_TTL = 7 * 24 * 60 * 60 * 1000;
const onlinePdfCacheMemory = {};

Page({
  data: {
    pdfFiles: [],
    loading: true,
    errorMsg: ''
  },

  onLoad() {
    this.initPdfList();
  },

  initPdfList() {
    const localPdfs = wx.getStorageSync('localPdfs') || [];

    this.setData({
      pdfFiles: localPdfs,
      loading: false
    });
  },

  previewPdf(e) {
    const index = e.currentTarget.dataset.index;
    const pdfFile = this.data.pdfFiles[index];

    this.setData({ errorMsg: '' });

    if (!pdfFile) {
      this.setData({ errorMsg: '未找到该PDF文件' });
      return;
    }

    wx.showLoading({ title: '准备预览...' });

    if (pdfFile.type === 'online') {
      this.openOnlinePdf(pdfFile, { showLoading: false });
    } else {
      wx.hideLoading();
      this.openPdfDocument(pdfFile.path);
    }
  },

  getOnlinePdfCacheKey(url) {
    return `${ONLINE_PDF_CACHE_KEY}:${url}`;
  },

  readOnlinePdfCache(url) {
    if (!url) {
      return Promise.reject(new Error('missing url'));
    }

    const memoryCache = onlinePdfCacheMemory[url];
    if (memoryCache && memoryCache.filePath) {
      if (!memoryCache.updatedAt || Date.now() - memoryCache.updatedAt <= ONLINE_PDF_CACHE_TTL) {
        return this.validateLocalFilePath(memoryCache.filePath).then(() => memoryCache.filePath);
      }
    }

    try {
      const cache = wx.getStorageSync(this.getOnlinePdfCacheKey(url));
      if (!cache || typeof cache !== 'object' || !cache.filePath) {
        return Promise.reject(new Error('cache miss'));
      }
      if (cache.updatedAt && Date.now() - Number(cache.updatedAt) > ONLINE_PDF_CACHE_TTL) {
        this.clearOnlinePdfCache(url);
        return Promise.reject(new Error('cache expired'));
      }
      return this.validateLocalFilePath(cache.filePath).then(() => {
        onlinePdfCacheMemory[url] = {
          filePath: cache.filePath,
          updatedAt: Number(cache.updatedAt) || Date.now()
        };
        return cache.filePath;
      });
    } catch (error) {
      return Promise.reject(error);
    }
  },

  writeOnlinePdfCache(url, filePath) {
    const cache = {
      filePath,
      updatedAt: Date.now()
    };
    onlinePdfCacheMemory[url] = cache;
    try {
      wx.setStorageSync(this.getOnlinePdfCacheKey(url), cache);
    } catch (error) {}
  },

  clearOnlinePdfCache(url) {
    delete onlinePdfCacheMemory[url];
    try {
      wx.removeStorageSync(this.getOnlinePdfCacheKey(url));
    } catch (error) {}
  },

  validateLocalFilePath(filePath) {
    return new Promise((resolve, reject) => {
      wx.getFileInfo({
        filePath,
        success: () => resolve(filePath),
        fail: reject
      });
    });
  },

  downloadAndCacheOnlinePdf(pdfFile) {
    return new Promise((resolve, reject) => {
      wx.downloadFile({
        url: pdfFile.url,
        success: res => {
          if (res.statusCode !== 200) {
            reject(new Error('下载PDF失败，请稍后重试'));
            return;
          }

          wx.saveFile({
            tempFilePath: res.tempFilePath,
            success: saveRes => {
              this.writeOnlinePdfCache(pdfFile.url, saveRes.savedFilePath);
              resolve(saveRes.savedFilePath);
            },
            fail: () => {
              resolve(res.tempFilePath);
            }
          });
        },
        fail: err => {
          console.error('下载失败:', err);
          reject(new Error(err.errMsg || '未知错误'));
        }
      });
    });
  },

  openOnlinePdf(pdfFile, options = {}) {
    if (options.showLoading !== false) {
      wx.showLoading({ title: '准备预览...' });
    }
    this.readOnlinePdfCache(pdfFile.url).then(filePath => {
      wx.hideLoading();
      this.openPdfDocument(filePath, {
        onFail: err => {
          this.clearOnlinePdfCache(pdfFile.url);
          console.error('缓存PDF打开失败:', err);
          this.openOnlinePdf(pdfFile);
        }
      });
    }).catch(() => {
      this.downloadAndCacheOnlinePdf(pdfFile).then(filePath => {
        wx.hideLoading();
        this.openPdfDocument(filePath);
      }).catch(err => {
        wx.hideLoading();
        console.error('下载失败:', err);
        this.setData({ errorMsg: '下载PDF失败: ' + (err.errMsg || err.message || '未知错误') });
      });
    });
  },

  openPdfDocument(filePath, options = {}) {
    if (!filePath) {
      this.setData({ errorMsg: '文件路径不存在' });
      return;
    }

    wx.openDocument({
      fileType: 'pdf',
      filePath: filePath,
      showMenu: true,
      fail: err => {
        if (options && typeof options.onFail === 'function') {
          options.onFail(err);
          return;
        }
        console.error('打开PDF失败:', err);
        this.setData({ errorMsg: '打开PDF失败: ' + (err.errMsg || '未知错误') });
      }
    });
  },

  chooseLocalPdf() {
    wx.chooseMessageFile({
      count: 1,
      type: 'file',
      extension: ['.pdf'],
      success: res => {
        const tempFile = res.tempFiles[0];

        if (!tempFile.name.toLowerCase().endsWith('.pdf')) {
          this.setData({ errorMsg: '请选择PDF格式的文件' });
          return;
        }

        const newPdf = {
          id: Date.now(),
          name: tempFile.name,
          path: tempFile.path,
          size: this.formatFileSize(tempFile.size),
          type: "local",
          addedTime: new Date().toISOString()
        };

        const updatedPdfs = [...this.data.pdfFiles, newPdf];
        this.setData({ pdfFiles: updatedPdfs });

        const localPdfs = wx.getStorageSync('localPdfs') || [];
        localPdfs.push(newPdf);
        wx.setStorageSync('localPdfs', localPdfs);

        this.openPdfDocument(newPdf.path);
      },
      fail: err => {
        console.error('选择文件失败:', err);
        if (err.errMsg !== 'chooseMessageFile:fail cancel') {
          this.setData({ errorMsg: '选择文件失败: ' + (err.errMsg || '未知错误') });
        }
      }
    });
  },

  formatFileSize(bytes) {
    if (bytes < 1024) return bytes + 'B';
    else if (bytes < 1048576) return (bytes / 1024).toFixed(1) + 'KB';
    else return (bytes / 1048576).toFixed(1) + 'MB';
  }
})
